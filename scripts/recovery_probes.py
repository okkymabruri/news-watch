"""
Reusable recovery probes for investigating blocked/quarantined scrapers.

Three harnesses:
1. Browser Trace — capture all network activity during page load
2. Leakage Diff — compare link sets across positive/different/nonsense keywords
3. Search Surface Discovery — probe common search endpoint patterns
"""

import logging
import re
from typing import Dict, List, Set
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ARTICLE_PATTERNS = [
    r"/\d{4}/\d{2}/\d{2}/",
    r"/read/\d+",
    r"/berita/\d+",
    r"/artikel/",
    r"/news/\d",
    r"/\d{6,}/",
]


# ── 1. Browser Trace Harness ────────────────────────────────────────────────

async def browser_trace(
    url: str,
    keywords: List[str] = None,
    wait_ms: int = 5000,
    timeout_ms: int = 30000,
) -> Dict:
    """Open url in Playwright, capture all network requests and response info.
    
    Run once per keyword to compare what endpoints are hit.
    Returns structured trace with request URLs, types, status codes, and Cloudflare markers.
    """
    from playwright.async_api import async_playwright
    
    keywords = keywords or ["test"]
    results = {}
    
    for kw in keywords:
        trace_url = url.replace("{keyword}", kw) if "{keyword}" in url else url
        trace = {
            "url": trace_url,
            "keyword": kw,
            "requests": [],
            "xhr_fetch": [],
            "cloudflare_markers": [],
            "page_title": "",
            "body_text_snippet": "",
            "article_links": [],
        }
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            async def handle_request(request):
                req_info = {
                    "url": request.url[:200],
                    "method": request.method,
                    "type": request.resource_type,
                }
                trace["requests"].append(req_info)
                
                if request.resource_type in ("xhr", "fetch"):
                    trace["xhr_fetch"].append({
                        "url": request.url[:200],
                        "method": request.method,
                        "post_data": request.post_data[:200] if request.post_data else None,
                    })
            
            page.on("request", handle_request)
            
            try:
                await page.goto(trace_url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(wait_ms)
                
                trace["page_title"] = await page.title()
                body_text = await page.evaluate("() => document.body.innerText")
                trace["body_text_snippet"] = body_text[:300]
                
                # Detect Cloudflare markers
                cf_markers = []
                body_lower = body_text.lower()
                for marker in ["cloudflare", "cf-challenge", "cf-ray", "checking your browser", "just a moment", "attention required"]:
                    if marker in body_lower:
                        cf_markers.append(marker)
                trace["cloudflare_markers"] = cf_markers
                
                # Extract article-like links
                links = await page.evaluate("""() => {
                    const links = [...document.querySelectorAll('a[href]')].map(a => a.href)
                    return [...new Set(links)].filter(l => l.startsWith('http')).slice(0, 50)
                }""")
                trace["article_links"] = links[:50]
                
            except Exception as e:
                trace["error"] = str(e)
            
            await browser.close()
        
        results[kw] = trace
    
    return results


# ── 2. Leakage Diff Harness ─────────────────────────────────────────────────

async def leakage_diff(
    search_url_template: str,
    positive_kw: str = "ekonomi",
    different_kw: str = "olahraga",
    nonsense_kw: str = "xyznonexistent999zzz",
    article_patterns: List[str] = None,
    headers: Dict = None,
    timeout: int = 15,
) -> Dict:
    """Compare search results across positive/different/nonsense keywords.
    
    Detects whether a source leaks fallback/generic results for nonsense keywords
    or returns the same results regardless of query.
    """
    article_patterns = article_patterns or ARTICLE_PATTERNS
    compiled = [re.compile(p) for p in article_patterns]
    
    async def fetch_links(keyword: str) -> Set[str]:
        url = search_url_template.replace("{keyword}", keyword)
        try:
            async with aiohttp.ClientSession() as session:
                hdrs = headers or {"User-Agent": "Mozilla/5.0"}
                async with session.get(url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                links = set()
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = urljoin(url, href)
                    if any(p.search(href) for p in compiled):
                        links.add(href)
                return links
        except Exception as e:
            logger.debug(f"leakage_diff fetch failed for '{keyword}': {e}")
            return set()
    
    positive_links = await fetch_links(positive_kw)
    different_links = await fetch_links(different_kw)
    nonsense_links = await fetch_links(nonsense_kw)
    
    p_d_overlap = positive_links & different_links
    p_n_overlap = positive_links & nonsense_links
    
    p_d_ratio = len(p_d_overlap) / min(len(positive_links), len(different_links)) if positive_links and different_links else 0
    p_n_ratio = len(p_n_overlap) / len(positive_links) if positive_links else 0
    
    result = {
        "positive_kw": positive_kw,
        "positive_count": len(positive_links),
        "different_kw": different_kw,
        "different_count": len(different_links),
        "nonsense_kw": nonsense_kw,
        "nonsense_count": len(nonsense_links),
        "positive_vs_different_overlap": len(p_d_overlap),
        "positive_vs_different_ratio": round(p_d_ratio, 3),
        "positive_vs_nonsense_overlap": len(p_n_overlap),
        "positive_vs_nonsense_ratio": round(p_n_ratio, 3),
        "is_query_dependent": p_d_ratio < 0.5 and len(nonsense_links) == 0,
        "has_nonsense_leakage": len(nonsense_links) > 0,
        "has_generic_fallback": p_d_ratio > 0.7,
        "positive_sample": sorted(list(positive_links))[:3],
        "different_sample": sorted(list(different_links))[:3],
        "nonsense_sample": sorted(list(nonsense_links))[:3],
    }
    
    return result


# ── 3. Search Surface Discovery Harness ─────────────────────────────────────

SEARCH_ENDPOINTS = [
    "/search?q={keyword}",
    "/search?query={keyword}",
    "/cari?q={keyword}",
    "/cari?query={keyword}",
    "/tag/{keyword}",
    "/tags/{keyword}",
    "/topic/{keyword}",
    "/topic?q={keyword}",
    "/api/search?q={keyword}",
    "/api/v1/search?q={keyword}",
    "/api/search?query={keyword}",
    "/artikel?q={keyword}",
    "/berita?q={keyword}",
    "/?s={keyword}",
    "/search/{keyword}",
    "/news/search?q={keyword}",
    "/pencarian?q={keyword}",
]


async def search_surface_discovery(
    base_url: str,
    keyword: str = "ekonomi",
    nonsense_keyword: str = "xyznonexistent999zzz",
    article_patterns: List[str] = None,
    headers: Dict = None,
    timeout: int = 10,
) -> List[Dict]:
    """Probe common search endpoint patterns against a base URL.
    
    Returns ranked list of candidate endpoints that return article links.
    Endpoints where nonsense returns zero are ranked highest.
    """
    article_patterns = article_patterns or ARTICLE_PATTERNS
    compiled = [re.compile(p) for p in article_patterns]
    hdrs = headers or {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    candidates = []
    
    async def check_endpoint(template: str, kw: str) -> Set[str]:
        url = base_url.rstrip("/") + template.replace("{keyword}", kw)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                links = set()
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = urljoin(url, href)
                    if any(p.search(href) for p in compiled):
                        links.add(href)
                return links
        except Exception:
            return set()
    
    for endpoint in SEARCH_ENDPOINTS:
        pos_links = await check_endpoint(endpoint, keyword)
        nons_links = await check_endpoint(endpoint, nonsense_keyword)
        
        if not pos_links:
            continue
        
        score = len(pos_links)
        is_strict = len(nons_links) == 0
        if is_strict:
            score += 1000  # bonus for strict search
        
        candidates.append({
            "endpoint": endpoint,
            "url": base_url.rstrip("/") + endpoint.replace("{keyword}", keyword),
            "positive_links": len(pos_links),
            "nonsense_links": len(nons_links),
            "is_strict": is_strict,
            "score": score,
            "sample": sorted(list(pos_links))[:2],
        })
    
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates
