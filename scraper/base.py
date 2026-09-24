from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ChapterInfo:
    index: int
    number: int
    title: str
    url: str

@dataclass
class NovelMetadata:
    title: str
    slug: str
    url: str
    platform: str = "Generic Web"
    author: str = "Unknown"
    description: str = ""
    cover_url: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    chapters: List[ChapterInfo] = field(default_factory=list)
    requested_chapter: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "slug": self.slug,
            "url": self.url,
            "platform": self.platform,
            "author": self.author,
            "description": self.description,
            "cover_url": self.cover_url,
            "categories": self.categories,
            "requested_chapter": self.requested_chapter,
            "chapters": [
                {
                    "index": ch.index,
                    "number": ch.number,
                    "title": ch.title,
                    "url": ch.url
                }
                for ch in self.chapters
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NovelMetadata":
        chapters = [
            ChapterInfo(
                index=ch["index"],
                number=ch["number"],
                title=ch["title"],
                url=ch["url"]
            )
            for ch in data.get("chapters", [])
        ]
        return cls(
            title=data.get("title", ""),
            slug=data.get("slug", ""),
            url=data.get("url", ""),
            platform=data.get("platform", "Generic Web"),
            author=data.get("author", "Unknown"),
            description=data.get("description", ""),
            cover_url=data.get("cover_url"),
            categories=data.get("categories", []),
            requested_chapter=data.get("requested_chapter"),
            chapters=chapters
        )

@dataclass
class ChapterContent:
    number: int
    title: str
    url: str
    paragraphs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "paragraphs": self.paragraphs
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterContent":
        return cls(
            number=data["number"],
            title=data["title"],
            url=data["url"],
            paragraphs=data.get("paragraphs", [])
        )

class BaseScraper(ABC):
    name: str = "BaseScraper"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        pass

    @abstractmethod
    def parse_slug(self, url: str) -> str:
        pass

    @abstractmethod
    def get_novel_metadata(self, url: str, on_progress=None) -> NovelMetadata:
        pass

    @abstractmethod
    def get_chapter_content(self, url: str) -> ChapterContent:
        pass
