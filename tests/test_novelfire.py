from curl_cffi import requests
from bs4 import BeautifulSoup
import urllib.parse

# Search novelfire
search_url = "https://novelfire.net/search?keyword=The+Golden+Lord"
resp = requests.get(search_url, impersonate="chrome120")
print("Search status:", resp.status_code)
soup = BeautifulSoup(resp.text, "html.parser")
for a in soup.find_all("a", href=True):
    if "/book/" in a["href"]:
        print("Novel link:", a["href"], a.get_text(strip=True)[:40])
