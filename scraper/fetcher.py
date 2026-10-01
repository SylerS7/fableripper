"""
Universal HTTP Fetcher with Cloudflare TLS Fingerprint Bypass and Rate-Limit Adaptation.
Supports curl_cffi Chrome impersonation with automatic fallback and per-domain pacing.
Strategy 3: Jina Reader proxy (bypasses Cloudflare from datacenter/serverless IPs).
"""

import time
import logging
import threading
from typing import Tuple, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Known bot-protected domains that block automated scrapers at the network/TLS level
BOT_PROTECTED_DOMAINS = {
    "archiveofourown.org": (
        "Archive of Our Own (AO3) strictly blocks automated scrapers. "
        "Please download the EPUB directly from the novel's page on AO3 using their built-in 'Download' button, "
        "or use the 'Paste Text to EPUB' tool."
    ),
    "fanfiction.net": (
        "FanFiction.net is protected by Cloudflare Under-Attack mode and blocks automated tools."
    ),
    "wattpad.com": (
        "Wattpad requires login and uses Cloudflare protection to block scrapers."
    ),
}

# Domains where Jina Reader proxy should be used as the primary strategy
# (Cloudflare-protected sites that block datacenter IPs like Vercel)
JINA_PREFERRED_DOMAINS = ["novelfire.net", "webnovel.com"]

# Known Cloudflare / bot protection page markers
BOT_PROTECTION_MARKERS = [
    "shields are up",
    "just a moment",
    "cf-browser-verification",
    "cf_captcha_kind",
    "enable javascript and cookies to continue",
    "checking your browser",
    "ddos-guard",
    "please wait while we verify",
    "security check",
    "human verification",
    "_cf_chl_opt",
    "used cloudflare to restrict access",
    "error 1015",
]

# Per-domain pacing locks to prevent 429 rate-limiting
_DOMAIN_LOCKS = {}
_LAST_REQUEST_TIME = {}
_LOCK = threading.Lock()

# Detect if running on Vercel (serverless environment)
def _is_vercel() -> bool:
    import os
    return bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))


def _get_domain_lock(domain: str) -> threading.Lock:
    with _LOCK:
        if domain not in _DOMAIN_LOCKS:
            _DOMAIN_LOCKS[domain] = threading.Lock()
        return _DOMAIN_LOCKS[domain]


def _apply_domain_pacing(domain: str):
    """
    Apply pacing if domain has strict rate-limiting rules.
    novelfire.net Cloudflare rate-limits if faster than ~1 request per 1.2s.
    jina.ai free tier: 20 req/min → 3 seconds between requests to be safe.
    Other domains run without artificial delays.
    """
    if "novelfire.net" in domain:
        min_interval = 1.25
    elif "jina.ai" in domain:
        min_interval = 3.2
    else:
        return

    lock = _get_domain_lock(domain)
    with lock:
        last = _LAST_REQUEST_TIME.get(domain, 0.0)
        now = time.time()
        elapsed = now - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _LAST_REQUEST_TIME[domain] = time.time()


def is_bot_protected(html: str, status_code: int) -> bool:
    """Detect if a page is a bot-protection challenge page."""
    if status_code in (403, 429, 503):
        lower = html.lower()
        return any(marker in lower for marker in BOT_PROTECTION_MARKERS)
    if status_code == 525:
        return True  # SSL handshake failures from Cloudflare
    return False


def get_bot_protection_reason(domain: str) -> str:
    """Get a user-friendly explanation for a known bot-protected domain."""
    for d, reason in BOT_PROTECTED_DOMAINS.items():
        if d in domain:
            return reason
    return (
        f"{domain} uses bot protection (Cloudflare or similar) that blocks automated access. "
        "This site cannot be scraped automatically — please use a site without Cloudflare protection."
    )


def _jina_fetch(url: str, timeout: int = 25) -> Tuple[str, int]:
    """
    Fetch a URL through the Jina Reader proxy (https://r.jina.ai/).
    Returns full HTML so BeautifulSoup can parse it normally.
    Free tier allows 20 req/min — pacing is applied via _apply_domain_pacing().
    """
    import urllib.request as _ureq

    jina_url = f"https://r.jina.ai/{url}"
    _apply_domain_pacing("r.jina.ai")

    req = _ureq.Request(
        jina_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "X-Return-Format": "html",
            "X-Timeout": str(timeout - 5),
        }
    )
    resp = _ureq.urlopen(req, timeout=timeout)
    html = resp.read().decode("utf-8", errors="replace")
    return html, 200


