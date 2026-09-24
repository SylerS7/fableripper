import re
import time
import json
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY
from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .extractor import clean_chapter_soup

logger = logging.getLogger(__name__)

class UniversalScraper(BaseScraper):
    name = "Universal Reader"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def can_handle(self, url: str) -> bool:
        # Handles any HTTP/HTTPS URL as a universal fallback
        return url.startswith("http://") or url.startswith("https://")

    def parse_slug(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]
        if parts:
            clean = re.sub(r"\.(html|htm|php|aspx)$", "", parts[-1])
            clean = re.sub(r"[^\w\-]", "-", clean)
            return clean.lower() or "novel"
        return parsed.netloc.replace(".", "-")

    def _fetch_html(self, url: str) -> str:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.encoding = resp.apparent_encoding or "utf-8"
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 404:
                    return ""
            except Exception as e:
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

        # 1. Title (OG -> JSON-LD -> H1 -> Title tag)
        title = ""
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title:
            t_tag = soup.find("title")
            if t_tag:
                title = re.sub(r"\s*[-|–].*$", "", t_tag.get_text()).strip()

        title = title or slug.replace("-", " ").title()

        # 2. Author
        author = "Unknown"
        og_author = soup.find("meta", property="book:author") or soup.find("meta", attrs={"name": "author"})
        if og_author and og_author.get("content"):
            author = og_author["content"].strip()
        else:
            for el in soup.find_all(attrs={"class": re.compile(r"author|creator|writer", re.I)}):
                text = el.get_text(strip=True)
                if text and len(text) < 40 and not any(w in text.lower() for w in ["comment", "post", "date"]):
                    author = re.sub(r"^(?:by|author:)\s*", "", text, flags=re.I).strip()
                    break

        # 3. Description
        description = ""
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            description = og_desc["content"].strip()
        else:
            desc_container = soup.find(attrs={"class": re.compile(r"synopsis|summary|description|intro", re.I)})
            if desc_container:
                description = desc_container.get_text("\n\n", strip=True)

        # 4. Cover URL
        cover_url = None
        og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        if og_img and og_img.get("content"):
            cover_url = urljoin(base_url, og_img["content"].strip())
        else:
            img_tag = soup.find(attrs={"class": re.compile(r"cover|thumbnail|poster", re.I)})
            if img_tag and img_tag.name == "img":
                src = img_tag.get("src") or img_tag.get("data-src")
                if src:
                    cover_url = urljoin(base_url, src)

        # 5. Extract chapters from links
        chapters: List[ChapterInfo] = []
        seen_urls = set()

        # Find all <a> tags that look like chapters
        chapter_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            # Heuristic match: text or url contains chapter/ch/episode or number
            is_ch_text = bool(re.search(r"\b(?:chapter|ch\.|ep\.|part)\s*\d+", text, re.I))
            is_ch_url = bool(re.search(r"/(?:chapter|ch|ep)[-_]?\d+", href, re.I))

            if is_ch_text or is_ch_url:
                seen_urls.add(full_url)
                chapter_links.append((full_url, text or href))

        for idx, (ch_url, ch_title) in enumerate(chapter_links, start=1):
            m = re.search(r"(\d+)", ch_title)
            num = int(m.group(1)) if m else idx

            chapters.append(ChapterInfo(
                index=idx,
                number=num,
                title=ch_title,
                url=ch_url
            ))

        # If no chapters found in TOC, perhaps URL itself is Chapter 1
        if not chapters:
            chapters.append(ChapterInfo(
                index=1,
                number=1,
                title=title or "Chapter 1",
                url=url
            ))

        return NovelMetadata(
            title=title,
            slug=slug,
            url=url,
            platform=self.name,
            author=author,
            description=description,
            cover_url=cover_url,
            categories=[],
            chapters=chapters
        )

    def get_chapter_content(self, url: str) -> ChapterContent:
        html_doc = self._fetch_html(url)
        soup = BeautifulSoup(html_doc, "html.parser")

        # Find title
        title = ""
        h1 = soup.find("h1") or soup.find("h2")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

        m_num = re.search(r"chapter\s*(\d+)", title, re.I) if title else None
        num = int(m_num.group(1)) if m_num else 1

        # Heuristic content container selection:
        # Check standard container classes
        candidate = (
            soup.find(attrs={"class": re.compile(r"chapter-content|read-content|entry-content|post-content|text-content|reading-content|story-content", re.I)})
            or soup.find(id=re.compile(r"chapter-content|content|reading-content", re.I))
            or soup.find("article")
        )

        # Fallback: find element with the highest number of <p> tags
        if not candidate:
            best_el = None
            max_p_count = 0
            for el in soup.find_all(["div", "article", "section"]):
                p_count = len(el.find_all("p", recursive=False))
                if p_count > max_p_count:
                    max_p_count = p_count
                    best_el = el
            candidate = best_el or soup

        paragraphs = clean_chapter_soup(candidate, chapter_title=title)

        return ChapterContent(
            number=num,
            title=title or f"Chapter {num}",
            url=url,
            paragraphs=paragraphs
        )
