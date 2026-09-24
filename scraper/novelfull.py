import re
import time
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY
from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup

logger = logging.getLogger(__name__)

class NovelFullScraper(BaseScraper):
    name = "NovelFull"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def can_handle(self, url: str) -> bool:
        u = url.lower()
        return "novelfull." in u or "allnovelfull." in u

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path.strip("/")
        slug = path.split("/")[-1]
        slug = re.sub(r"\.html$", "", slug)
        return slug or "novelfull-novel"

    def _fetch_html(self, url: str) -> str:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.encoding = "utf-8"
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 404:
                    return ""
            except requests.RequestException as e:
                logger.warning(f"Error fetching {url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
        raise RuntimeError(f"Failed to fetch {url}")

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h3.title") or soup.select_one(".books .title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        author_el = soup.select_one("a[href*='/author/']") or soup.select_one(".info span:-soup-contains('Author') + a")
        author = author_el.get_text(strip=True) if author_el else "Unknown"

        desc_el = soup.select_one(".desc-text") or soup.select_one("#tab-description")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        cover_url = None
        cover_img = soup.select_one(".book img") or soup.select_one(".col-image img")
        if cover_img:
            src = cover_img.get("src") or cover_img.get("data-src")
            if src:
                cover_url = urljoin(base_url, src)

        categories = [
            a.get_text(strip=True)
            for a in soup.select("a[href*='/genre/'], a[href*='/category/']")
            if a.get_text(strip=True)
        ]

        # Chapters from list
        chapters: List[ChapterInfo] = []
        ch_links = soup.select(".list-chapter li a") or soup.select("#list-chapter a")
        for idx, a in enumerate(ch_links, start=1):
            href = a.get("href", "")
            if not href:
                continue
            ch_url = urljoin(base_url, href)
            ch_title = a.get_text(strip=True) or a.get("title", "")
            
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

        title_el = soup.select_one(".chapter-title") or soup.select_one("h2") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        m_num = re.search(r"chapter\s*(\d+)", title, re.I)
        num = int(m_num.group(1)) if m_num else 1

        content_div = soup.select_one("#chapter-content") or soup.select_one(".chapter-content")
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
