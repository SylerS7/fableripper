from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .fetcher import BotProtectionError, smart_fetch
from .wuxiaworld import WuxiaWorldScraper
from .freewebnovel import FreeWebNovelScraper
from .wuxiaspot import WuxiaSpotScraper
from .royalroad import RoyalRoadScraper
from .novelfull import NovelFullScraper
from .novelfire import NovelFireScraper
from .universal import UniversalScraper
from typing import List

# Scrapers in priority order (specific platforms first, universal fallback last)
SCRAPERS: List[BaseScraper] = [
    WuxiaWorldScraper(),
    FreeWebNovelScraper(),
    WuxiaSpotScraper(),
    RoyalRoadScraper(),
    NovelFullScraper(),
    NovelFireScraper(),
    UniversalScraper(),
]

def get_scraper_for_url(url: str) -> BaseScraper:
    for scraper in SCRAPERS:
        if scraper.can_handle(url):
            return scraper
    return UniversalScraper()

__all__ = [
    "BaseScraper",
    "NovelMetadata",
    "ChapterInfo",
    "ChapterContent",
    "BotProtectionError",
    "WuxiaWorldScraper",
    "FreeWebNovelScraper",
    "WuxiaSpotScraper",
    "RoyalRoadScraper",
    "NovelFullScraper",
    "NovelFireScraper",
    "UniversalScraper",
    "get_scraper_for_url",
]
