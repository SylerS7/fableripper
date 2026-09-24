import re
import time
import logging
from urllib.parse import urljoin, urlparse
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Sites known to use aggressive bot protection (Cloudflare, etc.)
# These won't work with any automated scraping approach.
BOT_PROTECTED_DOMAINS = {
    "archiveofourown.org": "Archive of Our Own (AO3) uses Cloudflare bot protection that blocks automated access. Please download works manually from the AO3 website.",
    "fanfiction.net": "FanFiction.net blocks automated scraping. Consider using an alternative mirror.",
    "wattpad.com": "Wattpad blocks automated scraping.",
}

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
]


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


def smart_fetch(url: str, timeout: int = 15, max_retries: int = 3, retry_delay: float = 1.0) -> Tuple[str, int]:
    """
    Multi-strategy HTTP fetcher with Cloudflare TLS fingerprint bypass.
    Returns (html_text, status_code).
    Raises BotProtectionError or RuntimeError on failure.
    """
    domain = urlparse(url).netloc

    # Strategy 1: curl_cffi with Chrome impersonation (bypasses basic TLS fingerprinting)
    try:
        from curl_cffi import requests as cffi_requests
        for attempt in range(1, max_retries + 1):
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

                if is_bot_protected(html, code):
                    reason = get_bot_protection_reason(domain)
                    raise BotProtectionError(url, domain, reason)

                if code == 200:
                    return html, code

                if code in (404, 410):
                    return "", code

                logger.warning(f"[curl_cffi] HTTP {code} for {url} (attempt {attempt})")

            except BotProtectionError:
                raise
            except Exception as e:
                logger.warning(f"[curl_cffi] Error on {url}: {e} (attempt {attempt})")

            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

    except ImportError:
        logger.debug("curl_cffi not available, falling back to requests")

    # Strategy 2: Regular requests (fallback)
    try:
        import requests
        session = requests.Session()
        from config import DEFAULT_HEADERS
        session.headers.update(DEFAULT_HEADERS)
        
        for attempt in range(1, max_retries + 1):
            try:
                resp = session.get(url, timeout=timeout)
                resp.encoding = resp.apparent_encoding or "utf-8"
                html = resp.text
                code = resp.status_code

                if is_bot_protected(html, code):
                    reason = get_bot_protection_reason(domain)
                    raise BotProtectionError(url, domain, reason)

                if code == 200:
                    return html, code

                if code in (404, 410):
                    return "", code

                logger.warning(f"[requests] HTTP {code} for {url} (attempt {attempt})")

            except BotProtectionError:
                raise
            except requests.RequestException as e:
                logger.warning(f"[requests] Error on {url}: {e} (attempt {attempt})")

            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

    except ImportError:
        pass

    raise RuntimeError(f"All fetch strategies failed for {url}")


class BotProtectionError(Exception):
    """Raised when a page is behind bot protection (Cloudflare, DDoS-Guard, etc.)"""
    def __init__(self, url: str, domain: str, reason: str):
        self.url = url
        self.domain = domain
        self.reason = reason
        super().__init__(f"Bot protection detected on {domain}: {reason}")
