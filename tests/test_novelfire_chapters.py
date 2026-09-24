from curl_cffi import requests
from bs4 import BeautifulSoup

url = "https://novelfire.net/book/the-golden-lord-has-a-perverted-sss-rank-summoning-system/chapters"
resp = requests.get(url, impersonate="chrome120")
print("Status:", resp.status_code)
print("Length:", len(resp.text))
soup = BeautifulSoup(resp.text, "html.parser")
links = [a for a in soup.find_all("a", href=True) if "/chapter-" in a["href"]]
print(f"Total chapter links found on /chapters: {len(links)}")
if links:
    print("First chapter link:", links[0].get("href"), "->", links[0].get_text(strip=True))
    print("Last chapter link:", links[-1].get("href"), "->", links[-1].get_text(strip=True))

# Check pagination on /chapters page if any
pagination = soup.select(".pagination a, ul.pagination li a")
print(f"Pagination links found: {len(pagination)}")
for p in pagination:
    print("  Pag:", p.get("href"), p.get_text(strip=True))
