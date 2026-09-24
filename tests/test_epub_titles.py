import zipfile
import sys
sys.path.insert(0, '.')
from scraper.extractor import clean_title_str
from ebooklib import epub

with zipfile.ZipFile('output/Battle_Through_the_Heavens_Ch295-310.epub') as z:
    for name in z.namelist():
        if 'chapter_00301' in name or 'chapter_00303' in name:
            with z.open(name) as f:
                content = f.read().decode('utf-8')
                start = content.find('<h1')
                end = content.find('</h1>') + 5
                if start >= 0 and end > start:
                    print(f"{name}:")
                    print(content[start:end])
                    print()
