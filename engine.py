import time
import requests
from pathlib import Path
from typing import Optional, List, Callable, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DEFAULT_CONCURRENCY, OUTPUT_DIR
from scraper import get_scraper_for_url, NovelMetadata, ChapterInfo, ChapterContent
from storage import NovelCache
from epub import NovelExporter

class NovelPipeline:
    def __init__(
        self,
        url: str,
        concurrency: int = DEFAULT_CONCURRENCY,
        use_cache: bool = True,
        on_progress: Optional[Callable[[str, float], None]] = None
    ):
        self.url = url
        self.concurrency = concurrency
        self.use_cache = use_cache
        self.on_progress = on_progress
        self.scraper = get_scraper_for_url(url)
        self.slug = self.scraper.parse_slug(url)
        self.cache = NovelCache(self.slug)

    def _notify(self, message: str, percent: float = 0.0):
        if self.on_progress:
            self.on_progress(message, percent)

    def get_novel_info(self, force_refresh: bool = False) -> NovelMetadata:
        """
        Retrieves novel metadata either from cache or by scraping.
        """
        if self.use_cache and not force_refresh:
            cached_meta = self.cache.load_metadata()
            if cached_meta:
                # Use cache only if: same platform, has chapters, and has description
                same_platform = cached_meta.get("platform") == self.scraper.name
                has_chapters = len(cached_meta.get("chapters", [])) > 1
                has_description = bool(cached_meta.get("description", "").strip())
                if same_platform and has_chapters and has_description:
                    return NovelMetadata.from_dict(cached_meta)

        self._notify(f"Detecting platform: [{self.scraper.name}] - Fetching novel info...", 0.05)
        metadata = self.scraper.get_novel_metadata(
            self.url,
            on_progress=lambda msg: self._notify(msg, 0.1)
        )
        self.cache.save_metadata(metadata.to_dict())
        return metadata

    def download_cover(self, cover_url: Optional[str]) -> Optional[bytes]:
        if not cover_url:
            return None
        
        cached_cover_path = self.cache.get_cover_path()
        if self.use_cache and cached_cover_path:
            with open(cached_cover_path, "rb") as f:
                return f.read()

        try:
            self._notify("Downloading book cover image...", 0.15)
            session = requests.Session()
            resp = session.get(cover_url, timeout=15)
            if resp.status_code == 200:
                ext = "jpg"
                if ".png" in cover_url.lower():
                    ext = "png"
                elif ".webp" in cover_url.lower():
                    ext = "webp"
                self.cache.save_cover(resp.content, ext=ext)
                return resp.content
        except Exception as e:
            self._notify(f"Could not download cover image: {e}", 0.15)
        
        return None

    def fetch_chapter(self, ch_info: ChapterInfo) -> ChapterContent:
        if self.use_cache and self.cache.has_chapter(ch_info.number):
            cached_data = self.cache.get_chapter(ch_info.number)
            if cached_data:
                return ChapterContent.from_dict(cached_data)

        content = self.scraper.get_chapter_content(ch_info.url)
        if not content.title or content.title.strip() == "":
            content.title = ch_info.title
        self.cache.save_chapter(ch_info.number, content.to_dict())
        return content

    def run(
        self,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        output_file: Optional[str] = None,
        export_format: str = "epub",
        split_volumes: Optional[int] = None
    ) -> Union[Path, List[Path]]:
        start_time = time.time()
        self._notify(f"Initializing pipeline with {self.scraper.name}...", 0.02)

        # 1. Get metadata
        metadata = self.get_novel_info()
        all_chapters = metadata.chapters

        if not all_chapters:
            raise ValueError(f"No chapters found for novel at {self.url}")

        # 2. Filter chapters by range
        filtered_chapters: List[ChapterInfo] = []
        for ch in all_chapters:
            if start_chapter is not None and ch.number < start_chapter:
                continue
            if end_chapter is not None and ch.number > end_chapter:
                continue
            filtered_chapters.append(ch)

        if not filtered_chapters:
            raise ValueError(
                f"No chapters found within requested range: "
                f"start={start_chapter}, end={end_chapter} (Total available: {len(all_chapters)})"
            )

        total_to_download = len(filtered_chapters)
        self._notify(
            f"Selected {total_to_download} chapters "
            f"(Ch {filtered_chapters[0].number} to Ch {filtered_chapters[-1].number})",
            0.2
        )

        # 3. Download / Load cover
        cover_bytes = self.download_cover(metadata.cover_url)

        # 4. Fetch chapters (concurrency + cache)
        downloaded_chapters: List[ChapterContent] = []
        chapters_to_fetch: List[ChapterInfo] = []

        for ch in filtered_chapters:
            if self.use_cache and self.cache.has_chapter(ch.number):
                cached_data = self.cache.get_chapter(ch.number)
                if cached_data:
                    downloaded_chapters.append(ChapterContent.from_dict(cached_data))
                    continue
            chapters_to_fetch.append(ch)

        cached_count = len(downloaded_chapters)
        if cached_count > 0:
            self._notify(f"Found {cached_count} chapters already cached.", 0.25)

        if chapters_to_fetch:
            self._notify(f"Downloading {len(chapters_to_fetch)} chapters with {self.concurrency} threads...", 0.3)
            completed_count = cached_count

            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                future_to_ch = {
                    executor.submit(self.fetch_chapter, ch): ch
                    for ch in chapters_to_fetch
                }

                for future in as_completed(future_to_ch):
                    ch_info = future_to_ch[future]
                    try:
                        content = future.result()
                        downloaded_chapters.append(content)
                    except Exception as e:
                        self._notify(f"Error downloading {ch_info.title}: {e}", 0.3)
                    
                    completed_count += 1
                    percent = 0.3 + (completed_count / total_to_download) * 0.55
                    if completed_count % 10 == 0 or completed_count == total_to_download:
                        self._notify(
                            f"Downloaded chapter {completed_count}/{total_to_download}: {ch_info.title}",
                            percent
                        )

        # 5. Export
        exporter = NovelExporter(metadata, downloaded_chapters, cover_bytes)
        export_fmt = export_format.lower()

        # Handle volume splitting
        if split_volumes and split_volumes > 0:
            self._notify(f"Splitting into volumes of {split_volumes} chapters each...", 0.90)
            paths = exporter.export_volumes(
                base_output_dir=OUTPUT_DIR,
                chapters_per_volume=split_volumes,
                fmt=export_fmt,
                on_progress=lambda msg: self._notify(msg, 0.95)
            )
            elapsed = time.time() - start_time
            self._notify(f"Done in {elapsed:.1f}s! Generated {len(paths)} volumes in: {OUTPUT_DIR}", 1.0)
            return paths

        # Single file export
        safe_title = "".join(c for c in metadata.title if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")
        ext = export_fmt if export_fmt in ("epub", "txt", "md") else "epub"

        if not output_file:
            if start_chapter or end_chapter:
                first_num = filtered_chapters[0].number
                last_num = filtered_chapters[-1].number
                filename = f"{safe_title}_Ch{first_num}-{last_num}.{ext}"
            else:
                filename = f"{safe_title}.{ext}"
            out_path = OUTPUT_DIR / filename
        else:
            out_path = Path(output_file).with_suffix(f".{ext}")

        self._notify(f"Compiling into {ext.upper()} document...", 0.90)
        if ext == "epub":
            result_path = exporter.export_epub(out_path, on_progress=lambda msg: self._notify(msg, 0.95))
        elif ext == "txt":
            result_path = exporter.export_txt(out_path)
        elif ext == "md":
            result_path = exporter.export_markdown(out_path)
        else:
            result_path = exporter.export_epub(out_path, on_progress=lambda msg: self._notify(msg, 0.95))

        elapsed = time.time() - start_time
        self._notify(f"Done in {elapsed:.1f}s! Saved to: {result_path}", 1.0)
        return result_path
