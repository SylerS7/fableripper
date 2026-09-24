import re
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup
from .fetcher import smart_fetch, BotProtectionError

logger = logging.getLogger(__name__)

class RoyalRoadScraper(BaseScraper):
    name = "Royal Road"
    BASE_URL = "https://www.royalroad.com"

    def can_handle(self, url: str) -> bool:
        return "royalroad.com" in url.lower()

    def parse_slug(self, url: str) -> str:
        match = re.search(r"/fiction/(\d+)(?:/([^/?#]+))?", url)
        if match:
            f_id = match.group(1)
            slug_part = match.group(2) or "novel"
            return f"rr-{f_id}-{slug_part}"
        return "royalroad-novel"

    def _fetch_html(self, url: str) -> str:
        html, code = smart_fetch(url)
        return html if code == 200 else ""

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h1.font-white") or soup.select_one(".fic-title h1") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        author_el = soup.select_one("h4.font-white a") or soup.select_one("span[property='name']") or soup.select_one("h4 a")
        author = author_el.get_text(strip=True) if author_el else "Unknown"

        desc_el = soup.select_one(".description .portlet-body") or soup.select_one(".description")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        cover_url = None
        cover_img = soup.select_one("img.thumbnail") or soup.select_one(".cover-art-container img")
        if cover_img:
            src = cover_img.get("src")
            if src:
                cover_url = urljoin(self.BASE_URL, src)

        categories = []
        for tag in soup.select(".tags a, .fiction-tag"):
            t_text = tag.get_text(strip=True)
            if t_text and t_text not in categories:
                categories.append(t_text)

        chapters: List[ChapterInfo] = []
        ch_rows = soup.select("table#chapters tbody tr") or soup.select("tr[data-url]")
        for idx, row in enumerate(ch_rows, start=1):
            link = row.select_one("a[href*='/chapter/']") or row.select_one("a")
            if not link:
                continue
            href = link.get("href", "")
            ch_url = urljoin(self.BASE_URL, href)
            ch_title = link.get_text(strip=True)
            
            m = re.search(r"chapter\s*(\d+)", ch_title, re.I)
            num = int(m.group(1)) if m else idx

            chapters.append(ChapterInfo(
                index=idx,
                number=num,
                title=ch_title or f"Chapter {num}",
                url=ch_url
            ))

        return NovelMetadata(
            title=title,
            slug=slug,
            url=url,
            platform=self.name,
            author=author,
            description=description,
            cover_url=cover_url,
            categories=categories,
            chapters=chapters
        )

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h1.font-white") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        m_num = re.search(r"chapter\s*(\d+)", title, re.I)
        num = int(m_num.group(1)) if m_num else 1

        content_div = soup.select_one(".chapter-inner.chapter-content") or soup.select_one(".chapter-content")
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
