import re
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup, clean_title_str
from .fetcher import smart_fetch

logger = logging.getLogger(__name__)

class NovelFullScraper(BaseScraper):
    name = "NovelFull"

    def can_handle(self, url: str) -> bool:
        u = url.lower()
        return "novelfull." in u or "allnovelfull." in u

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path.strip("/")
        # If url is a chapter: e.g. /perfect-world/chapter-1.html
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and any(k in parts[-1].lower() for k in ["chapter", "prologue", "afterword"]):
            slug = parts[0]
        else:
            slug = parts[-1] if parts else "novelfull-novel"
        slug = re.sub(r"\.html$", "", slug)
        return slug or "novelfull-novel"

    def detect_chapter_number(self, url: str) -> Optional[int]:
        m = re.search(r"chapter[-_](\d+)", url, re.I)
        if m:
            return int(m.group(1))
        return None

    def _fetch_html(self, url: str) -> str:
        try:
            html, code = smart_fetch(url)
            return html if code == 200 else ""
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return ""

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        req_ch = self.detect_chapter_number(url)
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        main_url = f"{base_url}/{slug}.html"

        if on_progress:
            on_progress(f"Fetching metadata for {slug}...")

        html_doc = self._fetch_html(main_url)
        if not html_doc and url != main_url:
            html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h3.title") or soup.select_one(".books .title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()
        title = clean_title_str(title)

        author_el = soup.select_one("a[href*='/author/']")
        author = "Unknown"
        if author_el:
            author = clean_title_str(author_el.get_text(strip=True))

        desc_el = soup.select_one(".desc-text") or soup.select_one("#tab-description")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        cover_url = None
        cover_img = soup.select_one(".book img") or soup.select_one(".col-image img")
        if cover_img:
            src = cover_img.get("src") or cover_img.get("data-src")
            if src:
                cover_url = urljoin(base_url, src)

        categories = [
            clean_title_str(a.get_text(strip=True))
            for a in soup.select("a[href*='/genre/'], a[href*='/category/']")
            if a.get_text(strip=True)
        ]

        # Extract all chapters across all pagination pages
        chapters = self._fetch_all_chapters(base_url, main_url, soup, on_progress=on_progress)

        return NovelMetadata(
            title=title,
            slug=slug,
            url=main_url,
            platform=self.name,
            author=author,
            description=description,
            cover_url=cover_url,
            categories=categories,
            chapters=chapters,
            requested_chapter=req_ch
        )

    def _fetch_all_chapters(self, base_url: str, main_url: str, main_soup: BeautifulSoup, on_progress=None) -> List[ChapterInfo]:
        """
        Discovers total pages from pagination and loads all chapter pages in parallel.
        """
        def extract_page_chapters(soup: BeautifulSoup) -> List[tuple]:
            res = []
            ch_links = soup.select(".list-chapter li a") or soup.select("#list-chapter a")
            for a in ch_links:
                href = a.get("href", "")
                if not href:
                    continue
                ch_url = urljoin(base_url, href)
                raw_title = a.get_text(strip=True) or a.get("title", "")
                ch_title = clean_title_str(raw_title)

                m = re.search(r"chapter\s*(\d+)", ch_title, re.I)
                if not m:
                    m = re.search(r"chapter[-_](\d+)", href, re.I)
                num = int(m.group(1)) if m else None
                res.append((num, ch_title, ch_url))
            return res

        all_raw = extract_page_chapters(main_soup)

        # Detect total pages
        max_page = 1
        for a in main_soup.select(".pagination a"):
            href = a.get("href", "")
            m = re.search(r"page=(\d+)", href)
            if m:
                p = int(m.group(1))
                if p > max_page:
                    max_page = p

        if max_page > 1:
            if on_progress:
                on_progress(f"Discovered {max_page} chapter pages. Loading in parallel...")

            def fetch_single_page(p: int):
                p_url = f"{main_url}?page={p}"
                html = self._fetch_html(p_url)
                if not html:
                    return p, []
                sp = BeautifulSoup(html, "html.parser")
                return p, extract_page_chapters(sp)

            with ThreadPoolExecutor(max_workers=min(10, max_page)) as executor:
                results = sorted(executor.map(fetch_single_page, range(2, max_page + 1)), key=lambda x: x[0])
                for p_num, p_chapters in results:
                    all_raw.extend(p_chapters)

        # Deduplicate preserving order
        seen_urls = set()
        chapter_infos: List[ChapterInfo] = []
        idx = 1
        for num, ch_title, ch_url in all_raw:
            if ch_url not in seen_urls:
                seen_urls.add(ch_url)
                ch_num = num if num is not None else idx
                chapter_infos.append(ChapterInfo(
                    index=idx,
                    number=ch_num,
                    title=ch_title or f"Chapter {ch_num}",
                    url=ch_url
                ))
                idx += 1

        if on_progress:
            on_progress(f"Found {len(chapter_infos)} chapters.")

        return chapter_infos

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one(".chapter-title") or soup.select_one("h2") or soup.select_one("h1")
        raw_title = title_el.get_text(strip=True) if title_el else ""
        title = clean_title_str(raw_title)

        m_num = re.search(r"chapter\s*(\d+)", title, re.I)
        if not m_num:
            m_num = re.search(r"chapter[-_](\d+)", url, re.I)
        num = int(m_num.group(1)) if m_num else 1

        content_div = soup.select_one("#chapter-content") or soup.select_one(".chapter-content")
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
