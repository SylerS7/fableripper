import uuid
import html
from pathlib import Path
from typing import List, Optional, Callable
import ebooklib
from ebooklib import epub

from config import BASE_DIR
from scraper.base import NovelMetadata, ChapterContent
from scraper.extractor import paragraphs_to_xhtml

class EpubBuilder:
    def __init__(self, metadata: NovelMetadata):
        self.metadata = metadata
        self.book = epub.EpubBook()
        self.chapters_content: List[ChapterContent] = []
        self.cover_bytes: Optional[bytes] = None
        self.cover_ext: str = "jpg"
        
        # Load CSS
        css_path = BASE_DIR / "epub" / "styles.css"
        if css_path.exists():
            with open(css_path, "r", encoding="utf-8") as f:
                self.css_content = f.read()
        else:
            self.css_content = "body { font-family: serif; line-height: 1.6; padding: 2%; }"

    def set_cover_data(self, cover_bytes: bytes, ext: str = "jpg") -> None:
        self.cover_bytes = cover_bytes
        self.cover_ext = ext

    def add_chapter(self, chapter: ChapterContent) -> None:
        self.chapters_content.append(chapter)

    def set_chapters(self, chapters: List[ChapterContent]) -> None:
        self.chapters_content = sorted(chapters, key=lambda c: c.number)

    def build(self, output_path: Path, on_progress: Optional[Callable[[str], None]] = None) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if on_progress:
            on_progress("Initializing EPUB metadata...")

        # Setup metadata
        self.book.set_identifier(str(uuid.uuid4()))
        self.book.set_title(self.metadata.title)
        self.book.set_language("en")
        self.book.add_author(self.metadata.author)
        
        if self.metadata.description:
            self.book.add_metadata("DC", "description", self.metadata.description)
        for cat in self.metadata.categories:
            self.book.add_metadata("DC", "subject", cat)

        # Add CSS stylesheet
        style_item = epub.EpubItem(
            uid="style_default",
            file_name="Styles/styles.css",
            media_type="text/css",
            content=self.css_content.encode("utf-8")
        )
        self.book.add_item(style_item)

        spine = ["nav"]

        # Cover image
        if self.cover_bytes:
            if on_progress:
                on_progress("Embedding book cover...")
            cover_filename = f"cover.{self.cover_ext}"
            self.book.set_cover(cover_filename, self.cover_bytes)

        # About / Title Page
        if on_progress:
            on_progress("Generating title and overview page...")
        
        about_page = self._create_about_page(style_item)
        self.book.add_item(about_page)
        spine.append(about_page)

        # Chapters
        toc_items = [about_page]
        total = len(self.chapters_content)

        for idx, ch in enumerate(self.chapters_content, start=1):
            if on_progress and (idx % 25 == 0 or idx == total or idx == 1):
                on_progress(f"Processing chapter {idx}/{total}: {ch.title}...")

            file_name = f"Text/chapter_{ch.number:05d}.xhtml"
            ch_item = epub.EpubHtml(
                title=ch.title,
                file_name=file_name,
                lang="en"
            )
            ch_item.content = paragraphs_to_xhtml(ch.title, ch.paragraphs).encode("utf-8")
            ch_item.add_item(style_item)
            
            self.book.add_item(ch_item)
            spine.append(ch_item)
            toc_items.append(ch_item)

        # Table of Contents
        self.book.toc = tuple(toc_items)
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        self.book.spine = spine

        if on_progress:
            on_progress(f"Writing EPUB file to {output_path.name}...")

        epub.write_epub(str(output_path), self.book, {})
        
        if on_progress:
            on_progress(f"Successfully generated {output_path.name} ({len(self.chapters_content)} chapters)!")

        return output_path

    def _create_about_page(self, style_item: epub.EpubItem) -> epub.EpubHtml:
        esc_title = html.escape(self.metadata.title)
        esc_author = html.escape(self.metadata.author)
        esc_url = html.escape(self.metadata.url)
        cats_html = ", ".join(html.escape(c) for c in self.metadata.categories) if self.metadata.categories else "Uncategorized"

        # Split description paragraphs
        desc_parts = self.metadata.description.split("\n\n")
        desc_html = "\n".join(f"<p>{html.escape(p.strip())}</p>" for p in desc_parts if p.strip())

        html_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>About {esc_title}</title>
    <link rel="stylesheet" type="text/css" href="../Styles/styles.css" />
</head>
<body>
    <div class="book-info-page">
        <h1 class="book-title">{esc_title}</h1>
        <h2 class="book-author">by {esc_author}</h2>

        <div class="book-meta">
            <p><strong>Author:</strong> {esc_author}</p>
            <p><strong>Categories:</strong> {cats_html}</p>
            <p><strong>Chapters Included:</strong> {len(self.chapters_content)}</p>
            <p><strong>Source:</strong> <a href="{esc_url}">{esc_url}</a></p>
        </div>

        <div class="book-description">
            <h3>Synopsis</h3>
            {desc_html}
        </div>
    </div>
</body>
</html>"""

        about_item = epub.EpubHtml(
            title="About the Novel",
            file_name="Text/about.xhtml",
            lang="en"
        )
        about_item.content = html_content.encode("utf-8")
        about_item.add_item(style_item)
        return about_item
