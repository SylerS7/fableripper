import os
import json
import uuid
import queue
import threading
from pathlib import Path
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template_string, Response, send_file

from config import DEFAULT_CONCURRENCY, OUTPUT_DIR, CACHE_DIR, IS_VERCEL
from engine import NovelPipeline
from scraper import get_scraper_for_url, NovelMetadata, ChapterInfo, ChapterContent
from epub import NovelExporter

app = Flask(__name__)

# Progress queues for SSE
progress_queues = {}

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OmniNovel - Universal Novel to EPUB & Reader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&family=Literata:ital,opsz,wght@0,7..72,300;0,7..72,400;0,7..72,600;1,7..72,300&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .reader-text { font-family: 'Literata', 'Merriweather', serif; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen selection:bg-cyan-500 selection:text-white pb-16">

    <!-- Top Navigation -->
    <header class="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-40">
        <div class="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
                    <i class="fas fa-book-sparkles text-lg"></i>
                </div>
                <div>
                    <span class="font-extrabold text-lg tracking-tight bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-300 bg-clip-text text-transparent">OmniNovel</span>
                    <span class="hidden sm:inline-block ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60">Universal Scraper & Reader</span>
                </div>
            </div>
            <div class="flex items-center gap-3 text-xs text-slate-400">
                <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Multi-Platform Ready</span>
            </div>
        </div>
    </header>

    <main class="max-w-5xl mx-auto px-4 pt-8 sm:pt-12">
        <!-- Hero Section -->
        <div class="text-center max-w-2xl mx-auto mb-10">
            <h1 class="text-3xl sm:text-5xl font-extrabold tracking-tight text-white mb-3">
                Read & Convert Any <br class="hidden sm:block"/>
                <span class="bg-gradient-to-r from-cyan-400 via-sky-400 to-blue-500 bg-clip-text text-transparent">Web Novel to EPUB</span>
            </h1>
            <p class="text-slate-400 text-sm sm:text-base leading-relaxed">
                Paste any novel or chapter URL. Supports <span class="text-cyan-300 font-medium">WuxiaSpot</span>, <span class="text-cyan-300 font-medium">Royal Road</span>, <span class="text-cyan-300 font-medium">NovelFull</span>, or <span class="text-cyan-300 font-medium">Any Web Fiction Site</span>. Read live or export to Kindle-ready EPUB, TXT, or Markdown.
            </p>
        </div>

        <!-- Main Input Card -->
        <div class="bg-slate-900/90 border border-slate-800 rounded-3xl p-5 sm:p-8 shadow-2xl relative overflow-hidden mb-8">
            <div class="absolute -right-20 -top-20 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
            <div class="absolute -left-20 -bottom-20 w-64 h-64 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>

            <div class="space-y-4 relative z-10">
                <div class="flex items-center justify-between">
                    <label class="text-xs sm:text-sm font-semibold text-slate-300 uppercase tracking-wider">Novel or Chapter URL</label>
                    <span id="detectedPlatformBadge" class="hidden text-xs font-semibold px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"></span>
                </div>
                <div class="flex flex-col sm:flex-row gap-3">
                    <div class="relative flex-1">
                        <div class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                            <i class="fas fa-compass"></i>
                        </div>
                        <input type="url" id="novelUrl" 
                               value="https://www.wuxiaspot.com/novel/battle-through-the-heavens.html" 
                               placeholder="e.g. https://www.wuxiaspot.com/novel/battle-through-the-heavens.html or royalroad.com..." 
                               class="w-full pl-11 pr-4 py-3.5 bg-slate-950/80 border border-slate-800 rounded-2xl text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent text-sm transition">
                    </div>
                    <button id="inspectBtn" onclick="inspectNovel()" class="px-7 py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold rounded-2xl shadow-lg shadow-cyan-500/20 transition duration-150 flex items-center justify-center gap-2 cursor-pointer">
                        <i class="fas fa-wand-magic-sparkles"></i>
                        <span>Inspect Novel</span>
                    </button>
                </div>
            </div>

            <!-- Novel Details Preview Card -->
            <div id="novelInfoCard" class="hidden mt-8 pt-8 border-t border-slate-800/80 transition-all">
                <div class="flex flex-col md:flex-row gap-6 items-start">
                    <div class="w-full md:w-48 flex-shrink-0 flex justify-center">
                        <img id="novelCover" src="" alt="Cover" class="w-40 md:w-48 h-56 md:h-68 object-cover rounded-2xl shadow-xl border border-slate-700/80">
                    </div>
                    <div class="flex-1 space-y-3.5 w-full">
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h2 id="novelTitle" class="text-2xl sm:text-3xl font-extrabold text-white"></h2>
                        </div>
                        <div class="flex flex-wrap items-center gap-2 text-xs">
                            <span id="novelAuthor" class="text-slate-400 font-medium"></span>
                            <span class="text-slate-600">•</span>
                            <span id="novelChaptersBadge" class="px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-semibold"></span>
                            <span class="text-slate-600">•</span>
                            <span id="novelPlatformBadge" class="px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20 font-semibold"></span>
                        </div>
                        <div id="novelTags" class="flex flex-wrap gap-1.5 pt-1"></div>
                        <div class="pt-2">
                            <p id="novelSynopsis" class="text-xs sm:text-sm text-slate-300 leading-relaxed line-clamp-4"></p>
                        </div>
                        
                        <!-- Instant In-Browser Reader Button -->
                        <div class="pt-3 flex flex-wrap gap-3">
                            <button onclick="openReaderModal()" class="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-cyan-300 font-medium text-xs sm:text-sm rounded-xl border border-slate-700 flex items-center gap-2 transition shadow">
                                <i class="fas fa-book-open-reader text-cyan-400"></i>
                                <span>Read Online Now</span>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Export & Conversion Configurations -->
                <div class="mt-8 pt-8 border-t border-slate-800/80">
                    <h3 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <i class="fas fa-sliders text-cyan-400"></i> Export & Download Options
                    </h3>
                    
                    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">Start Chapter</label>
                            <input type="number" id="startCh" placeholder="1" min="1" 
                                   class="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">End Chapter</label>
                            <input type="number" id="endCh" placeholder="All" min="1" 
                                   class="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">Format</label>
                            <select id="exportFormat" class="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:outline-none">
                                <option value="epub" selected>EPUB (Kindle/Apple Books)</option>
                                <option value="txt">Clean TXT (Screen readers)</option>
                                <option value="md">Markdown (Obsidian/Notion)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">Volume Split</label>
                            <select id="volumeSplit" class="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:outline-none">
                                <option value="0" selected>Single File (All in 1)</option>
                                <option value="100">Split every 100 chapters</option>
                                <option value="200">Split every 200 chapters</option>
                                <option value="500">Split every 500 chapters</option>
                            </select>
                        </div>
                    </div>

                    <!-- Action Trigger -->
                    <div class="mt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                        <div class="text-xs text-slate-400 flex items-center gap-2">
                            <i class="fas fa-bolt text-amber-400"></i>
                            <span>Smart chunking enabled for Vercel & mobile browsers.</span>
                        </div>
                        <button id="downloadBtn" onclick="startExport()" class="w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold rounded-2xl shadow-lg shadow-cyan-500/25 transition flex items-center justify-center gap-2 cursor-pointer">
                            <i class="fas fa-cloud-arrow-down"></i>
                            <span>Download E-Book</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- Progress Tracker -->
            <div id="progressSection" class="hidden mt-8 pt-6 border-t border-slate-800 space-y-3">
                <div class="flex justify-between items-center text-xs sm:text-sm">
                    <span id="progressMessage" class="text-slate-300 font-medium truncate pr-4">Preparing download...</span>
                    <span id="progressPercent" class="text-cyan-400 font-bold">0%</span>
                </div>
                <div class="w-full bg-slate-950 rounded-full h-3 overflow-hidden p-0.5 border border-slate-800">
                    <div id="progressBar" class="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full transition-all duration-300 ease-out" style="width: 0%"></div>
                </div>
            </div>

            <!-- Result Box -->
            <div id="downloadReadyBox" class="hidden mt-6 p-4 sm:p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div class="flex items-center gap-3.5">
                    <div class="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xl flex-shrink-0">
                        <i class="fas fa-circle-check"></i>
                    </div>
                    <div>
                        <h4 class="font-bold text-emerald-300 text-sm sm:text-base">File Ready for Download!</h4>
                        <p id="downloadFilename" class="text-xs text-slate-400"></p>
                    </div>
                </div>
                <a id="downloadLink" href="#" class="w-full sm:w-auto px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl text-sm transition flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/30">
                    <i class="fas fa-download"></i>
                    <span>Save to Device</span>
                </a>
            </div>
        </div>

        <!-- Supported Platforms Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10">
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-center">
                <div class="text-cyan-400 text-lg mb-1"><i class="fas fa-dragon"></i></div>
                <h4 class="text-xs font-bold text-slate-200">WuxiaSpot</h4>
                <p class="text-[11px] text-slate-500 mt-0.5">Xianxia & Wuxia</p>
            </div>
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-center">
                <div class="text-purple-400 text-lg mb-1"><i class="fas fa-crown"></i></div>
                <h4 class="text-xs font-bold text-slate-200">Royal Road</h4>
                <p class="text-[11px] text-slate-500 mt-0.5">LitRPG & Fantasy</p>
            </div>
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-center">
                <div class="text-blue-400 text-lg mb-1"><i class="fas fa-book"></i></div>
                <h4 class="text-xs font-bold text-slate-200">NovelFull</h4>
                <p class="text-[11px] text-slate-500 mt-0.5">Web Light Novels</p>
            </div>
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-center">
                <div class="text-amber-400 text-lg mb-1"><i class="fas fa-globe"></i></div>
                <h4 class="text-xs font-bold text-slate-200">Universal Mode</h4>
                <p class="text-[11px] text-slate-500 mt-0.5">Any Novel Link</p>
            </div>
        </div>
    </main>

    <!-- IN-BROWSER READER MODAL -->
    <div id="readerModal" class="hidden fixed inset-0 z-50 bg-slate-950 flex flex-col">
        <!-- Reader Header -->
        <div id="readerHeader" class="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-4 flex items-center justify-between flex-shrink-0">
            <div class="flex items-center gap-3 overflow-hidden">
                <button onclick="closeReaderModal()" class="text-slate-400 hover:text-white p-2 rounded-lg">
                    <i class="fas fa-arrow-left"></i>
                </button>
                <div class="truncate">
                    <h3 id="readerNovelTitle" class="text-xs font-bold text-slate-200 truncate"></h3>
                    <p id="readerChapterTitle" class="text-[11px] text-cyan-400 truncate"></p>
                </div>
            </div>
            
            <div class="flex items-center gap-2">
                <!-- Chapter Selector Dropdown -->
                <select id="readerChapterSelect" onchange="onReaderChapterChange(this.value)" class="text-xs bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none max-w-[130px] sm:max-w-[200px] truncate">
                </select>

                <!-- Font size controls -->
                <button onclick="changeFontSize(-1)" class="p-1.5 text-slate-400 hover:text-white text-xs">A-</button>
                <button onclick="changeFontSize(1)" class="p-1.5 text-slate-400 hover:text-white text-xs">A+</button>
                
                <!-- Close Button -->
                <button onclick="closeReaderModal()" class="text-slate-400 hover:text-white p-2 text-sm ml-1">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>

        <!-- Reader Scroll Content Area -->
        <div id="readerContentContainer" class="flex-1 overflow-y-auto px-4 py-8">
            <div id="readerBody" class="max-w-2xl mx-auto reader-text text-base sm:text-lg leading-relaxed text-slate-200 space-y-6">
                <!-- Dynamic Chapter Content Injected Here -->
            </div>

            <!-- Bottom Navigation -->
            <div class="max-w-2xl mx-auto mt-12 pt-6 border-t border-slate-800 flex items-center justify-between">
                <button id="readerPrevBtn" onclick="navigateChapter(-1)" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold flex items-center gap-2">
                    <i class="fas fa-chevron-left"></i> Previous
                </button>
                <button id="readerNextBtn" onclick="navigateChapter(1)" class="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white rounded-xl text-xs font-semibold flex items-center gap-2">
                    Next <i class="fas fa-chevron-right"></i>
                </button>
            </div>
        </div>
    </div>

    <script>
        let inspectedNovel = null;
        let currentReaderChapterIndex = 0;
        let readerFontSize = 18;

        async function inspectNovel() {
            const url = document.getElementById('novelUrl').value.trim();
            if (!url) return alert('Please enter a novel URL');

            const btn = document.getElementById('inspectBtn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Analyzing...</span>';

            try {
                const res = await fetch('/api/inspect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Failed to inspect novel');

                inspectedNovel = data;

                document.getElementById('novelTitle').innerText = data.title;
                document.getElementById('novelAuthor').innerText = 'by ' + (data.author || 'Unknown');
                document.getElementById('novelChaptersBadge').innerText = (data.chapters || []).length + ' Chapters';
                document.getElementById('novelPlatformBadge').innerText = data.platform || 'Platform';
                document.getElementById('novelSynopsis').innerText = data.description || 'No synopsis provided.';
                
                if (data.cover_url) {
                    document.getElementById('novelCover').src = data.cover_url;
                } else {
                    document.getElementById('novelCover').src = 'https://via.placeholder.com/300x450?text=No+Cover';
                }

                // Tags
                const tagsContainer = document.getElementById('novelTags');
                tagsContainer.innerHTML = '';
                (data.categories || []).forEach(cat => {
                    const tag = document.createElement('span');
                    tag.className = 'px-2.5 py-0.5 text-xs bg-slate-800 text-slate-300 rounded-lg border border-slate-700/50';
                    tag.innerText = cat;
                    tagsContainer.appendChild(tag);
                });

                document.getElementById('startCh').value = 1;
                document.getElementById('endCh').placeholder = `Max (${data.chapters.length})`;

                // Populate reader chapter dropdown
                const select = document.getElementById('readerChapterSelect');
                select.innerHTML = '';
                (data.chapters || []).forEach((ch, idx) => {
                    const opt = document.createElement('option');
                    opt.value = idx;
                    opt.innerText = ch.title;
                    select.appendChild(opt);
                });

                document.getElementById('novelInfoCard').classList.remove('hidden');
                document.getElementById('detectedPlatformBadge').innerText = data.platform;
                document.getElementById('detectedPlatformBadge').classList.remove('hidden');
            } catch (err) {
                alert('Scraper Error: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i><span>Inspect Novel</span>';
            }
        }

        async function startExport() {
            if (!inspectedNovel) return alert('Please inspect a novel first.');

            const startVal = document.getElementById('startCh').value;
            const endVal = document.getElementById('endCh').value;
            const fmt = document.getElementById('exportFormat').value;
            const splitVal = parseInt(document.getElementById('volumeSplit').value);

            const startCh = startVal ? parseInt(startVal) : 1;
            const endCh = endVal ? parseInt(endVal) : (inspectedNovel.chapters.length || 1);

            const btn = document.getElementById('downloadBtn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Processing...</span>';

            document.getElementById('progressSection').classList.remove('hidden');
            document.getElementById('downloadReadyBox').classList.add('hidden');
            document.getElementById('progressBar').style.width = '5%';
            document.getElementById('progressPercent').innerText = '5%';
            document.getElementById('progressMessage').innerText = 'Starting client-orchestrated fetch...';

            try {
                // Filter chapters to export
                const chaptersToFetch = inspectedNovel.chapters.filter(ch => ch.number >= startCh && ch.number <= endCh);
                if (chaptersToFetch.length === 0) throw new Error('No chapters in the selected range.');

                // Batch fetch chapters (Vercel-safe chunking)
                const batchSize = 6;
                const fetchedChapters = [];
                const total = chaptersToFetch.length;

                for (let i = 0; i < total; i += batchSize) {
                    const chunk = chaptersToFetch.slice(i, i + batchSize);
                    document.getElementById('progressMessage').innerText = `Fetching chapters ${i + 1} to ${Math.min(i + batchSize, total)} of ${total}...`;

                    const batchRes = await fetch('/api/batch-chapters', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ chapters: chunk })
                    });
                    const batchData = await batchRes.json();
                    if (!batchRes.ok) throw new Error(batchData.error || 'Failed to fetch chapter batch');

                    fetchedChapters.push(...batchData.results);
                    const pct = Math.round(((i + chunk.length) / total) * 85);
                    document.getElementById('progressBar').style.width = pct + '%';
                    document.getElementById('progressPercent').innerText = pct + '%';
                }

                // Send assembled chapters to export endpoint
                document.getElementById('progressMessage').innerText = `Building ${fmt.toUpperCase()} document...`;
                document.getElementById('progressBar').style.width = '90%';
                document.getElementById('progressPercent').innerText = '90%';

                const exportRes = await fetch('/api/export-bundle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        metadata: inspectedNovel,
                        chapters: fetchedChapters,
                        format: fmt,
                        split_volumes: splitVal > 0 ? splitVal : null
                    })
                });

                const exportData = await exportRes.json();
                if (!exportRes.ok) throw new Error(exportData.error || 'Failed to build export');

                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressPercent').innerText = '100%';
                document.getElementById('progressMessage').innerText = 'Complete!';

                document.getElementById('downloadFilename').innerText = exportData.filename;
                document.getElementById('downloadLink').href = '/api/file/' + encodeURIComponent(exportData.filename);
                document.getElementById('downloadReadyBox').classList.remove('hidden');
            } catch (err) {
                alert('Export failed: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-cloud-arrow-down"></i><span>Download E-Book</span>';
            }
        }

        // ================= READER MODAL FUNCTIONS =================
        function openReaderModal() {
            if (!inspectedNovel || !inspectedNovel.chapters.length) return alert('No chapters available');
            document.getElementById('readerNovelTitle').innerText = inspectedNovel.title;
            document.getElementById('readerModal').classList.remove('hidden');
            loadReaderChapter(0);
        }

        function closeReaderModal() {
            document.getElementById('readerModal').classList.add('hidden');
        }

        async function loadReaderChapter(idx) {
            currentReaderChapterIndex = idx;
            const ch = inspectedNovel.chapters[idx];
            document.getElementById('readerChapterTitle').innerText = ch.title;
            document.getElementById('readerChapterSelect').value = idx;

            const bodyEl = document.getElementById('readerBody');
            bodyEl.innerHTML = '<div class="py-20 text-center text-slate-400"><i class="fas fa-spinner fa-spin text-2xl mb-3"></i><p>Loading chapter...</p></div>';
            document.getElementById('readerContentContainer').scrollTop = 0;

            try {
                const res = await fetch('/api/chapter', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: ch.url, title: ch.title, number: ch.number })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Failed to load chapter');

                bodyEl.innerHTML = `
                    <h2 class="text-2xl sm:text-3xl font-bold text-white mb-6 pt-4 border-b border-slate-800 pb-3">${data.title}</h2>
                    ${(data.paragraphs || []).map(p => `<p class="leading-relaxed mb-4">${p}</p>`).join('')}
                `;

                // Update prev/next button states
                document.getElementById('readerPrevBtn').disabled = idx === 0;
                document.getElementById('readerNextBtn').disabled = idx === inspectedNovel.chapters.length - 1;
            } catch (err) {
                bodyEl.innerHTML = `<div class="py-12 text-center text-rose-400"><p>Error loading chapter: ${err.message}</p></div>`;
            }
        }

        function onReaderChapterChange(idx) {
            loadReaderChapter(parseInt(idx));
        }

        function navigateChapter(dir) {
            const nextIdx = currentReaderChapterIndex + dir;
            if (nextIdx >= 0 && nextIdx < inspectedNovel.chapters.length) {
                loadReaderChapter(nextIdx);
            }
        }

        function changeFontSize(delta) {
            readerFontSize = Math.max(14, Math.min(28, readerFontSize + delta * 2));
            document.getElementById('readerBody').style.fontSize = readerFontSize + 'px';
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/api/inspect", methods=["POST"])
def api_inspect():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Novel URL is required"}), 400

    try:
        pipeline = NovelPipeline(url=url)
        metadata = pipeline.get_novel_info()
        return jsonify(metadata.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chapter", methods=["POST"])
def api_chapter():
    """
    Stateless chapter fetcher (Vercel-safe).
    """
    data = request.json or {}
    url = data.get("url", "").strip()
    title = data.get("title", "")
    number = int(data.get("number", 1))

    if not url:
        return jsonify({"error": "Chapter URL is required"}), 400

    try:
        scraper = get_scraper_for_url(url)
        content = scraper.get_chapter_content(url)
        if not content.title or not content.title.strip():
            content.title = title or f"Chapter {number}"
        return jsonify(content.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/batch-chapters", methods=["POST"])
def api_batch_chapters():
    """
    Fetches a small batch of chapters concurrently (5-10 chapters per call).
    Designed to complete well within Vercel's 10-second timeout.
    """
    data = request.json or {}
    chapters_data = data.get("chapters", [])
    if not chapters_data:
        return jsonify({"results": []})

    results = []
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(ch):
        url = ch.get("url")
        num = ch.get("number", 1)
        title = ch.get("title", f"Chapter {num}")
        scraper = get_scraper_for_url(url)
        try:
            content = scraper.get_chapter_content(url)
            if not content.title:
                content.title = title
            return content.to_dict()
        except Exception as e:
            return {
                "number": num,
                "title": title,
                "url": url,
                "paragraphs": [f"[Content could not be retrieved: {e}]"]
            }

    with ThreadPoolExecutor(max_workers=min(len(chapters_data), 6)) as executor:
        for item in executor.map(fetch_one, chapters_data):
            results.append(item)

    return jsonify({"results": results})

@app.route("/api/export-bundle", methods=["POST"])
def api_export_bundle():
    """
    Takes inspected metadata + fetched chapters and builds the requested format
    (EPUB, TXT, or MD) and saves to temporary directory for download.
    """
    data = request.json or {}
    meta_dict = data.get("metadata", {})
    chapters_dict_list = data.get("chapters", [])
    fmt = data.get("format", "epub").lower()
    split_volumes = data.get("split_volumes")

    if not chapters_dict_list:
        return jsonify({"error": "No chapters provided"}), 400

    metadata = NovelMetadata.from_dict(meta_dict)
    chapters = [ChapterContent.from_dict(c) for c in chapters_dict_list]

    # Download cover if available
    cover_bytes = None
    if metadata.cover_url:
        try:
            import requests
            resp = requests.get(metadata.cover_url, timeout=8)
            if resp.status_code == 200:
                cover_bytes = resp.content
        except Exception:
            pass

    exporter = NovelExporter(metadata, chapters, cover_bytes=cover_bytes)

    safe_title = "".join(c for c in metadata.title if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")
    ch_range = f"Ch{chapters[0].number}-{chapters[-1].number}"
    
    if split_volumes and int(split_volumes) > 0:
        vol_paths = exporter.export_volumes(
            base_output_dir=OUTPUT_DIR,
            chapters_per_volume=int(split_volumes),
            fmt=fmt
        )
        return jsonify({
            "status": "ready",
            "filename": vol_paths[0].name,
            "count": len(vol_paths)
        })

    filename = f"{safe_title}_{ch_range}.{fmt}"
    out_path = OUTPUT_DIR / filename

    if fmt == "epub":
        exporter.export_epub(out_path)
    elif fmt == "txt":
        exporter.export_txt(out_path)
    elif fmt == "md":
        exporter.export_markdown(out_path)
    else:
        exporter.export_epub(out_path)

    return jsonify({
        "status": "ready",
        "filename": filename
    })

@app.route("/api/file/<path:filename>")
def api_file(filename):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True, download_name=filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
