# 📚 OmniNovel - Universal Web Novel Scraper, Reader & EPUB Converter

A versatile, multi-platform tool to scrape online web novels from various platforms and compile them into reader-ready **EPUB**, **TXT**, or **Markdown** files with cover art, metadata, table of contents, and clean typography.

Features an **In-Browser Reader Mode** ("Read Online Now") and is optimized for both local use and serverless deployment on **Vercel**.

---

## ✨ Features

- **Multi-Platform Support (Not Hardcoded)**:
  - 🥋 **WuxiaSpot** (`wuxiaspot.com`) - Eastern fantasy, Xianxia, Wuxia (*Battle Through the Heavens*, etc.)
  - 👑 **Royal Road** (`royalroad.com`) - LitRPG, Progression Fantasy (*Mother of Learning*, etc.)
  - 📖 **NovelFull / AllNovelFull** (`novelfull.net`, `allnovelfull.com`) - Web translations
  - 🌐 **Universal Fallback** - Automatic heuristic scraper that can parse any arbitrary web novel page using OpenGraph, JSON-LD, and Readability DOM heuristics.
- **In-Browser Reader Mode**:
  - Read chapters directly on mobile or desktop without transferring an EPUB.
  - Chapter selector drawer, font sizing controls, and distraction-free dark typography.
- **Multi-Format Export**:
  - **EPUB**: E-reader ready with embedded cover art, CSS stylesheet, and NCX/EPUB3 navigation.
  - **Clean TXT**: Single text file formatted for screen readers and offline text-to-speech.
  - **Markdown (`.md`)**: Formatted for Obsidian, Notion, and personal archives.
- **Volume Splitting**:
  - Automatically splits 1,000+ chapter novels into volumes of 100 or 200 chapters to prevent e-reader freezes.
- **Vercel Serverless Ready**:
  - Serverless configuration in `vercel.json` and `api/index.py`.
  - Client-side chunked fetching prevents 10-second serverless execution timeouts.
  - Automatic detection and use of `/tmp` in cloud environments.

---

## 🚀 Local Quick Start

### 1. Web UI (Mobile & Desktop)
```powershell
python web_app.py
```
Open **`http://127.0.0.1:5000`** (or access via your local Wi-Fi IP on your phone).

### 2. Command Line (CLI)
```powershell
# Inspect any novel:
python main.py "https://www.royalroad.com/fiction/21220/mother-of-learning" --info

# Download specific chapter range as EPUB:
python main.py "https://www.wuxiaspot.com/novel/battle-through-the-heavens.html" --start 1 --end 50

# Export as Markdown or TXT:
python main.py "https://www.wuxiaspot.com/novel/battle-through-the-heavens.html" --start 1 --end 20 --format md

# Split into volumes of 100 chapters:
python main.py "https://www.wuxiaspot.com/novel/battle-through-the-heavens.html" --start 1 --end 300 --split 100
```

---

## ☁️ Deploying to Vercel

Deploy directly using the Vercel CLI:

```powershell
cd c:\Users\Aryan\Projects\novel-to-epub
vercel
```

Follow the prompts, and your novel scraper will be live at a public URL (e.g. `https://your-app.vercel.app`) accessible from your phone anywhere!
