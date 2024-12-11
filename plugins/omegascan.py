from typing import List, AsyncIterable
from urllib.parse import urlparse, urljoin, quote_plus
import re

from bs4 import BeautifulSoup
from plugins.client import MangaClient, MangaCard, MangaChapter, LastChapter


class OmegaScanClient(MangaClient):
    base_url = urlparse("https://omegascans.com/")
    search_url = base_url.geturl()  # Base URL for search
    updates_url = urljoin(base_url.geturl(), "latest-releases/")  # URL for updates

    pre_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'
    }

    def __init__(self, *args, name="OmegaScan", **kwargs):
        super().__init__(*args, name=name, headers=self.pre_headers, **kwargs)

    def mangas_from_page(self, page: bytes):
        """Parse the manga list page and return manga cards."""
        bs = BeautifulSoup(page, "html.parser")

        container = bs.find('div', {'class': 'manga-list'})

        cards = container.find_all("div", {"class": "manga-card"})
        
        mangas = [card.find_next('a') for card in cards]
        names = [manga.get('title') for manga in mangas]
        urls = [urljoin(self.base_url.geturl(), manga.get('href')) for manga in mangas]
        images = [manga.find_next("img").get("src") for manga in mangas]

        mangas = [MangaCard(self, name, url, image) for name, url, image in zip(names, urls, images)]
        
        return mangas

    def chapters_from_page(self, page: bytes, manga: MangaCard = None):
        """Parse the manga's chapter page."""
        bs = BeautifulSoup(page, "html.parser")

        lis = bs.find_all("li", {"class": "chapter-item"})

        items = [li.find_next('a') for li in lis]

        links = [item.get("href") for item in items]
        texts = [item.string.strip() for item in items]

        chapters = [MangaChapter(self, text, link, manga, []) for text, link in zip(texts, links)]

        return chapters

    async def updates_from_page(self):
        """Get the latest updates page."""
        page = await self.get_url(self.updates_url)

        bs = BeautifulSoup(page, "html.parser")

        manga_items = bs.find_all("div", {"class": "manga-item"})

        urls = dict()

        for manga_item in manga_items:
            manga_url = urljoin(self.base_url.geturl(), manga_item.find_next("a").get("href"))
            
            chapter_url = urljoin(self.base_url.geturl(), manga_item.find_next("a").find_next("a").get("href"))

            urls[manga_url] = chapter_url

        return urls

    async def pictures_from_chapters(self, content: bytes, response=None):
        """Extract chapter image URLs from the chapter page."""
        bs = BeautifulSoup(content, "html.parser")

        cards = bs.find_all("div", {"class": "page-break"})

        images_url = [quote(img.find_next("img").get("src"), safe=':/%') for img in cards]

        return images_url

    async def search(self, query: str = "", page: int = 1) -> List[MangaCard]:
        """Search for manga by query."""
        request_url = f'{self.search_url}?s={quote_plus(query)}'

        content = await self.get_url(request_url)

        return self.mangas_from_page(content)

    async def get_chapters(self, manga_card: MangaCard, page: int = 1) -> List[MangaChapter]:
        """Retrieve chapters for a given manga."""
        request_url = f'{manga_card.url}'

        content = await self.get_url(request_url)

        return self.chapters_from_page(content, manga_card)[(page - 1) * 20:page * 20]

    async def iter_chapters(self, manga_url: str, manga_name: str) -> AsyncIterable[MangaChapter]:
        """Iterate over chapters for a manga."""
        manga_card = MangaCard(self, manga_name, manga_url, '')

        request_url = f'{manga_card.url}'

        content = await self.get_url(request_url)

        for chapter in self.chapters_from_page(content, manga_card):
            yield chapter

    async def contains_url(self, url: str):
        """Check if the URL belongs to OmegaScan."""
        return url.startswith(self.base_url.geturl())

    async def check_updated_urls(self, last_chapters: List[LastChapter]):
        """Check if the URLs of the last chapters have been updated."""
        updates = await self.updates_from_page()

        updated = []
        not_updated = []

        for lc in last_chapters:
            if lc.url in updates.keys():
                if updates.get(lc.url) != lc.chapter_url:
                    updated.append(lc.url)
            elif updates.get(lc.url) == lc.chapter_url:
                not_updated.append(lc.url)

        return updated, not_updated
