import re
import json
import logging
from urllib.parse import urljoin, urlparse, urlunparse
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from scraper.extractor import clean_chapter_soup, clean_title_str
from scraper.fetcher import smart_fetch

logger = logging.getLogger(__name__)

class WuxiaWorldScraper(BaseScraper):
    name = "WuxiaWorld"
    BASE_URL = "https://www.wuxiaworld.com"
    LITE_BASE_URL = "https://lite.wuxiaworld.com"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        return "wuxiaworld.com" in low and "wuxiaspot.com" not in low

    def parse_slug(self, url: str) -> str:
        path = urlparse(url).path
        m = re.search(r"/novel/([a-zA-Z0-9\-]+)", path)
        if m:
            return m.group(1)
        parts = [p for p in path.strip("/").split("/") if p]
        if parts:
            return parts[-1]
        return "novel"

    def detect_chapter_number(self, url: str) -> Optional[int]:
        m = re.search(r"(?:chapter|ch)[-_](\d+)", url, re.I)
        if m:
            return int(m.group(1))
        return None

    def _to_lite_url(self, url: str) -> str:
        p = urlparse(url)
        return urlunparse(p._replace(netloc="lite.wuxiaworld.com"))

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
        lite_url = f"{self.LITE_BASE_URL}/novel/{slug}"

        if on_progress:
            on_progress(f"Fetching novel metadata for {slug}...")

        # 1. Fetch metadata from main site (has full JSON-LD schema with author, cover, etc.)
        html_main = self._fetch_html(main_url)
        soup_main = BeautifulSoup(html_main, "html.parser") if html_main else None

        title = slug.replace("-", " ").title()
        author = "Unknown"
        description = ""
        cover_url = None
        categories = []

        if soup_main:
            # Check JSON-LD
            for s in soup_main.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string)
                    if isinstance(data, dict):
                        if not title or title == slug.replace("-", " ").title():
                            title = data.get("name") or data.get("headline") or title
                        if author == "Unknown":
                            auth = data.get("author")
                            if isinstance(auth, dict) and auth.get("name"):
                                author = auth["name"]
                            elif isinstance(auth, str):
                                author = auth
                        if not description:
                            description = data.get("description", "")
                        if not cover_url:
                            img = data.get("image")
                            if isinstance(img, dict) and img.get("url"):
                                cover_url = img["url"]
                            elif isinstance(img, list) and img:
                                cover_url = img[0]
                            elif isinstance(img, str):
                                cover_url = img
                except Exception:
                    pass

            # Meta tags fallback
            if not cover_url:
                og_img = soup_main.find("meta", property="og:image") or soup_main.find("meta", attrs={"name": "twitter:image"})
                if og_img and og_img.get("content"):
                    cover_url = og_img["content"]

            if not description:
                og_desc = soup_main.find("meta", property="og:description") or soup_main.find("meta", attrs={"name": "description"})
                if og_desc and og_desc.get("content"):
                    description = og_desc["content"]

            kw_meta = soup_main.find("meta", attrs={"name": "keywords"})
            if kw_meta and kw_meta.get("content"):
                kws = [k.strip() for k in kw_meta["content"].split(",") if k.strip()]
                categories = [k for k in kws if k.lower() not in ["wuxiaworld", "chinese webnovel", slug.lower()]]

        # Fallback to Lite page if main page failed
        if not soup_main or not title:
            html_lite = self._fetch_html(lite_url)
            soup_lite = BeautifulSoup(html_lite, "html.parser") if html_lite else None
            if soup_lite:
                h1 = soup_lite.find("h1")
                if h1:
                    title = clean_title_str(h1.get_text(strip=True))
                desc_meta = soup_lite.find("meta", attrs={"name": "description"})
                if desc_meta and desc_meta.get("content") and not description:
                    description = desc_meta["content"]

        # Clean title
        title = clean_title_str(title)
        if title.lower().endswith("wuxiaworld"):
            title = re.sub(r"\s*\|\s*wuxiaworld\s*$", "", title, flags=re.I).strip()

        # 2. Fetch all chapters fast via Lite TOC pages
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
        Discovers all chapters using the lightweight, server-rendered Lite TOC pages.
        Fetches pages concurrently in batches of 5.
        """
        def fetch_toc_page(page: int):
            url = f"{self.LITE_BASE_URL}/novel/{slug}?toc={page}"
            html = self._fetch_html(url)
            if not html:
                return page, [], False

            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=True)
            ch_list = []
            novel_path = f"/novel/{slug}/"

            for a in links:
                href = a["href"]
                raw_text = a.get_text(strip=True)
                if novel_path in href and raw_text.lower() != "start reading":
                    full_ch_url = urljoin(self.LITE_BASE_URL, href)
                    num_match = re.search(r"chapter[-_](\d+)", href, re.I)
                    num = int(num_match.group(1)) if num_match else None
                    ch_title = clean_title_str(raw_text)
                    ch_list.append((num, ch_title, full_ch_url))

            has_next = bool(soup.find("a", string=re.compile(r"Next", re.I)))
            return page, ch_list, has_next

        if on_progress:
            on_progress("Loading table of contents...")

        # Fetch page 1
        p1_num, p1_links, p1_has_next = fetch_toc_page(1)
        all_raw = list(p1_links)

        if p1_has_next:
            current_page = 2
            while True:
                batch_pages = list(range(current_page, current_page + 5))
                with ThreadPoolExecutor(max_workers=5) as executor:
                    batch_results = sorted(executor.map(fetch_toc_page, batch_pages), key=lambda x: x[0])

                should_stop = False
                for p_num, p_links, p_next in batch_results:
                    if p_links:
                        all_raw.extend(p_links)
                    if not p_next or not p_links:
                        should_stop = True
                        break

                if should_stop:
                    break
                current_page += 5

        # Deduplicate preserving order
        seen_urls = set()
        unique = []
        for num, ch_title, ch_url in all_raw:
            if ch_url not in seen_urls:
                seen_urls.add(ch_url)
                unique.append((num, ch_title, ch_url))

        # Sort chapters cleanly
        # In Wuxiaworld, chapter 0 (prologue) comes first, then 1, 2, ...
        def sort_key(item):
            num = item[0]
            return num if num is not None else 999999

        sorted_items = sorted(unique, key=sort_key)

        chapter_infos = []
        for idx, (num, ch_title, ch_url) in enumerate(sorted_items, start=1):
            ch_num = num if num is not None else idx
            final_title = ch_title or f"Chapter {ch_num}"
            chapter_infos.append(ChapterInfo(
                index=idx,
                number=ch_num,
                title=final_title,
                url=ch_url
            ))

        if on_progress:
            on_progress(f"Found {len(chapter_infos)} chapters.")

        return chapter_infos

    def get_chapter_content(self, url: str) -> ChapterContent:
        slug = self.parse_slug(url)
        lite_url = self._to_lite_url(url)
        html_doc = self._fetch_html(lite_url)
        if not html_doc:
            html_doc = self._fetch_html(url)

        soup = BeautifulSoup(html_doc, "html.parser")

        # Extract title
        heading = soup.select_one("h1") or soup.select_one("h2")
        title = clean_title_str(heading.get_text(strip=True)) if heading else ""

        # Chapter number
        num = self.detect_chapter_number(url) or self.detect_chapter_number(lite_url) or 0

        # Chapter body
        body_div = (
            soup.select_one(".chapter-body")
            or soup.select_one(".chapter-content")
            or soup.select_one("#chapter-content")
            or soup.select_one(".wrap")
        )

        paragraphs = clean_chapter_soup(body_div, chapter_title=title)

        # Check if the chapter is paywalled / truncated on Wuxiaworld
        # Wuxiaworld truncates locked chapters to ~8-12 preview paragraphs,
        # often ending with "..." or cut off abruptly.
        is_truncated = False
        if len(paragraphs) <= 15:
            if not paragraphs or paragraphs[-1].strip().endswith("...") or len(paragraphs) < 14:
                is_truncated = True

        # If locked or truncated on Wuxiaworld, automatically retrieve the complete untruncated chapter
        # from the complete mirror archive so the user gets the full story.
        if is_truncated and slug:
            # Map chapter number/index to mirror URL
            # Note: Wuxiaworld has pw-chapter-0 as prologue (mirror chapter-1), pw-chapter-1 as ch 1 (mirror chapter-2), etc.
            mirror_idx = num + 1 if num is not None else None
            mirror_candidates = []
            if mirror_idx:
                mirror_candidates.append(f"https://freewebnovel.com/novel/{slug}/chapter-{mirror_idx}")
            if num:
                mirror_candidates.append(f"https://freewebnovel.com/novel/{slug}/chapter-{num}")

            for m_url in mirror_candidates:
                m_html = self._fetch_html(m_url)
                if m_html:
                    m_soup = BeautifulSoup(m_html, "html.parser")
                    m_txt = m_soup.select_one("div.txt") or m_soup.select_one("#chapter-content") or m_soup.select_one(".chapter-content")
                    if m_txt:
                        m_paras = clean_chapter_soup(m_txt, chapter_title=title)
                        if len(m_paras) > len(paragraphs):
                            paragraphs = m_paras
                            logger.info(f"Retrieved complete chapter {num} ({len(paragraphs)} paragraphs) via unpaywalled archive")
                            break

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
