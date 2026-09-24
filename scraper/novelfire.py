import re
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup
from .fetcher import smart_fetch

logger = logging.getLogger(__name__)

class NovelFireScraper(BaseScraper):
    name = "Novel Fire"
    BASE_URL = "https://novelfire.net"

    def can_handle(self, url: str) -> bool:
        u = url.lower()
        return "novelfire.net" in u or "novelfire.org" in u or "novelfire.com" in u

    def parse_slug(self, url: str) -> str:
        # e.g. https://novelfire.net/book/the-golden-lord-has-a-perverted-sss-rank-summoning-system
        # e.g. https://novelfire.net/book/the-golden-lord-has-a-perverted-sss-rank-summoning-system/chapter-1
        path = urlparse(url).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "book":
            return parts[1]
        elif len(parts) == 1:
            return parts[0]
        return "novel"

    def _fetch_html(self, url: str) -> str:
        html, code = smart_fetch(url)
        return html if code == 200 else ""

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        book_url = f"{self.BASE_URL}/book/{slug}"
        html_doc = self._fetch_html(book_url)
        if not html_doc:
            html_doc = self._fetch_html(url)
        
        soup = BeautifulSoup(html_doc, "html.parser")

        # Title
        title_el = soup.select_one("h1.novel-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        # Author
        author_el = soup.select_one("a[href*='/author/']") or soup.select_one(".author")
        author = "Unknown"
        if author_el:
            author_text = author_el.get_text(strip=True)
            author = re.sub(r"^(?:by|author:)\s*", "", author_text, flags=re.I).strip()

        # Description
        desc_el = soup.select_one(".summary__content") or soup.select_one(".description") or soup.select_one(".desc-text")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        # Cover
        cover_url = None
        cover_img = soup.select_one(".book-cover img") or soup.select_one(".cover img") or soup.find("meta", property="og:image")
        if cover_img:
            if cover_img.name == "meta":
                cover_url = cover_img.get("content")
            else:
                src = cover_img.get("src") or cover_img.get("data-src")
                if src:
                    cover_url = urljoin(self.BASE_URL, src)

        # Categories
        categories = [
            a.get_text(strip=True)
            for a in soup.select("a[href*='/genre/'], a[href*='/category/']")
            if a.get_text(strip=True)
        ]

        # Fetch complete chapter list using /chapters?page=...
        chapters = self._fetch_all_chapters(slug, on_progress=on_progress)

        return NovelMetadata(
            title=title,
            slug=slug,
            url=book_url,
            platform=self.name,
            author=author,
            description=description,
            cover_url=cover_url,
            categories=categories,
            chapters=chapters
        )

    def _fetch_all_chapters(self, slug: str, on_progress=None) -> List[ChapterInfo]:
        chapters: List[ChapterInfo] = []
        page = 1
        seen_urls = set()

        while True:
            page_url = f"{self.BASE_URL}/book/{slug}/chapters?page={page}"
            try:
                html_doc = self._fetch_html(page_url)
            except Exception as e:
                logger.warning(f"Error fetching NovelFire chapters page {page}: {e}")
                break

            if not html_doc:
                break

            soup = BeautifulSoup(html_doc, "html.parser")
            ch_links = [a for a in soup.find_all("a", href=True) if "/chapter-" in a["href"]]

            if not ch_links:
                break

            new_found = 0
            for a in ch_links:
                href = a["href"]
                full_url = urljoin(self.BASE_URL, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                new_found += 1

                raw_title = a.get_text(strip=True)
                # Clean up repeated chapter numbers or relative dates
                clean_title = re.sub(r"^\d+\s*", "", raw_title)
                clean_title = re.sub(r"\s*\d+\s*(?:months?|days?|hours?|years?)\s*ago.*$", "", clean_title, flags=re.I).strip()
                if not clean_title:
                    clean_title = raw_title

                m = re.search(r"chapter\s*[\-\.]?\s*(\d+)", href, re.I)
                if not m:
                    m = re.search(r"chapter\s*[\-\.]?\s*(\d+)", clean_title, re.I)
                num = int(m.group(1)) if m else len(chapters) + 1

                chapters.append(ChapterInfo(
                    index=len(chapters) + 1,
                    number=num,
                    title=clean_title or f"Chapter {num}",
                    url=full_url
                ))

            if new_found == 0:
                break

            if on_progress:
                on_progress(f"Discovered {len(chapters)} chapters (page {page})...")

            # Check if there is a next page
            pag_links = soup.select(".pagination a, ul.pagination li a")
            pages_available = set()
            for pl in pag_links:
                m_p = re.search(r"page=(\d+)", pl.get("href", ""))
                if m_p:
                    pages_available.add(int(m_p.group(1)))

            if pages_available and max(pages_available) <= page:
                break

            page += 1
            if page > 50:  # Safety circuit breaker
                break

        # Sort chapters in ascending order
        unique_chapters = {}
        for ch in chapters:
            if ch.number not in unique_chapters:
                unique_chapters[ch.number] = ch

        sorted_chapters = sorted(unique_chapters.values(), key=lambda c: c.number)
        for idx, ch in enumerate(sorted_chapters, start=1):
            ch.index = idx

        return sorted_chapters

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h1.chapter-title") or soup.select_one(".chapter-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""
        if title:
            title = re.sub(r"^.*?-\s*", "", title)  # Remove novel name prefix if present
            title = re.sub(r"\[\s*\.\.\.\s*words\s*\]", "", title, flags=re.I).strip()

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
