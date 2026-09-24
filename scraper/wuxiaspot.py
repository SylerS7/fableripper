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

class WuxiaSpotScraper(BaseScraper):
    name = "WuxiaSpot"
    BASE_URL = "https://www.wuxiaspot.com"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def can_handle(self, url: str) -> bool:
        return "wuxiaspot.com" in url.lower()

    def parse_slug(self, url: str) -> str:
        """
        Extracts novel slug from URL.
        e.g. https://www.wuxiaspot.com/novel/battle-through-the-heavens.html -> battle-through-the-heavens
        e.g. https://www.wuxiaspot.com/novel/battle-through-the-heavens_10.html -> battle-through-the-heavens
        """
        path = urlparse(url).path
        # Match /novel/{slug}.html or /novel/{slug}_{chapter}.html
        match = re.search(r"/novel/([a-zA-Z0-9\-]+?)(?:_\d+)?(?:\.html)?$", path)
        if match:
            return match.group(1)
        # Fallback to last path segment stripped of extension
        slug = path.strip("/").split("/")[-1]
        slug = re.sub(r"\.html$", "", slug)
        slug = re.sub(r"_\d+$", "", slug)
        return slug

    def _fetch_html(self, url: str) -> str:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.encoding = "utf-8"
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 404:
                    logger.warning(f"404 Not Found: {url}")
                    return ""
                else:
                    logger.warning(f"HTTP {resp.status_code} for {url} (attempt {attempt}/{MAX_RETRIES})")
            except requests.RequestException as e:
                logger.warning(f"Request error for {url}: {e} (attempt {attempt}/{MAX_RETRIES})")
            
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
        
        raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts.")

    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        slug = self.parse_slug(url)
        main_url = f"{self.BASE_URL}/novel/{slug}.html"
        logger.info(f"Fetching metadata for novel slug: {slug}")
        
        html_doc = self._fetch_html(main_url)
        soup = BeautifulSoup(html_doc, "html.parser")

        # 1. Title
        title_el = soup.select_one("h1.novel-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug.replace("-", " ").title()

        # 2. Author
        author_el = soup.select_one('span[itemprop="author"]') or soup.select_one(".author a") or soup.select_one(".author")
        author = "Unknown"
        if author_el:
            author_text = author_el.get_text(strip=True)
            # Remove "Author:" prefix if present
            author = re.sub(r"^Author:\s*", "", author_text, flags=re.I).strip()

        # 3. Description
        desc_el = soup.select_one("#info .summary .content") or soup.select_one(".summary .content")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else ""

        # 4. Cover URL
        cover_url = None
        cover_img = soup.select_one("figure.cover img") or soup.select_one(".fixed-img img")
        if cover_img:
            src = cover_img.get("data-src") or cover_img.get("src")
            if src:
                cover_url = urljoin(self.BASE_URL, src)

        # 5. Categories / Genres
        categories = []
        for cat in soup.select(".categories ul li a"):
            c_text = cat.get_text(strip=True)
            if c_text and c_text not in categories:
                categories.append(c_text)

        # 6. Chapters list via pagination
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
            chapters=chapters
        )

    def _fetch_all_chapters(self, slug: str, on_progress=None) -> List[ChapterInfo]:
        """
        Paginates through /e/extend/fy.php?page={page}&wjm={slug} to extract all chapters.
        """
        chapters: List[ChapterInfo] = []
        page = 0
        consecutive_empty = 0

        while True:
            fy_url = f"{self.BASE_URL}/e/extend/fy.php?page={page}&wjm={slug}"
            try:
                html_doc = self._fetch_html(fy_url)
            except Exception as e:
                logger.error(f"Error fetching chapter page {page}: {e}")
                break

            if not html_doc or len(html_doc.strip()) == 0:
                break

            soup = BeautifulSoup(html_doc, "html.parser")
            items = soup.select(".chapter-list li a")
            if not items:
                # Sometimes wuxiaspot has alternative markup
                items = soup.select("ul.chapter-list a")

            if not items:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                page += 1
                continue

            consecutive_empty = 0
            for item in items:
                href = item.get("href", "")
                if not href:
                    continue
                full_url = urljoin(self.BASE_URL, href)
                
                # Extract chapter title
                title_el = item.select_one(".chapter-title") or item.select_one("strong")
                title = title_el.get_text(strip=True) if title_el else item.get("title") or item.get_text(strip=True)
                
                # Extract chapter number
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
                    else:
                        m_title = re.search(r"chapter\s*(\d+)", title, re.I)
                        if m_title:
                            num = int(m_title.group(1))
                        else:
                            num = len(chapters) + 1

                chapters.append(ChapterInfo(
                    index=len(chapters) + 1,
                    number=num,
                    title=title,
                    url=full_url
                ))

            if on_progress:
                on_progress(f"Discovered {len(chapters)} chapters (page {page + 1})...")

            # Check if this was the last page
            # If the page returned fewer than 100 chapters (typically each page is 100 chapters), it's the last page.
            if len(items) < 100:
                break

            page += 1

        # Deduplicate and sort chapters by number
        unique_chapters: Dict[int, ChapterInfo] = {}
        for ch in chapters:
            if ch.number not in unique_chapters:
                unique_chapters[ch.number] = ch

        sorted_chapters = sorted(unique_chapters.values(), key=lambda c: c.number)
        # Re-index 1..N
        for idx, ch in enumerate(sorted_chapters, start=1):
            ch.index = idx

        return sorted_chapters

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        # Chapter title
        title_el = soup.select_one(".chapter-header h2") or soup.select_one("h2") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # Chapter number from URL or title
        m_num = re.search(r"_(\d+)\.html", url)
        num = int(m_num.group(1)) if m_num else 0

        # Chapter text container
        content_div = soup.select_one(".chapter-content") or soup.select_one("#chapter-content")
        paragraphs = clean_chapter_soup(content_div, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
