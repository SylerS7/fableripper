from curl_cffi import requests
from bs4 import BeautifulSoup
import re

url = "https://novelfire.net/book/the-golden-lord-has-a-perverted-sss-rank-summoning-system"
resp = requests.get(url, impersonate="chrome120")
print("Status:", resp.status_code)
print("Length:", len(resp.text))
soup = BeautifulSoup(resp.text, "html.parser")

title = soup.select_one("h1")
print("Title:", title.get_text(strip=True) if title else "None")

# Find author
author = soup.select_one(".author, a[href*='/author/']")
print("Author:", author.get_text(strip=True) if author else "None")

# Find cover
cover = soup.select_one(".book-cover img, .cover img, .poster img, img[src*='cover']")
print("Cover:", cover.get("src") if cover else "None")

# Check all links on the page that could be chapters or chapter list tabs
print("\nLinks containing chapter:")
ch_links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if "chapter" in href.lower() or "chapter" in text.lower():
        ch_links.append((href, text[:30]))

print(f"Total chapter links found on main page: {len(ch_links)}")
for h, t in ch_links[:10]:
    print("  ", h, "->", t)

# Check if there is an ajax endpoint, pagination, or tab for chapters
for script in soup.find_all("script"):
    src = script.get("src", "")
    content = script.string or ""
    if "chapter" in content.lower() or "ajax" in content.lower():
        for line in content.split("\n"):
            if "chapter" in line.lower() or "page" in line.lower() or "ajax" in line.lower():
                print("Script line:", line.strip()[:100])
