import re

with open('web_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the export section bounds and replace it entirely with the new UI
OLD_SECTION_START = '                <div class="mt-8 pt-8 border-t border-slate-800/80">\n                    <h3 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">\n                        <i class="fas fa-sliders text-cyan-400"></i> Export & Download Options\n                    </h3>'

NEW_SECTION = '''                <div class="mt-8 pt-8 border-t border-slate-800/80">
                    <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-5 flex items-center gap-2">
                        <i class="fas fa-sliders text-cyan-400"></i> Export & Download Options
                    </h3>

                    <!-- Chapter Range Row -->
                    <div class="flex flex-col sm:flex-row gap-3 mb-5">
                        <div class="flex-1">
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">From Chapter</label>
                            <div class="relative">
                                <span class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 text-xs font-bold">#</span>
                                <input type="number" id="startCh" placeholder="1" min="1"
                                       class="w-full pl-7 pr-3 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:border-cyan-500/50 focus:outline-none transition">
                            </div>
                        </div>
                        <div class="hidden sm:flex items-end pb-2 text-slate-600">—</div>
                        <div class="flex-1">
                            <label class="block text-xs font-medium text-slate-400 mb-1.5">To Chapter</label>
                            <div class="relative">
                                <span class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 text-xs font-bold">#</span>
                                <input type="number" id="endCh" placeholder="All" min="1"
                                       class="w-full pl-7 pr-3 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 text-sm focus:ring-1 focus:ring-cyan-500 focus:border-cyan-500/50 focus:outline-none transition">
                            </div>
                        </div>
                        <div class="hidden sm:flex items-end">
                            <button onclick="setAllChapters()" class="py-2.5 px-4 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold border border-slate-700 transition whitespace-nowrap">
                                All
                            </button>
                        </div>
                    </div>

                    <!-- Format Picker -->
                    <div class="mb-5">
                        <label class="block text-xs font-medium text-slate-400 mb-2">Output Format</label>
                        <div class="grid grid-cols-3 gap-2" id="formatPicker">
                            <button onclick="setFormat(\'epub\')" data-fmt="epub"
                                    class="fmt-btn active-fmt flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center transition cursor-pointer">
                                <i class="fas fa-book text-sm"></i>
                                <span class="text-xs font-bold">EPUB</span>
                                <span class="text-[10px] text-slate-400 leading-snug">Kindle · Apple Books</span>
                            </button>
                            <button onclick="setFormat(\'txt\')" data-fmt="txt"
                                    class="fmt-btn flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center transition cursor-pointer">
                                <i class="fas fa-file-lines text-sm"></i>
                                <span class="text-xs font-bold">Plain TXT</span>
                                <span class="text-[10px] text-slate-400 leading-snug">Any device</span>
                            </button>
                            <button onclick="setFormat(\'md\')" data-fmt="md"
                                    class="fmt-btn flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center transition cursor-pointer">
                                <i class="fab fa-markdown text-sm"></i>
                                <span class="text-xs font-bold">Markdown</span>
                                <span class="text-[10px] text-slate-400 leading-snug">Obsidian · Notion</span>
                            </button>
                        </div>
                        <input type="hidden" id="exportFormat" value="epub">
                    </div>

                    <!-- Volume Split Picker -->
                    <div class="mb-6">
                        <label class="block text-xs font-medium text-slate-400 mb-2">Volume Split</label>
                        <div class="flex flex-wrap gap-2" id="splitPicker">
                            <button onclick="setSplit(0)" data-split="0"
                                    class="split-btn active-split px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer">
                                Single File
                            </button>
                            <button onclick="setSplit(50)" data-split="50"
                                    class="split-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer">
                                50 / vol
                            </button>
                            <button onclick="setSplit(100)" data-split="100"
                                    class="split-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer">
                                100 / vol
                            </button>
                            <button onclick="setSplit(200)" data-split="200"
                                    class="split-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer">
                                200 / vol
                            </button>
                            <button onclick="setSplit(500)" data-split="500"
                                    class="split-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer">
                                500 / vol
                            </button>
                        </div>
                        <input type="hidden" id="volumeSplit" value="0">
                    </div>

                    <!-- Action Row -->
                    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                        <p class="text-[11px] text-slate-500 flex items-center gap-1.5">
                            <i class="fas fa-bolt text-amber-400/80 text-xs"></i>
                            Chapters fetched in smart batches — safe on mobile & Vercel.
                        </p>
                        <button id="downloadBtn" onclick="startExport()"
                                class="w-full sm:w-auto px-8 py-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold rounded-2xl shadow-lg shadow-cyan-500/20 transition flex items-center justify-center gap-2 cursor-pointer">
                            <i class="fas fa-cloud-arrow-down"></i>
                            <span>Download E-Book</span>
                        </button>
                    </div>
                </div>'''

if OLD_SECTION_START in content:
    # Find end of old section (closing </div> of the outer div)
    old_start_idx = content.find(OLD_SECTION_START)
    # Find the closing div of the export block (it ends right before "<!-- Progress Tracker -->")
    old_end_marker = '            </div>\n\n            <!-- Progress Tracker -->'
    old_end_idx = content.find(old_end_marker, old_start_idx)
    if old_end_idx == -1:
        print("ERROR: Could not find end marker")
    else:
        # Replace from start to just before the end marker (keep the end marker)
        new_content = content[:old_start_idx] + NEW_SECTION + '\n' + content[old_end_idx:]
        with open('web_app.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("SUCCESS: Export section replaced!")
        print(f"Old section started at char {old_start_idx}")
        print(f"Old section ended at char {old_end_idx}")
else:
    print("ERROR: Could not find OLD_SECTION_START in content!")
    # Show what's around the export section
    idx = content.find('Export & Download')
    print("Found at:", idx)
    print("Context:", repr(content[idx-200:idx+50]))