def smart_fetch(url: str, timeout: int = 15, max_retries: int = 3, retry_delay: float = 1.0) -> Tuple[str, int]:
    """
    Multi-strategy HTTP fetcher with Cloudflare TLS fingerprint bypass.
    Returns (html_text, status_code).
    Raises BotProtectionError or RuntimeError on failure.

    Strategy order:
      1. Jina Reader proxy  — used first on Vercel for Cloudflare-protected domains
      2. curl_cffi Chrome120  — bypasses TLS fingerprinting from local/residential IPs
      3. Regular requests  — plain fallback for non-fingerprinted sites
      4. Jina Reader proxy  — last-resort for any domain that failed above strategies
    """
    domain = urlparse(url).netloc
    last_code = 0
    is_vercel = _is_vercel()
    is_jina_preferred = any(d in domain for d in JINA_PREFERRED_DOMAINS)

    # ── Strategy 1: Jina Reader proxy (on Vercel for Cloudflare-protected domains) ──
    # On Vercel, datacenter IPs are blocked by Cloudflare regardless of TLS tricks.
    # Jina Reader proxies through clean residential-equivalent IPs and returns full HTML.
    if is_vercel and is_jina_preferred:
        try:
            html, code = _jina_fetch(url, timeout=30)
            if html and len(html) > 500:
                logger.info(f"[jina/primary] Successfully fetched {url}")
                return html, code
        except Exception as e:
            logger.warning(f"[jina/primary] Failed for {url}: {e} — falling through to curl_cffi")

    # ── Strategy 2: curl_cffi with Chrome impersonation ──
    # Bypasses basic TLS fingerprinting — works from residential/local IPs.
    curl_failed_with_bot = False
    try:
        from curl_cffi import requests as cffi_requests
        for attempt in range(1, max_retries + 1):
            _apply_domain_pacing(domain)
            try:
                resp = cffi_requests.get(
                    url,
                    impersonate="chrome120",
                    timeout=timeout,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": f"https://{domain}/",
                    }
                )
                html = resp.text
                code = resp.status_code
                last_code = code

                if code == 200:
                    return html, code

                if code in (404, 410):
                    return "", code

                if code == 429:
                    retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                    wait_time = float(retry_after) if retry_after and retry_after.isdigit() else 2.5
                    logger.warning(f"[curl_cffi] Rate limited (429) on {domain}. Waiting {wait_time}s (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        time.sleep(wait_time)
                        continue

                if is_bot_protected(html, code):
                    curl_failed_with_bot = True
                    logger.warning(f"[curl_cffi] Bot protection detected on {domain} (HTTP {code})")
                    break  # Don't re-raise yet — try Jina fallback first

                logger.warning(f"[curl_cffi] HTTP {code} for {url} (attempt {attempt})")

            except BotProtectionError:
                curl_failed_with_bot = True
                break
            except Exception as e:
                logger.warning(f"[curl_cffi] Error on {url}: {e} (attempt {attempt})")

            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

    except ImportError:
        logger.debug("curl_cffi not available, falling back to requests")

    # If curl_cffi failed due to rate-limiting (429), don't waste time retrying with requests
    if last_code == 429:
        raise RuntimeError(f"Rate limited by {domain} (HTTP 429). Please wait a moment before fetching more chapters.")

    # ── Strategy 3: Regular requests ──
    # Fallback for when curl_cffi is missing or for sites without TLS fingerprinting.
    # Skip for bot-protected domains where we know requests won't help.
    if not curl_failed_with_bot:
        try:
            import requests
            session = requests.Session()
            from config import DEFAULT_HEADERS
            session.headers.update(DEFAULT_HEADERS)

            for attempt in range(1, max_retries + 1):
                _apply_domain_pacing(domain)
                try:
                    resp = session.get(url, timeout=timeout)
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    html = resp.text
                    code = resp.status_code

                    if code == 200:
                        return html, code

                    if code in (404, 410):
                        return "", code

                    if is_bot_protected(html, code):
                        logger.warning(f"[requests] Bot protection detected on {domain} (HTTP {code})")
                        break  # Fall through to Jina

                    logger.warning(f"[requests] HTTP {code} for {url} (attempt {attempt})")

                except requests.RequestException as e:
                    logger.warning(f"[requests] Error on {url}: {e} (attempt {attempt})")

                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)

        except ImportError:
            pass

    # ── Strategy 4: Jina Reader proxy (last-resort for any domain) ──
    # Used when curl_cffi + requests both fail due to bot protection.
    # Also used as the universal fallback for any domain on Vercel.
    if is_jina_preferred or curl_failed_with_bot or is_vercel:
        try:
            logger.info(f"[jina/fallback] Attempting Jina proxy for {url}")
            html, code = _jina_fetch(url, timeout=30)
            if html and len(html) > 500:
                logger.info(f"[jina/fallback] Successfully fetched {url} via Jina Reader")
                return html, code
        except Exception as e:
            logger.warning(f"[jina/fallback] Failed for {url}: {e}")

    # All strategies exhausted — raise appropriate error
    if curl_failed_with_bot or is_vercel:
        reason = get_bot_protection_reason(domain)
        raise BotProtectionError(url, domain, reason)

    raise RuntimeError(f"All fetch strategies failed for {url}")


class BotProtectionError(Exception):
    """Raised when a page is behind bot protection (Cloudflare, DDoS-Guard, etc.)"""
    def __init__(self, url: str, domain: str, reason: str):
        self.url = url
        self.domain = domain
        self.reason = reason
        super().__init__(f"Bot protection detected on {domain}: {reason}")
