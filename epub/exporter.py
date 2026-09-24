from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
from scraper.base import NovelMetadata, ChapterContent
from scraper.extractor import clean_title_str, clean_text_line
from .builder import EpubBuilder

class NovelExporter:
    def __init__(self, metadata: NovelMetadata, chapters: List[ChapterContent], cover_bytes: Optional[bytes] = None):
        self.metadata = metadata
        self.chapters = sorted(chapters, key=lambda c: c.number)
        self.cover_bytes = cover_bytes

    def export_epub(self, output_path: Path, on_progress: Optional[Callable[[str], None]] = None) -> Path:
        builder = EpubBuilder(self.metadata)
        if self.cover_bytes:
            ext = "png" if self.metadata.cover_url and ".png" in self.metadata.cover_url.lower() else "jpg"
            builder.set_cover_data(self.cover_bytes, ext=ext)
        builder.set_chapters(self.chapters)
        return builder.build(output_path, on_progress=on_progress)

    def export_txt(self, output_path: Path) -> Path:
        output_path = Path(output_path).with_suffix(".txt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"Title: {self.metadata.title}",
            f"Author: {self.metadata.author}",
            f"Source: {self.metadata.url}",
            f"Platform: {self.metadata.platform}",
            f"Chapters: {len(self.chapters)}",
            "=" * 60,
            "SYNOPSIS",
            "=" * 60,
            self.metadata.description or "No description.",
            "\n" + "=" * 60,
            "TABLE OF CONTENTS",
            "=" * 60,
        ]

        for ch in self.chapters:
            lines.append(f"- {clean_title_str(ch.title)}")

        lines.append("\n" + "=" * 60)
        lines.append("CONTENT")
        lines.append("=" * 60 + "\n")

        for ch in self.chapters:
            c_title = clean_title_str(ch.title)
            lines.append(f"\n\n{'#' * 40}")
            lines.append(f"{c_title}")
            lines.append(f"{'#' * 40}\n")
            for p in ch.paragraphs:
                lines.append(clean_text_line(p) + "\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def export_markdown(self, output_path: Path) -> Path:
        output_path = Path(output_path).with_suffix(".md")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {self.metadata.title}",
            f"**Author:** {self.metadata.author}  ",
            f"**Platform:** {self.metadata.platform}  ",
            f"**Source:** [{self.metadata.url}]({self.metadata.url})  ",
            f"**Categories:** {', '.join(self.metadata.categories) if self.metadata.categories else 'None'}  ",
            "",
            "## Synopsis",
            "",
            self.metadata.description or "No description.",
            "",
            "---",
            "",
            "## Table of Contents",
            "",
        ]

        for idx, ch in enumerate(self.chapters, start=1):
            anchor = f"chapter-{ch.number}"
            lines.append(f"{idx}. [{clean_title_str(ch.title)}](#{anchor})")

        lines.append("\n---\n")

        for ch in self.chapters:
            anchor = f"chapter-{ch.number}"
            c_title = clean_title_str(ch.title)
            lines.append(f'<a id="{anchor}"></a>')
            lines.append(f"## {c_title}\n")
            for p in ch.paragraphs:
                lines.append(clean_text_line(p) + "\n")
            lines.append("\n---\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def export_volumes(
        self,
        base_output_dir: Path,
        chapters_per_volume: int = 100,
        fmt: str = "epub",
        on_progress: Optional[Callable[[str], None]] = None
    ) -> List[Path]:
        """
        Splits chapters into multiple volumes to prevent e-reader memory overload.
        """
        base_output_dir = Path(base_output_dir)
        base_output_dir.mkdir(parents=True, exist_ok=True)

        safe_title = "".join(c for c in self.metadata.title if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")
        results = []

        total_volumes = (len(self.chapters) + chapters_per_volume - 1) // chapters_per_volume

        for v_idx in range(total_volumes):
            start_i = v_idx * chapters_per_volume
            end_i = min((v_idx + 1) * chapters_per_volume, len(self.chapters))
            volume_chapters = self.chapters[start_i:end_i]
            first_ch = volume_chapters[0].number
            last_ch = volume_chapters[-1].number

            vol_num = v_idx + 1
            filename = f"{safe_title}_Vol{vol_num:02d}_Ch{first_ch}-{last_ch}.{fmt}"
            out_file = base_output_dir / filename

            if on_progress:
                on_progress(f"Building Volume {vol_num}/{total_volumes} (Ch {first_ch} to {last_ch})...")

            exporter = NovelExporter(self.metadata, volume_chapters, self.cover_bytes)
            if fmt == "epub":
                path = exporter.export_epub(out_file)
            elif fmt == "txt":
                path = exporter.export_txt(out_file)
            elif fmt == "md":
                path = exporter.export_markdown(out_file)
            else:
                path = exporter.export_epub(out_file)

            results.append(path)

        return results
