import re
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup, clean_title_str
from .fetcher import smart_fetch

logger = logging.getLogger(__name__)

class NovelFireScraper(BaseScraper):
    name = "Novel Fire"
    BASE_URL = "https://novelfire.net"

    def can_handle(self, url: str) -> bool:
        u = url.lower()
        return "novelfire.net" in u or "novelfire.org" in u or "novelfire.com" in u

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "book":
            return parts[1]
        elif len(parts) == 1:
            return parts[0]
        return "novel"

    def detect_chapter_number(self, url: str) -> Optional[int]:
        m = re.search(r"/chapter[-_]?(\d+)", url, re.I)
        if m:
            return int(m.group(1))
        return None

    def _fetch_html(self, url: str) -> str:
        html, code = smart_fetch(url)
        return html if code == 200 else ""

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        req_ch = self.detect_chapter_number(url)

        # Always fetch canonical book page for instant full metadata
        book_url = f"{self.BASE_URL}/book/{slug}"
        html_doc = self._fetch_html(book_url)
        if not html_doc and url != book_url:
            html_doc = self._fetch_html(url)
        
        soup = BeautifulSoup(html_doc, "html.parser")

        # 1. Title
        title_el = soup.select_one("h1.novel-title") or soup.select_one("h1")
        raw_title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()
        title = clean_title_str(raw_title)

        # 2. Author
        author_el = soup.select_one("a[href*='/author/']") or soup.select_one(".author")
        author = "Unknown"
        if author_el:
            author_text = author_el.get_text(strip=True)
            author = re.sub(r"^(?:by|author:)\s*", "", author_text, flags=re.I).strip()
            author = clean_title_str(author)

        # 3. Description (check meta itemprop first, then summary containers)
        description = ""
        meta_desc = soup.find("meta", itemprop="description") or soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()
        
        if not description:
            desc_el = (
                soup.select_one(".content.expand-wrapper")
                or soup.select_one(".summary .content")
                or soup.select_one(".summary")
                or soup.select_one(".desc-text")
            )
            if desc_el:
                description = desc_el.get_text("\n\n", strip=True)
                description = re.sub(r"^Summary\s*", "", description).strip()

        description = clean_title_str(description)

        # 4. Cover
        cover_url = None
        cover_img = soup.select_one(".book-cover img") or soup.select_one(".cover img") or soup.find("meta", property="og:image")
        if cover_img:
            if cover_img.name == "meta":
                cover_url = cover_img.get("content")
            else:
                src = cover_img.get("src") or cover_img.get("data-src")
                if src:
                    cover_url = urljoin(self.BASE_URL, src)

        # 5. Categories
        categories = [
            clean_title_str(a.get_text(strip=True))
            for a in soup.select("a[href*='/genre/'], a[href*='/category/']")
            if a.get_text(strip=True)
        ]

        # 6. Instant Total Chapters Detection
        total_chapters = 0
        for text in soup.stripped_strings:
            m = re.match(r"^(\d+)\s*chapters?$", text, re.I)
            if m:
                total_chapters = int(m.group(1))
                break

        # Fallback: check chapter mentions in headers
        if total_chapters == 0:
            for el in soup.find_all(attrs={"class": re.compile(r"chapter|stat|count", re.I)}):
                m = re.search(r"(\d+)\s*chapters?", el.get_text(), re.I)
                if m:
                    total_chapters = int(m.group(1))
                    break

        # If total_chapters found, construct the complete chapter list instantly
        chapters: List[ChapterInfo] = []
        if total_chapters > 0:
            for num in range(1, total_chapters + 1):
                ch_url = f"{self.BASE_URL}/book/{slug}/chapter-{num}"
                chapters.append(ChapterInfo(
                    index=num,
                    number=num,
                    title=f"Chapter {num}",
                    url=ch_url
                ))
        else:
            # Fallback: fetch page 1 of chapters
            p1_url = f"{self.BASE_URL}/book/{slug}/chapters?page=1"
            p1_html = self._fetch_html(p1_url)
            p1_soup = BeautifulSoup(p1_html, "html.parser")
            for a in p1_soup.find_all("a", href=True):
                href = a["href"]
                if "/chapter-" not in href:
                    continue
                ch_url = urljoin(self.BASE_URL, href)
                m = re.search(r"chapter\s*[\-\.]?\s*(\d+)", href, re.I)
                num = int(m.group(1)) if m else len(chapters) + 1
                raw_t = a.get_text(strip=True)
                clean_t = clean_title_str(raw_t) or f"Chapter {num}"
                chapters.append(ChapterInfo(
                    index=len(chapters) + 1,
                    number=num,
                    title=clean_t,
                    url=ch_url
                ))

        return NovelMetadata(
            title=title,
            slug=slug,
            url=book_url,
            platform=self.name,
            author=author,
            description=description,
            cover_url=cover_url,
            categories=categories,
            chapters=chapters,
            requested_chapter=req_ch
        )

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h1.chapter-title") or soup.select_one(".chapter-title") or soup.select_one("h1")
        raw_title = title_el.get_text(strip=True) if title_el else ""
        if raw_title:
            raw_title = re.sub(r"^.*?-\s*", "", raw_title)
            raw_title = re.sub(r"\[\s*\.\.\.\s*words\s*\]", "", raw_title, flags=re.I).strip()
        
        title = clean_title_str(raw_title)

        m_num = re.search(r"chapter\s*[\-\.]?\s*(\d+)", url, re.I)
        num = int(m_num.group(1)) if m_num else 1

        content_div = (
            soup.select_one("#chapter-container")
            or soup.select_one(".chapter-content")
            or soup.select_one("#content")
            or soup.select_one(".content")
        )
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
