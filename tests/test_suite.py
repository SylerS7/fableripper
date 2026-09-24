import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure root is in path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from scraper import get_scraper_for_url, NovelMetadata, ChapterInfo, ChapterContent
from scraper.wuxiaspot import WuxiaSpotScraper
from scraper.royalroad import RoyalRoadScraper
from scraper.universal import UniversalScraper
from epub import NovelExporter
from web_app import app

def test_scraper_resolution():
    print("Testing Scraper Resolution...")
    s1 = get_scraper_for_url("https://www.wuxiaspot.com/novel/battle-through-the-heavens.html")
    assert isinstance(s1, WuxiaSpotScraper), f"Expected WuxiaSpotScraper, got {type(s1)}"
    print("✓ WuxiaSpot scraper resolved correctly")

    s2 = get_scraper_for_url("https://www.royalroad.com/fiction/21220/mother-of-learning")
    assert isinstance(s2, RoyalRoadScraper), f"Expected RoyalRoadScraper, got {type(s2)}"
    print("✓ RoyalRoad scraper resolved correctly")

    s3 = get_scraper_for_url("https://example.com/some-random-novel")
    assert isinstance(s3, UniversalScraper), f"Expected UniversalScraper, got {type(s3)}"
    print("✓ Universal scraper resolved correctly as fallback")

def test_multi_format_export():
    print("\nTesting Multi-Format Export (EPUB, TXT, MD, Volumes)...")
    meta = NovelMetadata(
        title="Test Novel Title",
        slug="test-novel",
        url="https://example.com/novel",
        platform="TestPlatform",
        author="Author Persona",
        description="This is an adventurous synopsis about training and martial arts.",
        categories=["Fantasy", "Action"]
    )
    ch1 = ChapterContent(number=1, title="Chapter 1: The Beginning", url="https://example.com/1", paragraphs=["Paragraph 1 of novel.", "Paragraph 2 of novel."])
    ch2 = ChapterContent(number=2, title="Chapter 2: The Journey", url="https://example.com/2", paragraphs=["Another paragraph here.", "Concluding sentence."])
    ch3 = ChapterContent(number=3, title="Chapter 3: The Climax", url="https://example.com/3", paragraphs=["Final battle begins.", "Victory achieved!"])

    test_out = root_dir / "output" / "test_exports"
    test_out.mkdir(parents=True, exist_ok=True)

    exporter = NovelExporter(meta, [ch1, ch2, ch3])

    # 1. EPUB
    epub_file = exporter.export_epub(test_out / "test.epub")
    assert epub_file.exists() and epub_file.stat().st_size > 0
    print(f"✓ EPUB export created: {epub_file.name} ({epub_file.stat().st_size} bytes)")

    # 2. TXT
    txt_file = exporter.export_txt(test_out / "test.txt")
    assert txt_file.exists() and txt_file.stat().st_size > 0
    print(f"✓ TXT export created: {txt_file.name} ({txt_file.stat().st_size} bytes)")

    # 3. MD
    md_file = exporter.export_markdown(test_out / "test.md")
    assert md_file.exists() and md_file.stat().st_size > 0
    print(f"✓ Markdown export created: {md_file.name} ({md_file.stat().st_size} bytes)")

    # 4. Volumes (split 2 per volume)
    vols = exporter.export_volumes(test_out / "volumes", chapters_per_volume=2, fmt="epub")
    assert len(vols) == 2, f"Expected 2 volumes, got {len(vols)}"
    print(f"✓ Volume splitting created {len(vols)} volumes successfully")

def test_web_api_endpoints():
    print("\nTesting Web API Endpoints (Vercel-safe endpoints)...")
    client = app.test_client()

    # 1. GET /
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "OmniNovel" in res_root.text
    print("✓ GET / returned 200 with OmniNovel UI")

    # 2. POST /api/batch-chapters
    res_batch = client.post("/api/batch-chapters", json={
        "chapters": [
            {"number": 1, "title": "Chapter 1", "url": "https://www.wuxiaspot.com/novel/battle-through-the-heavens_1.html"},
            {"number": 2, "title": "Chapter 2", "url": "https://www.wuxiaspot.com/novel/battle-through-the-heavens_2.html"}
        ]
    })
    assert res_batch.status_code == 200
    batch_json = res_batch.get_json()
    assert len(batch_json["results"]) == 2
    assert len(batch_json["results"][0]["paragraphs"]) > 0
    print(f"✓ POST /api/batch-chapters fetched {len(batch_json['results'])} chapters successfully")

    # 3. POST /api/export-bundle
    res_bundle = client.post("/api/export-bundle", json={
        "metadata": {
            "title": "API Test Novel",
            "slug": "api-test",
            "url": "https://example.com",
            "author": "Tester"
        },
        "chapters": batch_json["results"],
        "format": "epub"
    })
    assert res_bundle.status_code == 200
    bundle_json = res_bundle.get_json()
    assert bundle_json["status"] == "ready"
    assert bundle_json["filename"].endswith(".epub")
    print(f"✓ POST /api/export-bundle generated file: {bundle_json['filename']}")

if __name__ == "__main__":
    test_scraper_resolution()
    test_multi_format_export()
    test_web_api_endpoints()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
