import re
import html
from bs4 import BeautifulSoup
from typing import List

# Patterns to remove from chapter text (ad notices, watermark strings, etc.)
BOILERPLATE_PATTERNS = [
    re.compile(r"if you find any errors.*?please let us know.*", re.IGNORECASE),
    re.compile(r"read (?:novel|latest chapters) at.*", re.IGNORECASE),
    re.compile(r"please report (?:broken links|errors).*", re.IGNORECASE),
    re.compile(r"^find authorized novels in webnovel.*", re.IGNORECASE),
]

def clean_text_line(text: str) -> str:
    # Strip BOM and zero-width spaces
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200e", "").replace("\u200f", "")
    text = html.unescape(text)
    # Remove invisible control chars (preserve standard whitespace and newlines)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()

def clean_chapter_soup(soup: BeautifulSoup, chapter_title: str = "") -> List[str]:
    """
    Extracts clean list of paragraph strings from BeautifulSoup container.
    """
    if not soup:
        return []

    # Remove unwanted tags
    for tag in soup(["script", "style", "iframe", "noscript", "svg", "input", "button", "ins"]):
        tag.decompose()

    # Remove advertising divs and containers
    for ad_el in soup.find_all(attrs={"class": re.compile(r"ad|advertisement|banner|social", re.I)}):
        ad_el.decompose()
    for ad_el in soup.find_all(attrs={"id": re.compile(r"ad|advertisement|banner", re.I)}):
        ad_el.decompose()

    paragraphs = []
    
    # Check if there are <p> elements
    p_tags = soup.find_all("p")
    if p_tags:
        for p in p_tags:
            text = clean_text_line(p.get_text())
            if not text:
                continue
            
            # Check for boilerplate
            if any(pattern.search(text) for pattern in BOILERPLATE_PATTERNS):
                continue

            paragraphs.append(text)
    else:
        # Fallback if no <p> tags: split by <br> or double newlines
        for br in soup.find_all("br"):
            br.replace_with("\n")
        raw_text = soup.get_text()
        for line in raw_text.split("\n"):
            line = clean_text_line(line)
            if not line:
                continue
            if any(pattern.search(line) for pattern in BOILERPLATE_PATTERNS):
                continue
            paragraphs.append(line)

    # If first paragraph is just a duplicate of the chapter title, we can skip it to avoid repeating in <h1> and <p>
    if paragraphs and chapter_title:
        norm_first = re.sub(r"[^\w]", "", paragraphs[0].lower())
        norm_title = re.sub(r"[^\w]", "", chapter_title.lower())
        if norm_first and (norm_first == norm_title or norm_first in norm_title or norm_title in norm_first):
            paragraphs.pop(0)

    return paragraphs

def paragraphs_to_xhtml(title: str, paragraphs: List[str]) -> str:
    """
    Renders chapter title and paragraphs into valid EPUB XHTML body.
    """
    escaped_title = html.escape(title)
    body_parts = [
        f'<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE html>',
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">',
        '<head>',
        f'<title>{escaped_title}</title>',
        '<link rel="stylesheet" type="text/css" href="../Styles/styles.css" />',
        '</head>',
        '<body>',
        f'<h1 class="chapter-title">{escaped_title}</h1>',
        '<div class="chapter-content">'
    ]
    for p in paragraphs:
        escaped_p = html.escape(p)
        body_parts.append(f'<p>{escaped_p}</p>')
    
    body_parts.append('</div>')
    body_parts.append('</body>')
    body_parts.append('</html>')
    return "\n".join(body_parts)
