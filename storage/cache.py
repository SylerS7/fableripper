import json
from pathlib import Path
from typing import Optional, Dict, Any
from config import CACHE_DIR

class NovelCache:
    def __init__(self, novel_slug: str):
        self.novel_slug = novel_slug
        self.novel_dir = CACHE_DIR / novel_slug
        self.chapters_dir = self.novel_dir / "chapters"
        self.novel_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        path = self.novel_dir / "metadata.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def load_metadata(self) -> Optional[Dict[str, Any]]:
        path = self.novel_dir / "metadata.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def save_cover(self, image_data: bytes, ext: str = "jpg") -> Path:
        cover_path = self.novel_dir / f"cover.{ext}"
        with open(cover_path, "wb") as f:
            f.write(image_data)
        return cover_path

    def get_cover_path(self) -> Optional[Path]:
        for ext in ["jpg", "jpeg", "png", "webp"]:
            p = self.novel_dir / f"cover.{ext}"
            if p.exists() and p.stat().st_size > 0:
                return p
        return None

    def save_chapter(self, chapter_num: int, chapter_data: Dict[str, Any]) -> None:
        path = self.chapters_dir / f"chapter_{chapter_num:05d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False, indent=2)

    def get_chapter(self, chapter_num: int) -> Optional[Dict[str, Any]]:
        path = self.chapters_dir / f"chapter_{chapter_num:05d}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def has_chapter(self, chapter_num: int) -> bool:
        path = self.chapters_dir / f"chapter_{chapter_num:05d}.json"
        return path.exists() and path.stat().st_size > 0

    def get_downloaded_count(self) -> int:
        return len(list(self.chapters_dir.glob("chapter_*.json")))
