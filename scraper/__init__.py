from .base import BaseScraper, NovelMetadata, ChapterInfo, ChapterContent
from .wuxiaspot import WuxiaSpotScraper
from .royalroad import RoyalRoadScraper
from .novelfull import NovelFullScraper
from .universal import UniversalScraper
from typing import List

# Scrapers in priority order (specific platforms first, universal fallback last)
SCRAPERS: List[BaseScraper] = [
    WuxiaSpotScraper(),
    RoyalRoadScraper(),
    NovelFullScraper(),
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
    "WuxiaSpotScraper",
    "RoyalRoadScraper",
    "NovelFullScraper",
    "UniversalScraper",
    "get_scraper_for_url",
]
