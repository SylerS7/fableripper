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

class WuxiaSpotScraper(BaseScraper):
    name = "WuxiaSpot"
    BASE_URL = "https://www.wuxiaspot.com"

    def can_handle(self, url: str) -> bool:
        return "wuxiaspot.com" in url.lower()

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path
        match = re.search(r"/novel/([a-zA-Z0-9\-]+?)(?:_\d+)?(?:\.html)?$", path)
        if match:
            return match.group(1)
        slug = path.strip("/").split("/")[-1]
        slug = re.sub(r"\.html$", "", slug)
        slug = re.sub(r"_\d+$", "", slug)
        return slug

    def detect_chapter_number(self, url: str) -> Optional[int]:
        m = re.search(r"_(\d+)\.html", url)
        if m:
            return int(m.group(1))
        return None

    def _fetch_html(self, url: str) -> str:
        html, code = smart_fetch(url)
        return html if code == 200 else ""

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        req_ch = self.detect_chapter_number(url)

        main_url = f"{self.BASE_URL}/novel/{slug}.html"
        logger.info(f"Fetching metadata for novel slug: {slug}")
        
        html_doc = self._fetch_html(main_url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one("h1.novel-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        author_el = soup.select_one('span[itemprop="author"]') or soup.select_one(".author a") or soup.select_one(".author")
        author = "Unknown"
        if author_el:
            author_text = author_el.get_text(strip=True)
            author = re.sub(r"^Author:\s*", "", author_text, flags=re.I).strip()

        desc_el = soup.select_one("#info .summary .content") or soup.select_one(".summary .content")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        cover_url = None
        cover_img = soup.select_one("figure.cover img") or soup.select_one(".fixed-img img")
        if cover_img:
            src = cover_img.get("data-src") or cover_img.get("src")
            if src:
                cover_url = urljoin(self.BASE_URL, src)

        categories = []
        for cat in soup.select(".categories ul li a"):
            c_text = cat.get_text(strip=True)
            if c_text and c_text not in categories:
                categories.append(c_text)

        # Fast parallel pagination
        chapters = self._fetch_all_chapters_fast(slug, soup, on_progress=on_progress)

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

    def _fetch_all_chapters_fast(self, slug: str, main_soup: BeautifulSoup, on_progress=None) -> List[ChapterInfo]:
        """
        Discovers total pages from main page pagination and loads all chapter pages concurrently.
        """
        max_page = 0
        for a in main_soup.select(".pagination a"):
            m = re.search(r"page=(\d+)", a.get("href", ""))
            if m:
                p_num = int(m.group(1))
                if p_num > max_page:
                    max_page = p_num

        def extract_page_chapters(html: str) -> List[tuple]:
            res = []
            if not html:
                return res
            s = BeautifulSoup(html, "html.parser")
            items = s.select(".chapter-list li a") or s.select("ul.chapter-list a")
            for item in items:
                href = item.get("href", "")
                if not href:
                    continue
                full_url = urljoin(self.BASE_URL, href)
                title_el = item.select_one(".chapter-title") or item.select_one("strong")
                title = title_el.get_text(strip=True) if title_el else item.get("title") or item.get_text(strip=True)
                
                ch_no_el = item.select_one(".chapter-no") or item.select_one("span")
                num = None
                if ch_no_el:
                    m = re.search(r"(\d+)", ch_no_el.get_text())
                    if m:
                        num = int(m.group(1))
                if num is None:
                    m = re.search(r"_(\d+)\.html", href)
                    if m:
                        num = int(m.group(1))
                res.append((num or 0, clean_title_str(title) or title, full_url))
            return res

        all_raw = []
        if max_page == 0:
            # Fallback single page
            p0_url = f"{self.BASE_URL}/e/extend/fy.php?page=0&wjm={slug}"
            all_raw = extract_page_chapters(self._fetch_html(p0_url))
        else:
            if on_progress:
                on_progress(f"Discovered {max_page + 1} chapter pages. Loading in parallel...")

            def fetch_single_page(p: int):
                url = f"{self.BASE_URL}/e/extend/fy.php?page={p}&wjm={slug}"
                return extract_page_chapters(self._fetch_html(url))

            with ThreadPoolExecutor(max_workers=min(12, max_page + 1)) as executor:
                for page_res in executor.map(fetch_single_page, range(0, max_page + 1)):
                    all_raw.extend(page_res)

        unique = {}
        for num, title, url in all_raw:
            if num not in unique:
                unique[num] = (num, title, url)

        sorted_chapters = []
        for idx, (num, title, url) in enumerate(sorted(unique.values(), key=lambda x: x[0]), start=1):
            ch_num = num if num > 0 else idx
            sorted_chapters.append(ChapterInfo(
                index=idx,
                number=ch_num,
                title=title or f"Chapter {ch_num}",
                url=url
            ))

        return sorted_chapters

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        title_el = soup.select_one(".chapter-header h2") or soup.select_one("h2") or soup.select_one("h1")
        raw_title = title_el.get_text(strip=True) if title_el else ""
        title = clean_title_str(raw_title)

        m_num = re.search(r"_(\d+)\.html", url)
        num = int(m_num.group(1)) if m_num else 0

        content_div = soup.select_one(".chapter-content") or soup.select_one("#chapter-content")
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
