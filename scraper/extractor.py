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

def clean_title_str(text: str) -> str:
    """
    Cleans chapter/novel titles by unescaping multiple passes (e.g. &amp;#39; -> &#39; -> '),
    stripping zero-width characters, normalizing whitespace, and removing HTML tags.
    """
    if not text:
        return ""
    # Strip any stray HTML tags in title
    text = re.sub(r"<[^>]+>", "", text)
    # Strip BOM, zero-width spaces, and non-breaking spaces
    text = (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u200e", "")
        .replace("\u200f", "")
        .replace("\xa0", " ")
    )
    # Multi-pass unescape to handle double-encoded entities like &amp;#39; or &amp;quot;
    prev = ""
    iterations = 0
    while text != prev and iterations < 5:
        prev = text
        text = html.unescape(text)
        iterations += 1

    # Remove invisible control chars
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def clean_text_line(text: str) -> str:
    """
    Cleans paragraph content lines by multi-pass unescaping and removing invisible characters.
    """
    if not text:
        return ""
    text = (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u200e", "")
        .replace("\u200f", "")
        .replace("\xa0", " ")
    )
    # Multi-pass unescape
    prev = ""
    iterations = 0
    while text != prev and iterations < 5:
        prev = text
        text = html.unescape(text)
        iterations += 1

    # Remove control characters (preserve standard whitespace and newlines)
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
    for ad_el in soup.find_all(attrs={"class": re.compile(r"ad|advertisement|banner|social|comments", re.I)}):
        ad_el.decompose()
    for ad_el in soup.find_all(attrs={"id": re.compile(r"ad|advertisement|banner|comments", re.I)}):
        ad_el.decompose()

    paragraphs = []
    
    p_tags = soup.find_all("p")
    if p_tags:
        for p in p_tags:
            text = clean_text_line(p.get_text())
            if not text:
                continue
            if any(pattern.search(text) for pattern in BOILERPLATE_PATTERNS):
                continue
            paragraphs.append(text)
    else:
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

    # Avoid repeating the chapter title if the first paragraph is an identical title header
    clean_ch_title = clean_title_str(chapter_title)
    if paragraphs and clean_ch_title:
        norm_first = re.sub(r"[^\w]", "", paragraphs[0].lower())
        norm_title = re.sub(r"[^\w]", "", clean_ch_title.lower())
        if norm_first and (norm_first == norm_title or norm_first in norm_title or norm_title in norm_first):
            paragraphs.pop(0)

    return paragraphs

def paragraphs_to_xhtml(title: str, paragraphs: List[str]) -> str:
    """
    Renders clean chapter title and paragraphs into valid EPUB XHTML body.
    """
    clean_title = clean_title_str(title)
    escaped_title = html.escape(clean_title)
    body_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
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
        # Multi-pass clean and escape for XHTML
        clean_p = clean_text_line(p)
        escaped_p = html.escape(clean_p)
        body_parts.append(f'<p>{escaped_p}</p>')
    
    body_parts.append('</div>')
    body_parts.append('</body>')
    body_parts.append('</html>')
    return "\n".join(body_parts)
