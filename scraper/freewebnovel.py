import re
import json
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from scraper.extractor import clean_chapter_soup, clean_title_str
from scraper.fetcher import smart_fetch

logger = logging.getLogger(__name__)

class FreeWebNovelScraper(BaseScraper):
    name = "FreeWebNovel"
    BASE_URL = "https://freewebnovel.com"

    def can_handle(self, url: str) -> bool:
        return "freewebnovel.com" in url.lower()

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path
        m = re.search(r"/novel/([a-zA-Z0-9\-]+)", path)
        if m:
            return m.group(1)
        parts = [p for p in path.strip("/").split("/") if p]
        if parts:
            slug = parts[-1]
            slug = re.sub(r"\.html$", "", slug)
            return slug
        return "novel"

    def detect_chapter_number(self, url: str) -> Optional[int]:
        m = re.search(r"(?:chapter|ch)[-_](\d+)", url, re.I)
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
        main_url = f"{self.BASE_URL}/novel/{slug}"

        if on_progress:
            on_progress(f"Fetching novel metadata for {slug}...")

        html = self._fetch_html(main_url)
        soup = BeautifulSoup(html, "html.parser") if html else None

        title = slug.replace("-", " ").title()
        author = "Unknown"
        description = ""
        cover_url = None
        categories = []

        if soup:
            # Title
            h1 = soup.find("h1") or soup.find("h2")
            if h1:
                title = clean_title_str(h1.get_text(strip=True))

            # JSON-LD
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string)
                    if isinstance(data, dict):
                        auth = data.get("author")
                        if isinstance(auth, list) and auth:
                            author = auth[0].get("name", author) if isinstance(auth[0], dict) else str(auth[0])
                        elif isinstance(auth, dict):
                            author = auth.get("name", author)
                        elif isinstance(auth, str):
                            author = auth
                        if not cover_url and data.get("image"):
                            cover_url = data["image"]
                        if not description and data.get("description"):
                            description = data["description"]
                except Exception:
                    pass

            if not cover_url:
                img_el = soup.select_one(".pic img") or soup.select_one(".book-img img")
                if img_el:
                    cover_url = urljoin(self.BASE_URL, img_el.get("src") or img_el.get("data-src", ""))

            if not description:
                desc_el = soup.select_one(".m-desc .txt") or soup.select_one(".description")
                if desc_el:
                    description = desc_el.get_text("\n\n", strip=True)

            for cat_a in soup.select(".m-tags a, .genres a"):
                c_text = cat_a.get_text(strip=True)
                if c_text and c_text not in categories:
                    categories.append(c_text)

        # Clean title
        title = clean_title_str(title)
        title = re.sub(r"\s+Novel\s*$", "", title, flags=re.I).strip()

        chapters = self._fetch_all_chapters(slug, on_progress=on_progress)

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

    def _fetch_all_chapters(self, slug: str, on_progress=None) -> List[ChapterInfo]:
        """
        Fetches all chapters using FreeWebNovel's JSON chapter pagination API.
        Uses moderate concurrency (max_workers=2) to respect their rate limits.
        """
        first_page_url = f"{self.BASE_URL}/novel/{slug}?ajax=chapters&page=1&pageSize=100"
        first_resp = self._fetch_html(first_page_url)

        total_pages = 1
        all_raw = []

        if first_resp:
            try:
                data = json.loads(first_resp)
                total_pages = int(data.get("totalPage", 1))
                all_raw.extend(self._parse_chapters_html(data.get("html", ""), slug))
            except Exception as e:
                logger.warning(f"Error parsing page 1: {e}")

        if total_pages > 1:
            if on_progress:
                on_progress(f"Loading {total_pages} chapter pages...")

            def fetch_page(p: int):
                url = f"{self.BASE_URL}/novel/{slug}?ajax=chapters&page={p}&pageSize=100"
                resp = self._fetch_html(url)
                if not resp:
                    return p, []
                try:
                    d = json.loads(resp)
                    return p, self._parse_chapters_html(d.get("html", ""), slug)
                except Exception:
                    return p, []

            # 2 workers to avoid 429
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = sorted(executor.map(fetch_page, range(2, total_pages + 1)), key=lambda x: x[0])
                for p_num, p_chapters in results:
                    all_raw.extend(p_chapters)

        # Deduplicate
        seen_urls = set()
        chapter_infos = []
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

    def _parse_chapters_html(self, html_snippet: str, slug: str) -> List[tuple]:
        if not html_snippet:
            return []
        soup = BeautifulSoup(html_snippet, "html.parser")
        res = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            raw_title = clean_title_str(a.get_text(strip=True))
            full_url = urljoin(self.BASE_URL, href)
            m = re.search(r"chapter[-_](\d+)", href, re.I)
            num = int(m.group(1)) if m else None
            res.append((num, raw_title, full_url))
        return res

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        h1 = soup.select_one("h1") or soup.select_one("h2")
        title = clean_title_str(h1.get_text(strip=True)) if h1 else ""

        num = self.detect_chapter_number(url) or 0

        txt_div = (
            soup.select_one("div.txt")
            or soup.select_one("#chapter-content")
            or soup.select_one(".chapter-content")
            or soup.select_one("div.content")
        )

        paragraphs = clean_chapter_soup(txt_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
