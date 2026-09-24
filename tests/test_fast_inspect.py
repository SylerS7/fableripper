import time
import re
from curl_cffi import requests
from bs4 import BeautifulSoup

start = time.time()
slug = "shadow-slave"
r = requests.get(f"https://novelfire.net/book/{slug}", impersonate="chrome120")
s = BeautifulSoup(r.text, "html.parser")

title = s.select_one("h1").get_text(strip=True) if s.select_one("h1") else slug
author_el = s.find("a", href=re.compile(r"/author/"))
author = author_el.get_text(strip=True) if author_el else "Unknown"

desc_tag = s.find("meta", itemprop="description")
desc = desc_tag["content"] if desc_tag and "content" in desc_tag.attrs else ""

# Find total chapters count from text
ch_count = 0
for text in s.stripped_strings:
    m = re.match(r"^(\d+)\s*chapters?$", text, re.I)
    if m:
        ch_count = int(m.group(1))
        break

cover_tag = s.find("meta", property="og:image") or s.select_one(".book-cover img")
cover = cover_tag.get("content") or cover_tag.get("src") if cover_tag else None

print(f"Instantly fetched in {time.time() - start:.2f}s!")
print("Title:", title)
print("Author:", author)
print("Cover:", cover)
print("Total Chapters:", ch_count)
print("Synopsis preview:", desc[:80])
