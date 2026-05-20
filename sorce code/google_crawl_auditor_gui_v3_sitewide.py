#!/usr/bin/env python3
"""
Google Crawl Auditor - SEO Team Edition v3

What is new in this version
---------------------------
1) Sitewide audits: crawl a full website (home page + sitemap + internal links)
2) Better SEO-team output: charts, grouped issues, actions, and sample URLs
3) Latest Google-aligned crawl/index checks (public guidance up to Mar/Apr 2026)
   - mobile-first indexing parity checks
   - 2 MB Googlebot fetch limit for text-based files/resources
   - file type / content-type sanity checks
   - crawlable href links vs buttons / infinite scroll traps
   - JavaScript rendering clues and blocked resources
   - parameter/faceted/search URL management clues

Dependencies:
    pip install requests beautifulsoup4

Run:
    python google_crawl_auditor_gui_v3_sitewide.py
"""

from __future__ import annotations

import csv
import gzip
import html
import io
import json
import queue
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qsl, unquote, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Google Crawl Auditor - SEO Team Edition v3"
REQUEST_TIMEOUT = 18
MAX_RESOURCE_CHECKS = 10
MAX_SITEMAP_FILES = 12
MAX_SITEMAP_URLS = 400
MAX_SITE_PAGES_DEFAULT = 40
MAX_PAGES_ALLOWED = 200

USER_AGENT = "Mozilla/5.0 (compatible; GoogleCrawlAuditorSEO/3.0; +https://example.com/bot)"
DESKTOP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
GOOGLEBOT_SMARTPHONE_UA = (
    "Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
COMMON_SITEMAPS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap.txt",
]
TEXT_BASED_INDEXABLE_CONTENT_HINTS = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "application/pdf",
)
SOFT_404_PATTERNS = [
    "page not found",
    "404 not found",
    "not found",
    "sorry, the page",
    "doesn't exist",
    "does not exist",
    "no longer available",
    "error 404",
    "product not found",
    "no products found",
]
NON_HTML_FILE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".css", ".js", ".mjs", ".json", ".xml", ".pdf", ".zip", ".gz", ".mp4",
    ".mov", ".avi", ".webm", ".mp3", ".wav", ".woff", ".woff2", ".ttf", ".eot",
    ".xlsx", ".xls", ".csv", ".doc", ".docx", ".ppt", ".pptx",
}
BLOCKING_TOKENS = {
    "noindex": "Google has been told not to index this page.",
    "nofollow": "Google has been told not to follow links from this page.",
    "none": "Equivalent to noindex,nofollow.",
    "nosnippet": "Search snippets are restricted.",
    "noarchive": "Cached copy is disabled.",
    "unavailable_after": "The page has an expiry rule for indexing.",
}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
SEVERITY_COLORS = {
    "CRITICAL": "#c62828",
    "HIGH": "#ef6c00",
    "MEDIUM": "#f9a825",
    "LOW": "#6d6d6d",
    "INFO": "#2e7d32",
}
SEVERITY_PENALTIES = {"CRITICAL": 30, "HIGH": 18, "MEDIUM": 10, "LOW": 4, "INFO": 0}
PAGINATION_PATTERNS = [
    re.compile(r"[?&](page|p|paged)=\d+", re.I),
    re.compile(r"/page/\d+/?$", re.I),
]
FACET_QUERY_HINTS = [
    "filter", "sort", "order", "color", "size", "brand", "price", "query", "search",
    "q", "technique", "tissue", "material", "category", "collection", "page",
]
SUPPORTED_FILE_EXTENSIONS_FOR_INDEX = {
    ".html", ".htm", ".txt", ".xml", ".pdf", ".csv", ".rtf", ".doc", ".docx",
    ".ppt", ".pptx", ".xls", ".xlsx",
}


@dataclass
class Finding:
    severity: str
    title: str
    details: str
    why_it_matters: str
    what_to_do: str
    owner: str
    category: str
    sample_urls: List[str] = field(default_factory=list)


@dataclass
class PageAuditResult:
    input_url: str
    normalized_url: str = ""
    final_url: str = ""
    final_status: Optional[int] = None
    response_time_ms: Optional[int] = None
    content_type: str = ""
    content_bytes: int = 0
    https_ok: Optional[bool] = None
    robots_url: str = ""
    robots_status: Optional[int] = None
    robots_accessible: Optional[bool] = None
    robots_allows_page: Optional[bool] = None
    sitemap_urls: List[str] = field(default_factory=list)
    sitemap_accessible: Optional[bool] = None
    meta_robots: str = ""
    x_robots_tag: str = ""
    canonical: str = ""
    canonical_status: Optional[int] = None
    canonical_same_domain: Optional[bool] = None
    title_text: str = ""
    meta_description: str = ""
    viewport_present: Optional[bool] = None
    page_type: str = "General page"
    text_length: int = 0
    script_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    crawlable_internal_link_count: int = 0
    css_js_checked: int = 0
    css_js_blocked_or_broken: int = 0
    mobile_desktop_mismatch: bool = False
    mobile_test_run: bool = False
    indexability: str = ""
    verdict: str = ""
    score: int = 100
    summary: str = ""
    executive_summary: str = ""
    top_actions: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    discovered_internal_urls: List[str] = field(default_factory=list)
    error: str = ""

    def add(
        self,
        severity: str,
        title: str,
        details: str,
        why_it_matters: str,
        what_to_do: str,
        owner: str,
        category: str,
        sample_urls: Optional[List[str]] = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                title=title,
                details=details,
                why_it_matters=why_it_matters,
                what_to_do=what_to_do,
                owner=owner,
                category=category,
                sample_urls=list(sample_urls or []),
            )
        )


@dataclass
class SiteAuditResult:
    input_url: str
    normalized_url: str = ""
    final_site_url: str = ""
    mode: str = "site"
    site_domain: str = ""
    pages_requested_limit: int = 0
    pages_crawled: int = 0
    html_pages_crawled: int = 0
    pages_indexable: int = 0
    pages_noindex: int = 0
    pages_disallowed: int = 0
    pages_error: int = 0
    pages_redirected: int = 0
    pages_over_2mb: int = 0
    pages_mobile_mismatch: int = 0
    pages_js_heavy: int = 0
    pages_missing_viewport: int = 0
    pages_missing_title: int = 0
    pages_missing_canonical: int = 0
    pages_with_parameter_urls: int = 0
    sitewide_findings: List[Finding] = field(default_factory=list)
    page_results: List[PageAuditResult] = field(default_factory=list)
    score: int = 100
    verdict: str = ""
    indexability: str = ""
    summary: str = ""
    executive_summary: str = ""
    top_actions: List[str] = field(default_factory=list)
    crawl_notes: List[str] = field(default_factory=list)
    error: str = ""

    def add(self, finding: Finding) -> None:
        self.sitewide_findings.append(finding)


@dataclass
class RobotsContext:
    base_url: str
    robots_url: str
    robots_status: Optional[int] = None
    robots_accessible: Optional[bool] = None
    text: str = ""
    parser: RobotFileParser = field(default_factory=RobotFileParser)
    sitemap_urls: List[str] = field(default_factory=list)
    sitemap_accessible: Optional[bool] = None


AuditAnyResult = Union[PageAuditResult, SiteAuditResult]


class CrawlAuditor:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # -----------------------------
    # public entry points
    # -----------------------------
    def audit_page(self, raw_url: str, shared_robots: Optional[RobotsContext] = None, run_mobile_check: bool = True) -> PageAuditResult:
        result = PageAuditResult(input_url=raw_url.strip())
        try:
            url = self._normalize_url(raw_url)
            result.normalized_url = url
            result.page_type = self._infer_page_type(url)
            parsed = urlparse(url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            result.robots_url = urljoin(base, "/robots.txt")

            start = time.perf_counter()
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            elapsed = time.perf_counter() - start
            result.response_time_ms = int(elapsed * 1000)
            result.final_status = response.status_code
            result.final_url = response.url
            result.https_ok = result.final_url.startswith("https://")
            result.content_type = response.headers.get("Content-Type", "")
            result.content_bytes = len(response.content or b"")
            result.page_type = self._infer_page_type(result.final_url)

            robots = shared_robots or self._load_robots_context(base)
            result.robots_status = robots.robots_status
            result.robots_accessible = robots.robots_accessible
            result.sitemap_urls = robots.sitemap_urls[:]
            result.sitemap_accessible = robots.sitemap_accessible

            self._check_redirects(result, response)
            self._check_status_code(result, response)
            self._check_ssl_and_scheme(result)
            self._check_robots(result, response, robots)
            self._check_content_type_and_size(result, response)
            self._check_page_directives(result, response)
            self._check_canonical(result, response)
            self._check_meta_and_mobile_basics(result, response)
            self._check_content_clues(result, response)
            self._check_links(result, response)
            self._check_resources(result, response, robots)
            self._check_url_pattern_guidance(result)
            self._check_pagination_and_incremental_loading(result, response)
            if run_mobile_check and self._is_html_response(response) and result.final_status == 200:
                self._check_mobile_first_parity(result, response)
            self._calculate_page_score(result)
            self._build_page_summary(result)
        except requests.exceptions.SSLError as e:
            result.error = f"SSL/TLS error: {e}"
            result.add(
                "CRITICAL",
                "SSL/TLS connection failed",
                "The HTTPS connection could not be established.",
                "If the secure version of the site cannot be fetched reliably, Google may struggle to crawl it.",
                "Fix the certificate chain, hostname coverage, and TLS configuration. Test the final HTTPS URL from a browser and the server directly.",
                "Developer / DevOps",
                "Infrastructure",
            )
            self._calculate_page_score(result)
            self._build_page_summary(result)
        except requests.exceptions.ConnectionError as e:
            result.error = f"Connection error: {e}"
            result.add(
                "CRITICAL",
                "Connection failed",
                "The page could not be reached from the checker.",
                "If the URL cannot be reached publicly, Googlebot may also fail to fetch it.",
                "Check DNS, firewall rules, CDN rules, origin availability, and whether the site blocks some countries or user agents.",
                "Developer / DevOps",
                "Infrastructure",
            )
            self._calculate_page_score(result)
            self._build_page_summary(result)
        except requests.exceptions.Timeout:
            result.error = "Timed out while loading the page."
            result.add(
                "HIGH",
                "Page timed out",
                "The page took too long to respond.",
                "Slow pages can reduce crawl efficiency and may lead to failed fetches.",
                "Improve server response time, caching, and upstream stability. Re-test the page and similar templates.",
                "Developer / DevOps",
                "Performance",
            )
            self._calculate_page_score(result)
            self._build_page_summary(result)
        except Exception as e:  # noqa: BLE001
            result.error = str(e)
            result.add(
                "CRITICAL",
                "Unexpected audit error",
                str(e),
                "The audit could not complete cleanly.",
                "Review the URL and retry. If this repeats across many URLs, inspect the app logs and the site response format.",
                "Developer",
                "Tooling",
            )
            self._calculate_page_score(result)
            self._build_page_summary(result)
        return result

    def audit_site(self, raw_url: str, max_pages: int = MAX_SITE_PAGES_DEFAULT, stop_checker: Optional[callable] = None) -> SiteAuditResult:
        site = SiteAuditResult(input_url=raw_url.strip(), pages_requested_limit=max(1, min(MAX_PAGES_ALLOWED, int(max_pages))))
        try:
            home = self._normalize_url(raw_url)
            site.normalized_url = home
            parsed = urlparse(home)
            base = f"{parsed.scheme}://{parsed.netloc}"
            site.final_site_url = base
            site.site_domain = parsed.netloc.lower()
            robots = self._load_robots_context(base)

            seed_urls: List[str] = [home]
            if robots.sitemap_urls:
                sitemap_urls = self._collect_sitemap_urls(base, robots.sitemap_urls)
                if sitemap_urls:
                    seed_urls.extend(sitemap_urls)
                    site.crawl_notes.append(f"Loaded {len(sitemap_urls)} URL(s) from sitemap files.")
                else:
                    site.crawl_notes.append("Sitemap files were found, but no same-domain URLs were extracted.")
            else:
                site.crawl_notes.append("No sitemap discovered in robots.txt or common sitemap paths.")

            queue_urls: List[str] = []
            seen_queue: Set[Tuple[str, str, str, Tuple[Tuple[str, str], ...]]] = set()
            for u in seed_urls:
                self._queue_unique_url(queue_urls, seen_queue, u, site.site_domain)

            crawled_signatures: Set[Tuple[str, str, str, Tuple[Tuple[str, str], ...]]] = set()
            crawl_round = 0
            while queue_urls and site.pages_crawled < site.pages_requested_limit:
                if stop_checker and stop_checker():
                    site.crawl_notes.append("Stopped early by user request.")
                    break
                target = queue_urls.pop(0)
                sig = self._url_signature(target)
                if sig in crawled_signatures:
                    continue
                crawl_round += 1
                run_mobile_check = crawl_round <= min(8, site.pages_requested_limit)
                page = self.audit_page(target, shared_robots=robots, run_mobile_check=run_mobile_check)
                site.page_results.append(page)
                crawled_signatures.add(sig)
                site.pages_crawled += 1

                if self._is_probably_html_page_result(page):
                    site.html_pages_crawled += 1
                if page.final_status and 300 <= page.final_status < 400:
                    site.pages_redirected += 1
                if page.final_status and page.final_status >= 400:
                    site.pages_error += 1
                if self._page_has_noindex(page):
                    site.pages_noindex += 1
                if page.robots_allows_page is False:
                    site.pages_disallowed += 1
                if page.indexability == "Probably indexable":
                    site.pages_indexable += 1
                if page.content_bytes > 2 * 1024 * 1024:
                    site.pages_over_2mb += 1
                if page.mobile_desktop_mismatch:
                    site.pages_mobile_mismatch += 1
                if any(f.title == "JavaScript-heavy shell page" for f in page.findings):
                    site.pages_js_heavy += 1
                if page.viewport_present is False:
                    site.pages_missing_viewport += 1
                if not page.title_text:
                    site.pages_missing_title += 1
                if not page.canonical:
                    site.pages_missing_canonical += 1
                if urlparse(page.normalized_url).query:
                    site.pages_with_parameter_urls += 1

                for discovered in page.discovered_internal_urls:
                    self._queue_unique_url(queue_urls, seen_queue, discovered, site.site_domain)

            self._aggregate_site_findings(site, robots)
            self._calculate_site_score(site)
            self._build_site_summary(site)
        except Exception as e:  # noqa: BLE001
            site.error = str(e)
            site.add(
                Finding(
                    severity="CRITICAL",
                    title="Site audit failed",
                    details=str(e),
                    why_it_matters="The sitewide crawl could not finish cleanly.",
                    what_to_do="Retry the crawl. If this repeats, test the homepage manually and check whether the site blocks automated requests or has unstable responses.",
                    owner="Developer / DevOps",
                    category="Tooling",
                )
            )
            self._calculate_site_score(site)
            self._build_site_summary(site)
        return site

    # -----------------------------
    # utilities
    # -----------------------------
    def _normalize_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url:
            raise ValueError("Empty URL")
        if not re.match(r"^https?://", url, flags=re.I):
            url = "https://" + url
        return url

    def _is_html_response(self, response: requests.Response) -> bool:
        return "html" in (response.headers.get("Content-Type", "").lower())

    def _is_probably_html_page_result(self, page: PageAuditResult) -> bool:
        return "html" in page.content_type.lower() or page.page_type in {"Homepage", "General page", "Category / listing page", "Search / filtered results page"}

    def _fetch(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        try:
            return self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, headers=headers)
        except Exception:
            return None

    def _extract_directives(self, raw: str) -> List[str]:
        directives: List[str] = []
        for piece in raw.split(","):
            p = piece.strip().lower()
            if p:
                directives.append(p)
        return directives

    def _url_signature(self, url: str) -> Tuple[str, str, str, Tuple[Tuple[str, str], ...]]:
        p = urlparse(url)
        query = tuple(sorted((unquote(k), unquote(v)) for k, v in parse_qsl(p.query, keep_blank_values=True)))
        path = unquote((p.path or "/").rstrip("/") or "/")
        return p.scheme.lower(), p.netloc.lower(), path, query

    def _same_semantic_url(self, left: str, right: str) -> bool:
        return self._url_signature(left) == self._url_signature(right)

    def _base_url(self, url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    def _same_domain(self, url: str, domain: str) -> bool:
        return urlparse(url).netloc.lower() == domain.lower()

    def _clean_url_for_display(self, url: str) -> str:
        if len(url) <= 120:
            return url
        return url[:117] + "..."

    def _infer_page_type(self, url: str) -> str:
        p = urlparse(url)
        path = (p.path or "").lower()
        query = (p.query or "").lower()
        if path in {"", "/"}:
            return "Homepage"
        if "search" in path or any(token in query for token in ["filter", "q=", "query=", "search="]):
            return "Search / filtered results page"
        if any(token in path for token in ["/category", "/categories", "/collections", "/catalog", "/shop", "/products", "/collection"]):
            return "Category / listing page"
        return "General page"

    def _load_robots_context(self, base_url: str) -> RobotsContext:
        robots_url = urljoin(base_url, "/robots.txt")
        ctx = RobotsContext(base_url=base_url, robots_url=robots_url)
        resp = self._fetch(robots_url)
        if resp is None:
            ctx.robots_accessible = False
            return ctx
        ctx.robots_status = resp.status_code
        ctx.robots_accessible = resp.status_code == 200
        if resp.status_code == 200:
            ctx.text = resp.text
            ctx.parser.parse(resp.text.splitlines())
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm = line.split(":", 1)[1].strip()
                    if sm:
                        ctx.sitemap_urls.append(sm)
        if not ctx.sitemap_urls:
            for path in COMMON_SITEMAPS:
                sm_url = urljoin(base_url, path)
                sm_resp = self._fetch(sm_url)
                if sm_resp is not None and sm_resp.status_code == 200:
                    ctx.sitemap_urls.append(sm_url)
        if ctx.sitemap_urls:
            ctx.sitemap_accessible = any((self._fetch(sm) is not None and self._fetch(sm).status_code == 200) for sm in ctx.sitemap_urls[:3])
        return ctx

    def _queue_unique_url(
        self,
        queue_urls: List[str],
        seen_queue: Set[Tuple[str, str, str, Tuple[Tuple[str, str], ...]]],
        url: str,
        domain: str,
    ) -> None:
        if not url:
            return
        try:
            absolute = self._normalize_url(url)
        except Exception:
            return
        if not self._same_domain(absolute, domain):
            return
        parsed = urlparse(absolute)
        if any(parsed.path.lower().endswith(ext) for ext in NON_HTML_FILE_EXTENSIONS):
            return
        cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))
        sig = self._url_signature(cleaned)
        if sig in seen_queue:
            return
        seen_queue.add(sig)
        queue_urls.append(cleaned)

    def _collect_sitemap_urls(self, base_url: str, sitemap_urls: List[str]) -> List[str]:
        discovered: List[str] = []
        sitemap_queue = sitemap_urls[:MAX_SITEMAP_FILES]
        seen_sitemaps: Set[str] = set()
        domain = urlparse(base_url).netloc.lower()
        while sitemap_queue and len(seen_sitemaps) < MAX_SITEMAP_FILES and len(discovered) < MAX_SITEMAP_URLS:
            sm = sitemap_queue.pop(0)
            if sm in seen_sitemaps:
                continue
            seen_sitemaps.add(sm)
            resp = self._fetch(sm)
            if resp is None or resp.status_code != 200:
                continue
            content = resp.content
            try:
                if sm.endswith(".gz"):
                    content = gzip.decompress(content)
            except Exception:
                pass
            urls, child_maps = self._parse_sitemap_bytes(content, sm)
            for u in urls:
                if self._same_domain(u, domain):
                    discovered.append(u)
                    if len(discovered) >= MAX_SITEMAP_URLS:
                        break
            for child in child_maps:
                if child not in seen_sitemaps and len(seen_sitemaps) + len(sitemap_queue) < MAX_SITEMAP_FILES:
                    sitemap_queue.append(child)
        unique = []
        seen = set()
        for u in discovered:
            sig = self._url_signature(u)
            if sig not in seen:
                unique.append(u)
                seen.add(sig)
        return unique[:MAX_SITEMAP_URLS]

    def _parse_sitemap_bytes(self, content: bytes, source_url: str) -> Tuple[List[str], List[str]]:
        try:
            root = ET.fromstring(content)
        except Exception:
            text = content.decode("utf-8", errors="ignore")
            urls = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://"):
                    urls.append(line)
            return urls, []

        urls: List[str] = []
        child_maps: List[str] = []
        for elem in root.iter():
            tag = elem.tag.lower().split("}")[-1]
            if tag == "loc" and elem.text:
                loc = elem.text.strip()
                parent = elem.getparent() if hasattr(elem, "getparent") else None
                # fallback: infer by root tag only
                if root.tag.lower().endswith("sitemapindex"):
                    child_maps.append(loc)
                elif root.tag.lower().endswith("urlset"):
                    urls.append(loc)
                else:
                    # best effort: sitemap files ending xml in loc become child maps, otherwise URLs
                    if loc.lower().endswith(".xml") or loc.lower().endswith(".xml.gz"):
                        child_maps.append(loc)
                    else:
                        urls.append(loc)
        return urls, child_maps

    # -----------------------------
    # page checks
    # -----------------------------
    def _check_redirects(self, result: PageAuditResult, response: requests.Response) -> None:
        if response.history:
            chain = " -> ".join([str(r.status_code) for r in response.history] + [str(response.status_code)])
            result.add(
                "INFO",
                "Redirect chain detected",
                f"Redirect chain: {chain}. Final URL: {response.url}",
                "Redirects are normal, but long chains slow down crawling and waste crawl budget.",
                "Keep redirects short. Ideally one hop from old URL to final destination.",
                "Developer / SEO",
                "Crawling",
            )
            if len(response.history) >= 4:
                result.add(
                    "MEDIUM",
                    "Long redirect chain",
                    f"This URL needed {len(response.history)} redirects before landing on the final page.",
                    "Multiple redirect hops slow crawling and can reduce how efficiently Google discovers the final page.",
                    "Update internal links, canonicals, sitemap URLs, and redirects so important URLs go directly to the final destination.",
                    "Developer / SEO",
                    "Crawling",
                )

    def _check_status_code(self, result: PageAuditResult, response: requests.Response) -> None:
        code = response.status_code
        if code >= 500:
            result.add(
                "CRITICAL",
                "Server error on page",
                f"The final page returned HTTP {code}.",
                "Google cannot index a page reliably when the server fails to deliver it.",
                "Fix the server error, then re-test the page and check whether the same template fails on other URLs.",
                "Developer / DevOps",
                "Infrastructure",
            )
        elif code in (401, 403):
            result.add(
                "CRITICAL",
                "Access blocked",
                f"The final page returned HTTP {code}.",
                "Googlebot may be blocked from crawling the page.",
                "Remove unintended access restrictions for publicly indexable pages. Review CDN, firewall, bot rules, auth, and geoblocking.",
                "Developer / DevOps",
                "Access",
            )
        elif code >= 400:
            result.add(
                "HIGH",
                "Client error on page",
                f"The final page returned HTTP {code}.",
                "Error pages are generally not indexable and can waste crawl effort if linked internally.",
                "Fix the broken URL, redirect it, or remove it from internal links and sitemaps.",
                "Developer / SEO",
                "Indexing",
            )
        elif code in (200, 204):
            result.add(
                "INFO",
                "Page reachable",
                f"The final page returned HTTP {code}.",
                "This is the normal response for a page that can be crawled.",
                "No action needed.",
                "SEO",
                "Crawling",
            )
        elif 300 <= code < 400:
            result.add(
                "MEDIUM",
                "Page ended on redirect",
                f"The final fetch ended with HTTP {code} rather than a normal page response.",
                "Important URLs should normally resolve to a final 200 page.",
                "Make sure this URL is not the one listed in internal links, canonicals, or XML sitemaps if it still redirects.",
                "SEO / Developer",
                "Crawling",
            )

    def _check_ssl_and_scheme(self, result: PageAuditResult) -> None:
        if result.final_url.startswith("https://"):
            result.add(
                "INFO",
                "HTTPS enabled",
                "The final URL uses HTTPS.",
                "Google expects modern websites to be accessible securely.",
                "No action needed.",
                "SEO",
                "Infrastructure",
            )
        else:
            result.add(
                "HIGH",
                "HTTPS not used",
                "The final URL is not HTTPS.",
                "This is not always a hard crawl blocker, but it is a trust and duplicate-version risk.",
                "Serve the site on HTTPS and redirect HTTP to HTTPS consistently.",
                "Developer / DevOps",
                "Infrastructure",
            )

    def _check_robots(self, result: PageAuditResult, response: requests.Response, robots: RobotsContext) -> None:
        if robots.robots_status == 200:
            result.robots_allows_page = robots.parser.can_fetch("Googlebot", response.url)
            if result.robots_allows_page:
                result.add(
                    "INFO",
                    "Page allowed in robots.txt",
                    "The tested page appears crawlable for Googlebot according to robots.txt.",
                    "This means robots.txt is not currently blocking this page.",
                    "No action needed.",
                    "SEO",
                    "Crawling",
                )
            else:
                result.add(
                    "CRITICAL",
                    "Page disallowed in robots.txt",
                    "robots.txt appears to block Googlebot from the tested URL.",
                    "If Googlebot is blocked here, it may not be able to crawl the content at all.",
                    "Remove or relax the disallow rule for URLs that should be crawlable. Re-test the exact URL pattern after the change.",
                    "Developer / SEO",
                    "Crawling",
                )

            if robots.sitemap_urls:
                result.add(
                    "INFO",
                    "Sitemap declared or discovered",
                    f"Found {len(robots.sitemap_urls)} sitemap file(s).",
                    "Sitemaps help Google discover important URLs faster.",
                    "No action needed unless the sitemap itself is broken.",
                    "SEO",
                    "Discovery",
                )
            else:
                result.add(
                    "MEDIUM",
                    "No sitemap found",
                    "No sitemap was declared in robots.txt or found at common paths.",
                    "Google can still crawl through links, but new or deep pages may be discovered more slowly.",
                    "Publish an XML sitemap with canonical 200 URLs and reference it in robots.txt.",
                    "SEO / Developer",
                    "Discovery",
                )

        elif robots.robots_status in (401, 403):
            result.add(
                "HIGH",
                "robots.txt blocked",
                f"robots.txt returned HTTP {robots.robots_status}.",
                "Blocking access to robots.txt can create crawler confusion and often points to access control issues.",
                "Allow public access to /robots.txt and make sure it returns a stable 200 response.",
                "Developer / DevOps",
                "Crawling",
            )
        elif robots.robots_status and robots.robots_status >= 500:
            result.add(
                "HIGH",
                "robots.txt server error",
                f"robots.txt returned HTTP {robots.robots_status}.",
                "If robots.txt fails intermittently, crawling instructions become unreliable.",
                "Fix the origin or CDN issue serving robots.txt and keep it available at all times.",
                "Developer / DevOps",
                "Infrastructure",
            )
        elif robots.robots_status is None:
            result.add(
                "MEDIUM",
                "robots.txt unreachable",
                "The robots.txt file could not be loaded.",
                "Google can still crawl without robots.txt, but if the file is supposed to exist and cannot be fetched, that may indicate infrastructure issues.",
                "Check whether /robots.txt is publicly available and fast. Make sure the CDN or origin is not blocking it.",
                "Developer / DevOps",
                "Crawling",
            )
        else:
            result.add(
                "LOW",
                "robots.txt not found",
                f"robots.txt returned HTTP {robots.robots_status}.",
                "A site can still be crawled without robots.txt, but explicit crawler guidance is missing.",
                "Consider adding a basic robots.txt and include the sitemap location.",
                "SEO / Developer",
                "Crawling",
            )

        if robots.sitemap_urls:
            if robots.sitemap_accessible:
                result.add(
                    "INFO",
                    "Sitemap reachable",
                    "At least one sitemap URL could be fetched successfully.",
                    "That supports faster URL discovery.",
                    "No action needed.",
                    "SEO",
                    "Discovery",
                )
            else:
                result.add(
                    "HIGH",
                    "Sitemap unreachable",
                    "Sitemap URLs were found, but the checked sitemap files could not be fetched successfully.",
                    "A broken sitemap sends Google to URLs it cannot retrieve.",
                    "Fix the sitemap URL, server access, or CDN rules. Then resubmit the sitemap in Search Console.",
                    "Developer / SEO",
                    "Discovery",
                )

    def _check_content_type_and_size(self, result: PageAuditResult, response: requests.Response) -> None:
        ctype = response.headers.get("Content-Type", "").lower()
        result.content_type = response.headers.get("Content-Type", "")
        size = len(response.content or b"")
        result.content_bytes = size

        if size > 2 * 1024 * 1024 and "pdf" not in ctype:
            result.add(
                "MEDIUM",
                "Page exceeds Google's 2 MB fetch limit",
                f"Downloaded content size is about {size / (1024 * 1024):.2f} MB.",
                "Googlebot only processes the first part of oversized text-based files for indexing consideration, which can cut off important content or links.",
                "Reduce HTML bloat, inline data, excessive embedded JSON, and oversized script/style blocks. Keep important content and links early in the HTML.",
                "Developer / SEO",
                "Rendering",
            )
        elif size > 0 and size <= 2 * 1024 * 1024:
            result.add(
                "INFO",
                "Page is within Google's 2 MB fetch window",
                f"Downloaded content size is about {size / 1024:.0f} KB.",
                "This reduces the risk of Googlebot truncating the fetched HTML for indexing consideration.",
                "No action needed.",
                "Developer",
                "Rendering",
            )

        path = urlparse(response.url).path.lower()
        ext = "." + path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
        if ext and ext in SUPPORTED_FILE_EXTENSIONS_FOR_INDEX and not any(h in ctype for h in TEXT_BASED_INDEXABLE_CONTENT_HINTS):
            result.add(
                "MEDIUM",
                "Suspicious Content-Type for indexable file",
                f"URL extension suggests an indexable document ({ext}) but the server returned Content-Type '{result.content_type or 'unknown'}'.",
                "Google relies primarily on the Content-Type header when understanding file formats. Incorrect headers can confuse indexing expectations.",
                "Serve the correct Content-Type header for the file or page template.",
                "Developer / DevOps",
                "Indexing",
            )

    def _check_page_directives(self, result: PageAuditResult, response: requests.Response) -> None:
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            if any(h in content_type.lower() for h in TEXT_BASED_INDEXABLE_CONTENT_HINTS):
                result.add(
                    "INFO",
                    "Non-HTML but indexable file type",
                    f"Content-Type is '{content_type}'.",
                    "Google can index many text-based files, not just HTML pages.",
                    "No action needed if this URL is intentionally a document or feed.",
                    "SEO",
                    "Indexing",
                )
            else:
                result.add(
                    "HIGH",
                    "Page is not HTML",
                    f"Content-Type is '{content_type}'.",
                    "This is unusual for a normal webpage and may affect indexing expectations.",
                    "Confirm that this URL is meant to be an HTML page. If it should be a page, return HTML with the correct content type.",
                    "Developer",
                    "Rendering",
                )
            return

        soup = BeautifulSoup(response.text, "html.parser")
        robots_values = []
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("http-equiv") or "").strip().lower()
            content = (meta.get("content") or "").strip()
            if name in {"robots", "googlebot", "googlebot-news"} and content:
                robots_values.append(f"{name}: {content}")
                for directive in self._extract_directives(content):
                    if directive not in BLOCKING_TOKENS:
                        continue
                    sev = "CRITICAL" if directive in {"noindex", "none"} else "MEDIUM"
                    result.add(
                        sev,
                        f"Meta robots contains {directive}",
                        f"Found '{name}: {content}'.",
                        BLOCKING_TOKENS[directive],
                        self._recommend_for_directive(result, directive, source="meta"),
                        self._owner_for_directive(directive),
                        "Indexing",
                    )
        result.meta_robots = " | ".join(robots_values)

        x_robots = response.headers.get("X-Robots-Tag", "")
        result.x_robots_tag = x_robots
        if x_robots:
            for directive in self._extract_directives(x_robots):
                if directive not in BLOCKING_TOKENS:
                    continue
                sev = "CRITICAL" if directive in {"noindex", "none"} else "MEDIUM"
                result.add(
                    sev,
                    f"X-Robots-Tag contains {directive}",
                    f"Found X-Robots-Tag: {x_robots}.",
                    BLOCKING_TOKENS[directive],
                    self._recommend_for_directive(result, directive, source="header"),
                    self._owner_for_directive(directive),
                    "Indexing",
                )

        if result.robots_allows_page is False and self._page_has_noindex(result):
            result.add(
                "HIGH",
                "Blocked page also uses noindex",
                "The page is blocked in robots.txt and also contains a noindex directive.",
                "When a page is blocked by robots.txt, Google may not reliably see the noindex directive, which creates confusing signals.",
                "Decide which control you actually want. Usually: allow crawling and use noindex, or remove noindex and keep the page crawlable if you want Google to process the directive.",
                "SEO / Developer",
                "Indexing",
            )

    def _recommend_for_directive(self, result: PageAuditResult, directive: str, source: str) -> str:
        source_name = "meta robots tag" if source == "meta" else "X-Robots-Tag header"
        if directive == "noindex":
            if result.page_type == "Search / filtered results page":
                return (
                    f"This often looks intentional on search or faceted URLs. Keep the {source_name} only if you do NOT want these filtered pages in Google. "
                    f"If this page should rank, remove the noindex from the {source_name} and make sure it has a self-canonical, internal links, and useful unique content."
                )
            return (
                f"Remove the noindex from the {source_name} if this page is meant to appear in Google. "
                f"After publishing the change, request reindexing in Search Console and verify the page is not blocked elsewhere."
            )
        if directive == "nofollow":
            return f"Remove nofollow from the {source_name} if you want Google to use links on this page for discovery and signal flow."
        if directive == "none":
            return f"Replace 'none' with the exact directive you actually want. If the page should rank, remove it from the {source_name}."
        if directive == "nosnippet":
            return "Keep this only if you intentionally want limited SERP snippets. Remove it if you want normal search snippets."
        if directive == "noarchive":
            return "Usually safe to keep. Remove it only if you want Google to be allowed to show cached copies."
        if directive == "unavailable_after":
            return "Check whether the expiry date is still correct. Remove or update it if the page should stay eligible for search."
        return "Review whether this directive is intentional. Remove it if it blocks your SEO goal for this page."

    def _owner_for_directive(self, directive: str) -> str:
        if directive in {"noindex", "nofollow", "none", "nosnippet", "noarchive", "unavailable_after"}:
            return "SEO / Developer"
        return "SEO"

    def _check_canonical(self, result: PageAuditResult, response: requests.Response) -> None:
        if "html" not in response.headers.get("Content-Type", "").lower():
            return
        soup = BeautifulSoup(response.text, "html.parser")
        link = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
        if not link or not link.get("href"):
            result.add(
                "LOW",
                "Canonical tag missing",
                "No rel=canonical was found on the page.",
                "A canonical is a useful hint for duplicate handling, especially on large ecommerce sites.",
                "Add a self-referencing canonical on indexable pages. For intentionally non-indexed utility pages, this is lower priority.",
                "SEO / Developer",
                "Canonicalization",
            )
            return

        canonical = urljoin(response.url, link["href"].strip())
        result.canonical = canonical
        same_domain = urlparse(response.url).netloc.lower() == urlparse(canonical).netloc.lower()
        result.canonical_same_domain = same_domain
        can_resp = self._fetch(canonical)
        if can_resp is not None:
            result.canonical_status = can_resp.status_code

        if can_resp is not None and can_resp.status_code >= 400:
            result.add(
                "HIGH",
                "Canonical points to an error page",
                f"Canonical URL returns HTTP {can_resp.status_code}: {canonical}",
                "A canonical should point to a live preferred URL. If it points to an error, Google receives a broken consolidation hint.",
                "Update the canonical to the live preferred URL and make sure that URL returns 200.",
                "SEO / Developer",
                "Canonicalization",
            )
        elif not same_domain:
            result.add(
                "HIGH",
                "Canonical points to another domain",
                f"Canonical points to {canonical}",
                "Cross-domain canonicals can be valid, but only when you intentionally want another domain to be the indexed version.",
                "Confirm this is deliberate. If not, replace it with a self-canonical or the correct preferred URL on the same site.",
                "SEO / Developer",
                "Canonicalization",
            )
        elif not self._same_semantic_url(response.url, canonical):
            result.add(
                "LOW",
                "Canonical differs from fetched URL",
                f"Fetched URL: {response.url} | Canonical: {canonical}",
                "A different canonical may be correct, but it can also indicate duplicate URL patterns or unnecessary parameters.",
                "Confirm whether the canonical target is truly the preferred indexable URL. If yes, align internal links and sitemaps to that target.",
                "SEO / Developer",
                "Canonicalization",
            )
        else:
            result.add(
                "INFO",
                "Canonical looks consistent",
                f"Canonical points to the same URL pattern: {canonical}",
                "This helps Google understand the preferred version of the page.",
                "No action needed.",
                "SEO",
                "Canonicalization",
            )

    def _check_meta_and_mobile_basics(self, result: PageAuditResult, response: requests.Response) -> None:
        if not self._is_html_response(response):
            return
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("title")
        result.title_text = title_tag.get_text(" ", strip=True) if title_tag else ""
        if not result.title_text:
            result.add(
                "LOW",
                "Missing title tag",
                "The page has no <title> tag.",
                "This weakens how the page is understood and presented in search.",
                "Add a unique, descriptive title tag that matches the page intent.",
                "SEO / Developer",
                "Metadata",
            )

        desc = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
        result.meta_description = (desc.get("content") or "").strip() if desc else ""

        viewport = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "viewport"})
        result.viewport_present = bool(viewport)
        if viewport:
            result.add(
                "INFO",
                "Viewport tag present",
                "The page includes a viewport meta tag.",
                "Google primarily indexes the mobile version of pages, so mobile-friendly markup matters.",
                "No action needed.",
                "Developer / SEO",
                "Mobile-first",
            )
        else:
            result.add(
                "MEDIUM",
                "Viewport tag missing",
                "No viewport meta tag was found in the HTML head.",
                "Google uses mobile-first indexing for most sites. Missing mobile basics can create rendering and usability problems on mobile crawls.",
                "Add a standard viewport tag, such as <meta name='viewport' content='width=device-width, initial-scale=1'>.",
                "Developer",
                "Mobile-first",
            )

        if soup.find("input", {"type": "password"}):
            result.add(
                "MEDIUM",
                "Login-gated page",
                "The page appears to include a password or login form.",
                "Google generally cannot access private authenticated content.",
                "Do not expect this URL to index unless a public version exists. Keep private content behind auth and expose public landing pages where needed.",
                "SEO / Product",
                "Access",
            )

    def _check_content_clues(self, result: PageAuditResult, response: requests.Response) -> None:
        if not self._is_html_response(response):
            return
        soup = BeautifulSoup(response.text, "html.parser")
        body_text = soup.get_text(" ", strip=True)
        body_text_lower = body_text.lower()
        result.text_length = len(body_text)
        result.script_count = len(soup.find_all("script"))

        if response.status_code == 200:
            for phrase in SOFT_404_PATTERNS:
                if phrase in body_text_lower:
                    result.add(
                        "MEDIUM",
                        "Possible soft 404",
                        f"HTTP 200 page contains wording that often appears on error pages: '{phrase}'.",
                        "If this URL is really gone or empty, returning 200 can confuse indexing and reporting.",
                        "Return a real 404/410 for missing pages, or provide a clear useful page if it should stay live.",
                        "Developer / SEO",
                        "Indexing",
                    )
                    break

        if result.script_count >= 20 and result.text_length < 1200 and result.internal_link_count <= 3:
            result.add(
                "HIGH",
                "JavaScript-heavy shell page",
                f"The page has {result.script_count} script tags, relatively little visible HTML text ({result.text_length} chars), and very few crawlable HTML links.",
                "Google can render JavaScript, but JS-heavy shell pages are more fragile and may delay or reduce content discovery if critical content only appears after client-side rendering.",
                "Expose critical content, canonicals, metadata, and important internal links in the initial HTML when possible. Test the page with Search Console URL Inspection or Rich Results Test.",
                "Developer / SEO",
                "Rendering",
            )
        elif result.script_count >= 50 and result.text_length < 2500:
            result.add(
                "MEDIUM",
                "Very script-heavy page",
                f"The page has {result.script_count} script tags and limited visible HTML text ({result.text_length} chars).",
                "This can make crawling and rendering less efficient, especially if important content is delayed behind JavaScript.",
                "Reduce unnecessary scripts and ensure critical content and links exist in the initial HTML where possible.",
                "Developer",
                "Rendering",
            )

    def _check_links(self, result: PageAuditResult, response: requests.Response) -> None:
        if not self._is_html_response(response):
            return
        soup = BeautifulSoup(response.text, "html.parser")
        final_netloc = urlparse(response.url).netloc.lower()
        internal = 0
        external = 0
        crawlable_internal = 0
        discovered: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
                continue
            abs_url = urljoin(response.url, href)
            netloc = urlparse(abs_url).netloc.lower()
            if netloc == final_netloc:
                internal += 1
                if urlparse(abs_url).scheme in {"http", "https"}:
                    crawlable_internal += 1
                    discovered.append(abs_url)
            elif netloc:
                external += 1
        result.internal_link_count = internal
        result.external_link_count = external
        result.crawlable_internal_link_count = crawlable_internal
        result.discovered_internal_urls = discovered[:150]

        if crawlable_internal == 0:
            result.add(
                "MEDIUM",
                "No crawlable internal links detected",
                "The page did not expose crawlable internal links in HTML href attributes.",
                "Google primarily discovers URLs from links. Buttons and JS actions are less reliable for discovery.",
                "Add crawlable internal links using real <a href='...'> links, especially on key templates and category pages.",
                "SEO / Developer",
                "Internal linking",
            )
        else:
            result.add(
                "INFO",
                "Internal links detected",
                f"Found {crawlable_internal} crawlable internal link(s) in the HTML.",
                "Internal links help Google discover and prioritize pages.",
                "No action needed unless important pages are still isolated.",
                "SEO",
                "Internal linking",
            )

    def _check_resources(self, result: PageAuditResult, response: requests.Response, robots: RobotsContext) -> None:
        if not self._is_html_response(response):
            return
        soup = BeautifulSoup(response.text, "html.parser")
        resource_urls: List[str] = []

        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel") or []).lower()
            href = link["href"].strip()
            if "stylesheet" in rel and href:
                resource_urls.append(urljoin(response.url, href))

        for script in soup.find_all("script", src=True):
            src = script["src"].strip()
            if src:
                resource_urls.append(urljoin(response.url, src))

        seen = set()
        deduped = []
        for u in resource_urls:
            if u not in seen:
                deduped.append(u)
                seen.add(u)
        resource_urls = deduped[:MAX_RESOURCE_CHECKS]
        if not resource_urls:
            return

        blocked_or_broken = 0
        checked = 0
        for res_url in resource_urls:
            checked += 1
            allowed = True
            if robots.robots_status == 200:
                allowed = robots.parser.can_fetch("Googlebot", res_url)
            res_resp = self._fetch(res_url)
            broken = res_resp is None or res_resp.status_code >= 400
            if (not allowed) or broken:
                blocked_or_broken += 1

        result.css_js_checked = checked
        result.css_js_blocked_or_broken = blocked_or_broken
        if blocked_or_broken:
            result.add(
                "HIGH",
                "Important resources blocked or broken",
                f"{blocked_or_broken} out of {checked} checked CSS/JS resources were blocked or returned errors.",
                "If Google cannot fetch important CSS or JavaScript, rendering and page understanding can break.",
                "Allow Googlebot to fetch required resources and fix broken resource URLs. Then re-test the affected template.",
                "Developer",
                "Rendering",
            )
        else:
            result.add(
                "INFO",
                "Checked resources are fetchable",
                f"Checked {checked} CSS/JS resource(s) and found no obvious fetch issues.",
                "That reduces the risk of rendering-related crawl problems.",
                "No action needed.",
                "Developer",
                "Rendering",
            )

    def _check_url_pattern_guidance(self, result: PageAuditResult) -> None:
        parsed = urlparse(result.final_url or result.normalized_url)
        if not parsed.query:
            return
        low_query = parsed.query.lower()
        if any(hint in low_query for hint in FACET_QUERY_HINTS):
            if self._page_has_noindex(result):
                result.add(
                    "INFO",
                    "Parameterized search or faceted URL is controlled",
                    "This parameterized URL looks like a search or faceted page and it is already excluded from indexing.",
                    "Google recommends carefully managing dynamic, filter, and search-result URLs because they can create large crawl spaces.",
                    "Usually keep this excluded unless there is a strong SEO reason for this exact page to rank.",
                    "SEO",
                    "URL management",
                )
            else:
                result.add(
                    "MEDIUM",
                    "Parameterized search or faceted URL may expand crawl space",
                    "This URL includes query parameters that look like search or filter controls.",
                    "Large volumes of dynamic URLs can dilute crawl efficiency and create duplicate or low-value indexable pages.",
                    "Decide whether these pages should index. If not, use a consistent control such as noindex or robots strategy for non-valuable parameter combinations.",
                    "SEO / Developer",
                    "URL management",
                )

    def _check_pagination_and_incremental_loading(self, result: PageAuditResult, response: requests.Response) -> None:
        if not self._is_html_response(response):
            return
        if result.page_type not in {"Category / listing page", "Search / filtered results page"}:
            return
        soup = BeautifulSoup(response.text, "html.parser")
        html_text = soup.get_text(" ", strip=True).lower()

        has_pagination_href = False
        for a in soup.find_all("a", href=True):
            href = a["href"]
            rel = " ".join(a.get("rel") or []).lower()
            if "next" in rel:
                has_pagination_href = True
                break
            if any(p.search(href) for p in PAGINATION_PATTERNS):
                has_pagination_href = True
                break
            if a.get_text(" ", strip=True).lower() in {"next", "next page", "more results"}:
                has_pagination_href = True
                break

        button_texts = [b.get_text(" ", strip=True).lower() for b in soup.find_all(["button", "input"])]
        load_more = any(t in {"load more", "show more", "more results", "view more"} for t in button_texts) or "infinite scroll" in html_text
        if load_more and not has_pagination_href:
            result.add(
                "MEDIUM",
                "Possible infinite-scroll or load-more discovery risk",
                "The page appears to rely on load-more / infinite-scroll patterns without obvious paginated href links.",
                "Google generally discovers additional pages through href links, not button clicks or user-triggered JavaScript events.",
                "Expose paginated URLs with crawlable <a href> links for deeper result pages, even if the front-end also uses load-more or infinite scroll.",
                "Developer / SEO",
                "Discovery",
            )

    def _check_mobile_first_parity(self, result: PageAuditResult, desktop_response: requests.Response) -> None:
        result.mobile_test_run = True
        mobile_headers = dict(HEADERS)
        mobile_headers["User-Agent"] = GOOGLEBOT_SMARTPHONE_UA
        desktop_headers = dict(HEADERS)
        desktop_headers["User-Agent"] = DESKTOP_UA

        mobile_resp = self._fetch(result.normalized_url, headers=mobile_headers)
        desktop_resp = self._fetch(result.normalized_url, headers=desktop_headers)
        if mobile_resp is None or desktop_resp is None:
            return
        if not self._is_html_response(mobile_resp) or not self._is_html_response(desktop_resp):
            return

        mobile_soup = BeautifulSoup(mobile_resp.text, "html.parser")
        desktop_soup = BeautifulSoup(desktop_resp.text, "html.parser")
        mobile_title = mobile_soup.title.get_text(" ", strip=True) if mobile_soup.title else ""
        desktop_title = desktop_soup.title.get_text(" ", strip=True) if desktop_soup.title else ""
        mobile_robots = self._collect_meta_robots(mobile_soup)
        desktop_robots = self._collect_meta_robots(desktop_soup)
        mobile_can = self._collect_canonical(mobile_soup, mobile_resp.url)
        desktop_can = self._collect_canonical(desktop_soup, desktop_resp.url)
        mobile_text = mobile_soup.get_text(" ", strip=True)
        desktop_text = desktop_soup.get_text(" ", strip=True)

        mismatch_reasons = []
        if mobile_resp.status_code != desktop_resp.status_code:
            mismatch_reasons.append(f"status mobile {mobile_resp.status_code} vs desktop {desktop_resp.status_code}")
        if bool(mobile_title) != bool(desktop_title) or (mobile_title and desktop_title and mobile_title != desktop_title):
            mismatch_reasons.append("title differs")
        if mobile_robots != desktop_robots:
            mismatch_reasons.append("robots meta differs")
        if (mobile_can or "") != (desktop_can or ""):
            mismatch_reasons.append("canonical differs")
        if desktop_text and abs(len(mobile_text) - len(desktop_text)) > max(500, int(len(desktop_text) * 0.35)):
            mismatch_reasons.append("visible text differs strongly")

        if mismatch_reasons:
            result.mobile_desktop_mismatch = True
            result.add(
                "HIGH",
                "Mobile-first indexing parity risk",
                f"Mobile and desktop fetches differ: {', '.join(mismatch_reasons)}.",
                "Google primarily indexes the mobile version of most sites. Major differences between mobile and desktop can change what gets indexed or evaluated.",
                "Make sure the mobile response contains the same core content, metadata, canonicals, robots directives, and important links as the desktop version.",
                "Developer / SEO",
                "Mobile-first",
            )
        else:
            result.add(
                "INFO",
                "Mobile-first parity looks stable",
                "The quick mobile vs desktop comparison did not find major differences in the fetched HTML signals.",
                "This reduces the risk of mobile-first indexing surprises.",
                "No action needed.",
                "Developer / SEO",
                "Mobile-first",
            )

    def _collect_meta_robots(self, soup: BeautifulSoup) -> str:
        vals = []
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("http-equiv") or "").strip().lower()
            content = (meta.get("content") or "").strip().lower()
            if name in {"robots", "googlebot", "googlebot-news"} and content:
                vals.append(f"{name}:{content}")
        return "|".join(vals)

    def _collect_canonical(self, soup: BeautifulSoup, page_url: str) -> str:
        link = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
        if not link or not link.get("href"):
            return ""
        return urljoin(page_url, link["href"].strip())

    # -----------------------------
    # scoring and summaries
    # -----------------------------
    def _page_has_noindex(self, page: PageAuditResult) -> bool:
        combined = (page.meta_robots + " " + page.x_robots_tag).lower()
        return "noindex" in combined or "none" in combined

    def _calculate_page_score(self, result: PageAuditResult) -> None:
        score = 100
        for finding in result.findings:
            score -= SEVERITY_PENALTIES.get(finding.severity, 0)
        if self._page_has_noindex(result) and result.page_type == "Search / filtered results page":
            score = min(100, score + 8)
        result.score = max(0, min(100, score))

    def _build_page_summary(self, result: PageAuditResult) -> None:
        counts: Dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
        for finding in result.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1

        has_noindex = self._page_has_noindex(result)
        crawl_blocked = any(f.title == "Page disallowed in robots.txt" for f in result.findings)
        hard_error = any(f.severity == "CRITICAL" and f.category in {"Infrastructure", "Access", "Indexing"} for f in result.findings)

        if hard_error or crawl_blocked:
            result.indexability = "Blocked or highly unstable"
        elif has_noindex and result.page_type == "Search / filtered results page":
            result.indexability = "Excluded by design (likely intentional)"
        elif has_noindex:
            result.indexability = "Excluded from index"
        elif result.final_status and result.final_status >= 400:
            result.indexability = "Not indexable in current state"
        else:
            result.indexability = "Probably indexable"

        if counts["CRITICAL"]:
            result.verdict = "Immediate action needed"
        elif counts["HIGH"] >= 2:
            result.verdict = "Important fixes needed"
        elif counts["HIGH"] == 1 or counts["MEDIUM"] >= 2:
            result.verdict = "Needs review"
        else:
            result.verdict = "Looks healthy"

        priority = sorted([f for f in result.findings if f.severity != "INFO"], key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower()))
        result.top_actions = []
        seen = set()
        for finding in priority:
            action = f"{finding.title}: {finding.what_to_do}"
            if action not in seen:
                result.top_actions.append(action)
                seen.add(action)
            if len(result.top_actions) == 3:
                break
        if not result.top_actions:
            result.top_actions = ["No major action required. Keep monitoring key templates in Search Console and server logs."]

        if has_noindex and result.page_type == "Search / filtered results page":
            result.executive_summary = (
                "This URL looks like a search or filtered results page and it is marked noindex. "
                "For this type of page, that is often intentional and not necessarily a problem. "
                "The main decision is whether you want these filtered URLs to rank in Google."
            )
        elif counts["CRITICAL"]:
            result.executive_summary = (
                "Google is likely to have serious difficulty crawling or indexing this page in its current state. "
                "Fix the critical issues first, then re-check the page and request reindexing if appropriate."
            )
        elif counts["HIGH"] or counts["MEDIUM"]:
            result.executive_summary = (
                "The page is reachable, but there are signals that may reduce crawl efficiency, discovery, or indexability. "
                "The action plan below shows what matters most and who should fix it."
            )
        else:
            result.executive_summary = (
                "No major public crawl blockers were detected. "
                "This does not guarantee indexing, but the page looks technically healthy from an external crawl perspective."
            )

        result.summary = (
            f"{result.verdict}. Score: {result.score}/100. "
            f"Indexability: {result.indexability}. "
            f"Critical: {counts['CRITICAL']}, High: {counts['HIGH']}, Medium: {counts['MEDIUM']}."
        )

    def _aggregate_site_findings(self, site: SiteAuditResult, robots: RobotsContext) -> None:
        grouped: Dict[Tuple[str, str, str, str, str, str], Finding] = {}
        counts: Dict[Tuple[str, str, str, str, str, str], int] = defaultdict(int)

        def key_for(f: Finding) -> Tuple[str, str, str, str, str, str]:
            return (f.severity, f.title, f.why_it_matters, f.what_to_do, f.owner, f.category)

        for page in site.page_results:
            for finding in page.findings:
                if finding.severity == "INFO":
                    continue
                k = key_for(finding)
                counts[k] += 1
                if k not in grouped:
                    grouped[k] = Finding(
                        severity=finding.severity,
                        title=finding.title,
                        details=f"Seen on {counts[k]} page(s).",
                        why_it_matters=finding.why_it_matters,
                        what_to_do=finding.what_to_do,
                        owner=finding.owner,
                        category=finding.category,
                        sample_urls=[],
                    )
                if page.final_url and len(grouped[k].sample_urls) < 5 and page.final_url not in grouped[k].sample_urls:
                    grouped[k].sample_urls.append(page.final_url)
                grouped[k].details = f"Seen on {counts[k]} page(s)."

        # explicit site-level findings
        if robots.robots_status == 200 and not robots.sitemap_urls:
            grouped_key = ("MEDIUM", "No sitemap found sitewide", "", "", "SEO / Developer", "Discovery")
            grouped[grouped_key] = Finding(
                severity="MEDIUM",
                title="No sitemap found sitewide",
                details="No sitemap was declared in robots.txt or found at common sitemap paths.",
                why_it_matters="Sitemaps help Google discover important URLs and understand the preferred canonical URL set.",
                what_to_do="Publish an XML sitemap, keep only canonical 200 URLs in it, and declare it in robots.txt.",
                owner="SEO / Developer",
                category="Discovery",
            )

        if site.pages_crawled == 0:
            site.add(
                Finding(
                    severity="CRITICAL",
                    title="No pages crawled",
                    details="The sitewide crawl did not successfully audit any pages.",
                    why_it_matters="Without successful fetches, Google will also struggle to understand the site.",
                    what_to_do="Test the homepage manually, then check DNS, CDN, bot protection, and origin availability.",
                    owner="Developer / DevOps",
                    category="Infrastructure",
                )
            )
            return

        if site.pages_error / max(site.pages_crawled, 1) >= 0.15:
            site.add(
                Finding(
                    severity="HIGH",
                    title="Too many error pages in sampled crawl",
                    details=f"{site.pages_error} of {site.pages_crawled} crawled URLs returned 4xx/5xx responses.",
                    why_it_matters="A high proportion of broken pages wastes crawl effort and weakens discovery across the site.",
                    what_to_do="Fix broken internal links, clean sitemaps, and stabilize failing templates or routes.",
                    owner="Developer / SEO",
                    category="Infrastructure",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if (p.final_status or 0) >= 400][:5],
                )
            )

        if site.pages_disallowed > 0 and any(not self._page_has_noindex(p) for p in site.page_results if p.robots_allows_page is False):
            site.add(
                Finding(
                    severity="MEDIUM",
                    title="robots.txt is being used on sampled pages without clear page-level exclusion",
                    details=f"{site.pages_disallowed} crawled URL(s) are disallowed in robots.txt.",
                    why_it_matters="robots.txt controls crawling, not necessarily indexing. URLs can still appear in results without their content if they are linked elsewhere.",
                    what_to_do="Use robots.txt for crawl control and use noindex or access control when you truly want a page excluded from search.",
                    owner="SEO / Developer",
                    category="Indexing",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if p.robots_allows_page is False][:5],
                )
            )

        if site.pages_mobile_mismatch > 0:
            site.add(
                Finding(
                    severity="HIGH",
                    title="Mobile-first indexing parity issues found",
                    details=f"{site.pages_mobile_mismatch} sampled page(s) showed notable differences between mobile and desktop fetches.",
                    why_it_matters="Google primarily indexes the mobile version of most sites. Major differences can change what gets indexed or evaluated.",
                    what_to_do="Align content, metadata, canonicals, and internal links across mobile and desktop responses.",
                    owner="Developer / SEO",
                    category="Mobile-first",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if p.mobile_desktop_mismatch][:5],
                )
            )

        if site.pages_over_2mb > 0:
            site.add(
                Finding(
                    severity="MEDIUM",
                    title="Oversized pages found",
                    details=f"{site.pages_over_2mb} sampled page(s) exceeded Google's 2 MB fetch window for text-based files.",
                    why_it_matters="Important content or links late in the HTML may be ignored if the fetched HTML is truncated for indexing consideration.",
                    what_to_do="Reduce HTML bloat and move critical content, metadata, and links earlier in the response.",
                    owner="Developer / SEO",
                    category="Rendering",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if p.content_bytes > 2 * 1024 * 1024][:5],
                )
            )

        if site.pages_js_heavy / max(site.html_pages_crawled, 1) >= 0.2:
            site.add(
                Finding(
                    severity="HIGH",
                    title="JavaScript-heavy templates are common",
                    details=f"{site.pages_js_heavy} of {site.html_pages_crawled} sampled HTML pages look heavily dependent on JavaScript.",
                    why_it_matters="JS-heavy shell pages are more fragile for crawling, rendering, and link discovery.",
                    what_to_do="Expose core content, metadata, canonicals, and important internal links in the initial HTML where possible.",
                    owner="Developer / SEO",
                    category="Rendering",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if any(f.title == 'JavaScript-heavy shell page' for f in p.findings)][:5],
                )
            )

        if site.pages_missing_viewport / max(site.html_pages_crawled, 1) >= 0.2:
            site.add(
                Finding(
                    severity="MEDIUM",
                    title="Missing mobile viewport on sampled pages",
                    details=f"{site.pages_missing_viewport} sampled HTML page(s) are missing a viewport tag.",
                    why_it_matters="Mobile-first indexing relies on the mobile experience and response. Missing viewport basics increase risk on mobile rendering.",
                    what_to_do="Add a standard viewport tag to affected templates.",
                    owner="Developer",
                    category="Mobile-first",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if p.viewport_present is False][:5],
                )
            )

        if site.pages_with_parameter_urls / max(site.pages_crawled, 1) >= 0.3:
            site.add(
                Finding(
                    severity="MEDIUM",
                    title="High share of parameterized URLs in sampled crawl",
                    details=f"{site.pages_with_parameter_urls} of {site.pages_crawled} sampled URLs contain query parameters.",
                    why_it_matters="Large dynamic URL sets can create crawl inefficiency and duplicate or low-value indexable pages.",
                    what_to_do="Define which parameter URLs deserve indexing and keep non-valuable combinations consistently controlled.",
                    owner="SEO / Developer",
                    category="URL management",
                    sample_urls=[p.final_url or p.input_url for p in site.page_results if urlparse(p.normalized_url).query][:5],
                )
            )

        # page-grouped findings
        for _, finding in sorted(grouped.items(), key=lambda item: (SEVERITY_ORDER.get(item[1].severity, 99), item[1].title.lower())):
            site.add(finding)

    def _calculate_site_score(self, site: SiteAuditResult) -> None:
        score = 100
        for finding in site.sitewide_findings:
            score -= SEVERITY_PENALTIES.get(finding.severity, 0)
        # ratio-based nudges
        if site.pages_crawled:
            score -= min(20, int((site.pages_error / site.pages_crawled) * 40))
            score -= min(12, int((site.pages_mobile_mismatch / max(site.html_pages_crawled, 1)) * 30))
            score -= min(10, int((site.pages_js_heavy / max(site.html_pages_crawled, 1)) * 20))
        site.score = max(0, min(100, score))

    def _build_site_summary(self, site: SiteAuditResult) -> None:
        counts: Dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
        for finding in site.sitewide_findings:
            counts[finding.severity] += 1

        if site.pages_crawled == 0 or counts["CRITICAL"]:
            site.verdict = "Immediate action needed"
            site.indexability = "Site crawl/indexing risk is high"
        elif counts["HIGH"] >= 2 or site.pages_error >= max(2, int(site.pages_crawled * 0.15)):
            site.verdict = "Important fixes needed"
            site.indexability = "Site is partially crawlable but unstable"
        elif counts["HIGH"] == 1 or counts["MEDIUM"] >= 2:
            site.verdict = "Needs review"
            site.indexability = "Mostly crawlable with notable risks"
        else:
            site.verdict = "Looks healthy"
            site.indexability = "No major public crawl blockers found sitewide"

        site.executive_summary = (
            f"This sitewide audit crawled {site.pages_crawled} URL(s) on {site.site_domain}. "
            f"It translates technical crawl signals into SEO actions. "
            f"Focus first on the high-priority issues that affect many pages or core templates."
        )
        if site.pages_mobile_mismatch:
            site.executive_summary += " Mobile-first differences were found, which matters because Google primarily indexes the mobile version of sites."
        if site.pages_over_2mb:
            site.executive_summary += " Some pages were large enough to risk partial processing by Googlebot."
        if site.pages_js_heavy:
            site.executive_summary += " Several pages also appear highly dependent on JavaScript for content or link discovery."

        ordered = sorted(site.sitewide_findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower()))
        site.top_actions = []
        seen = set()
        for f in ordered:
            text = f"{f.title}: {f.what_to_do}"
            if text not in seen:
                site.top_actions.append(text)
                seen.add(text)
            if len(site.top_actions) == 5:
                break
        if not site.top_actions:
            site.top_actions = ["No major action required. Keep monitoring Search Console crawl stats, coverage, and server logs."]

        site.summary = (
            f"{site.verdict}. Score: {site.score}/100. "
            f"Pages crawled: {site.pages_crawled}. "
            f"Critical: {counts['CRITICAL']}, High: {counts['HIGH']}, Medium: {counts['MEDIUM']}."
        )


class AuditorGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x980")
        self.root.minsize(1220, 760)

        self.auditor = CrawlAuditor()
        self.results: List[AuditAnyResult] = []
        self.result_map: Dict[str, AuditAnyResult] = {}
        self.queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_requested = False

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Paste one website or page URL per line", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.url_text = tk.Text(top, height=6, wrap="word")
        self.url_text.grid(row=1, column=0, columnspan=10, sticky="nsew", pady=(6, 8))
        self.url_text.insert("1.0", "https://example.com\nhttps://www.python.org")

        controls = ttk.Frame(top)
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(16, weight=1)

        ttk.Button(controls, text="Run audit", command=self.run_audit).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(controls, text="Stop", command=self.request_stop).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(controls, text="Load TXT/CSV", command=self.load_urls_from_file).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(controls, text="Clear URLs", command=self.clear_urls).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(controls, text="Export CSV", command=self.export_csv).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(controls, text="Export JSON", command=self.export_json).grid(row=0, column=5, padx=(0, 6))
        ttk.Button(controls, text="Export HTML report", command=self.export_html_report).grid(row=0, column=6, padx=(0, 12))

        self.mode_var = tk.StringVar(value="site")
        ttk.Label(controls, text="Mode:").grid(row=0, column=7, padx=(0, 4))
        ttk.Radiobutton(controls, text="Full website", variable=self.mode_var, value="site").grid(row=0, column=8, padx=(0, 4))
        ttk.Radiobutton(controls, text="Single page", variable=self.mode_var, value="page").grid(row=0, column=9, padx=(0, 12))

        ttk.Label(controls, text="Max pages:").grid(row=0, column=10, padx=(0, 4))
        self.max_pages_var = tk.IntVar(value=40)
        self.max_pages_spin = ttk.Spinbox(controls, from_=5, to=MAX_PAGES_ALLOWED, increment=5, textvariable=self.max_pages_var, width=6)
        self.max_pages_spin.grid(row=0, column=11, padx=(0, 12))

        self.progress = ttk.Progressbar(controls, mode="determinate", length=230)
        self.progress.grid(row=0, column=12, padx=(0, 8))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=16, sticky="w")

        main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main_pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(main_pane, padding=6)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)

        ttk.Label(left_frame, text="Audit results", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.tree = ttk.Treeview(
            left_frame,
            columns=("target", "mode", "pages", "score", "verdict", "indexability", "main_issue", "next_step"),
            show="headings",
            height=22,
        )
        headings = {
            "target": "Target",
            "mode": "Mode",
            "pages": "Pages",
            "score": "Score",
            "verdict": "Verdict",
            "indexability": "Indexability",
            "main_issue": "Main issue",
            "next_step": "Next step",
        }
        widths = {
            "target": 250,
            "mode": 60,
            "pages": 60,
            "score": 60,
            "verdict": 150,
            "indexability": 220,
            "main_issue": 240,
            "next_step": 430,
        }
        for col in headings:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self.sort_tree(c, False))
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        right_frame = ttk.Frame(main_pane, padding=6)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        self.detail_title = tk.StringVar(value="Select a result to view the SEO-friendly explanation")
        ttk.Label(right_frame, textvariable=self.detail_title, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        self.overview_tab = ttk.Frame(self.notebook, padding=10)
        self.actions_tab = ttk.Frame(self.notebook, padding=10)
        self.technical_tab = ttk.Frame(self.notebook, padding=10)
        self.pages_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.overview_tab, text="Overview")
        self.notebook.add(self.actions_tab, text="Issues & Actions")
        self.notebook.add(self.pages_tab, text="Pages")
        self.notebook.add(self.technical_tab, text="Technical")

        self._build_overview_tab()
        self._build_actions_tab()
        self._build_pages_tab()
        self._build_technical_tab()

        main_pane.add(left_frame, weight=3)
        main_pane.add(right_frame, weight=4)

    def _build_overview_tab(self) -> None:
        self.overview_tab.columnconfigure(0, weight=1)
        self.overview_tab.columnconfigure(1, weight=1)
        self.overview_tab.rowconfigure(2, weight=1)

        card1 = ttk.LabelFrame(self.overview_tab, text="Score")
        card1.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.score_canvas = tk.Canvas(card1, width=340, height=220, bg="white", highlightthickness=0)
        self.score_canvas.pack(fill="both", expand=True)

        card2 = ttk.LabelFrame(self.overview_tab, text="Issue severity")
        card2.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.severity_canvas = tk.Canvas(card2, width=340, height=220, bg="white", highlightthickness=0)
        self.severity_canvas.pack(fill="both", expand=True)

        card3 = ttk.LabelFrame(self.overview_tab, text="Executive summary")
        card3.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        self.summary_text = tk.Text(card3, wrap="word", height=7)
        self.summary_text.pack(fill="both", expand=True)
        self.summary_text.configure(state="disabled")

        card4 = ttk.LabelFrame(self.overview_tab, text="Top actions")
        card4.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.top_actions_text = tk.Text(card4, wrap="word")
        self.top_actions_text.pack(fill="both", expand=True)
        self.top_actions_text.configure(state="disabled")

    def _build_actions_tab(self) -> None:
        self.actions_tab.columnconfigure(0, weight=1)
        self.actions_tab.rowconfigure(0, weight=1)
        self.issues_tree = ttk.Treeview(
            self.actions_tab,
            columns=("severity", "issue", "why", "action", "owner", "samples"),
            show="headings",
            height=18,
        )
        widths = {"severity": 80, "issue": 210, "why": 260, "action": 420, "owner": 130, "samples": 320}
        headings = {"severity": "Priority", "issue": "Issue", "why": "Why it matters", "action": "What to do", "owner": "Owner", "samples": "Sample URLs"}
        for col in headings:
            self.issues_tree.heading(col, text=headings[col])
            self.issues_tree.column(col, width=widths[col], anchor="w")
        self.issues_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(self.actions_tab, orient="vertical", command=self.issues_tree.yview)
        self.issues_tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")

    def _build_pages_tab(self) -> None:
        self.pages_tab.columnconfigure(0, weight=1)
        self.pages_tab.rowconfigure(0, weight=1)
        self.pages_tree = ttk.Treeview(
            self.pages_tab,
            columns=("url", "http", "score", "indexability", "main_issue"),
            show="headings",
            height=18,
        )
        widths = {"url": 480, "http": 60, "score": 60, "indexability": 180, "main_issue": 320}
        headings = {"url": "Page URL", "http": "HTTP", "score": "Score", "indexability": "Indexability", "main_issue": "Main issue"}
        for col in headings:
            self.pages_tree.heading(col, text=headings[col])
            self.pages_tree.column(col, width=widths[col], anchor="w")
        self.pages_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(self.pages_tab, orient="vertical", command=self.pages_tree.yview)
        self.pages_tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")

    def _build_technical_tab(self) -> None:
        self.technical_tab.columnconfigure(0, weight=1)
        self.technical_tab.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(self.technical_tab, wrap="word")
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(self.technical_tab, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.detail_text.configure(state="disabled")

    def _set_text(self, widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def clear_urls(self) -> None:
        self.url_text.delete("1.0", "end")

    def load_urls_from_file(self) -> None:
        path = filedialog.askopenfilename(title="Select URL list", filetypes=[("Text or CSV", "*.txt *.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            urls = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if "," in line and not line.lower().startswith("http"):
                        urls.extend([p.strip() for p in line.split(",") if p.strip()])
                    else:
                        urls.append(line)
            self.url_text.delete("1.0", "end")
            self.url_text.insert("1.0", "\n".join(urls))
            self.status_var.set(f"Loaded {len(urls)} URL(s).")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Load error", str(e))

    def get_urls(self) -> List[str]:
        raw = self.url_text.get("1.0", "end").strip()
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def request_stop(self) -> None:
        self.stop_requested = True
        self.status_var.set("Stop requested. Finishing current target...")

    def run_audit(self) -> None:
        urls = self.get_urls()
        if not urls:
            messagebox.showwarning("No URLs", "Please enter at least one URL.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Busy", "An audit is already running.")
            return
        self.stop_requested = False
        self.results.clear()
        self.result_map.clear()
        self.tree.delete(*self.tree.get_children())
        self.pages_tree.delete(*self.pages_tree.get_children())
        self.issues_tree.delete(*self.issues_tree.get_children())
        self._set_text(self.summary_text, "")
        self._set_text(self.top_actions_text, "")
        self._set_text(self.detail_text, "")
        self.score_canvas.delete("all")
        self.severity_canvas.delete("all")

        mode = self.mode_var.get()
        max_pages = max(1, min(MAX_PAGES_ALLOWED, int(self.max_pages_var.get() or MAX_SITE_PAGES_DEFAULT)))
        self.progress.configure(maximum=len(urls), value=0)
        self.status_var.set(f"Starting {mode} audit for {len(urls)} target(s)...")

        def worker() -> None:
            for idx, url in enumerate(urls, start=1):
                if self.stop_requested:
                    break
                self.queue.put(("status", f"Auditing {idx}/{len(urls)}: {url}"))
                if mode == "site":
                    result = self.auditor.audit_site(url, max_pages=max_pages, stop_checker=lambda: self.stop_requested)
                else:
                    result = self.auditor.audit_page(url)
                self.queue.put(("result", result))
                self.queue.put(("progress", idx))
            self.queue.put(("done", None))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    self.progress.configure(value=int(payload))
                elif kind == "result":
                    result = payload
                    self.results.append(result)
                    self._insert_result(result)
                elif kind == "done":
                    if self.stop_requested:
                        self.status_var.set("Stopped.")
                    else:
                        self.status_var.set("Audit completed.")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _highest_priority_finding(self, result: AuditAnyResult) -> Optional[Finding]:
        findings = result.sitewide_findings if isinstance(result, SiteAuditResult) else result.findings
        non_info = [f for f in findings if f.severity != "INFO"]
        if not non_info:
            return None
        return sorted(non_info, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower()))[0]

    def _insert_result(self, result: AuditAnyResult) -> None:
        main_issue = self._highest_priority_finding(result)
        next_step = main_issue.what_to_do if main_issue else "No urgent action"
        target = result.input_url
        mode = "site" if isinstance(result, SiteAuditResult) else "page"
        pages = result.pages_crawled if isinstance(result, SiteAuditResult) else 1
        item_id = self.tree.insert(
            "",
            "end",
            values=(
                target,
                mode,
                pages,
                result.score,
                result.verdict,
                result.indexability,
                main_issue.title if main_issue else "No major issue",
                next_step,
            ),
        )
        self.result_map[item_id] = result

    def on_tree_select(self, event: object | None = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        result = self.result_map.get(item_id)
        if not result:
            return

        self.detail_title.set(f"SEO view for {result.input_url}")
        self._draw_score_chart(result)
        self._draw_severity_chart(result)

        if isinstance(result, SiteAuditResult):
            summary_lines = [
                f"Mode: Full website",
                f"Site: {result.site_domain}",
                f"Pages crawled: {result.pages_crawled}/{result.pages_requested_limit}",
                f"Verdict: {result.verdict}",
                f"Indexability: {result.indexability}",
                "",
                result.executive_summary,
                "",
                f"Quick summary: {result.summary}",
            ]
            action_lines = [f"{i}. {a}" for i, a in enumerate(result.top_actions, start=1)]
            self._set_text(self.summary_text, "\n".join(summary_lines))
            self._set_text(self.top_actions_text, "\n\n".join(action_lines))

            self.issues_tree.delete(*self.issues_tree.get_children())
            for f in sorted(result.sitewide_findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower())):
                self.issues_tree.insert(
                    "",
                    "end",
                    values=(f.severity, f.title, f.why_it_matters, f.what_to_do, f.owner, " | ".join(self._clean_url_for_display(u) for u in f.sample_urls)),
                )

            self.pages_tree.delete(*self.pages_tree.get_children())
            for p in result.page_results:
                main_issue = self._highest_priority_finding(p)
                self.pages_tree.insert(
                    "",
                    "end",
                    values=(
                        p.final_url or p.input_url,
                        p.final_status or "",
                        p.score,
                        p.indexability,
                        main_issue.title if main_issue else "No major issue",
                    ),
                )
            self._set_text(self.detail_text, self._format_site_technical_details(result))
        else:
            summary_lines = [
                f"Mode: Single page",
                f"Page type: {result.page_type}",
                f"Verdict: {result.verdict}",
                f"Indexability: {result.indexability}",
                "",
                result.executive_summary,
                "",
                f"Quick summary: {result.summary}",
            ]
            self._set_text(self.summary_text, "\n".join(summary_lines))
            self._set_text(self.top_actions_text, "\n\n".join(f"{i}. {a}" for i, a in enumerate(result.top_actions, start=1)))
            self.issues_tree.delete(*self.issues_tree.get_children())
            for f in sorted(result.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower())):
                self.issues_tree.insert("", "end", values=(f.severity, f.title, f.why_it_matters, f.what_to_do, f.owner, ""))
            self.pages_tree.delete(*self.pages_tree.get_children())
            self.pages_tree.insert("", "end", values=(result.final_url or result.input_url, result.final_status or "", result.score, result.indexability, (self._highest_priority_finding(result).title if self._highest_priority_finding(result) else "No major issue")))
            self._set_text(self.detail_text, self._format_page_technical_details(result))

    def _draw_score_chart(self, result: AuditAnyResult) -> None:
        c = self.score_canvas
        c.delete("all")
        width = int(c["width"])
        cx = width // 2
        cy = 135
        radius = 80
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        c.create_arc(bbox, start=180, extent=180, style="arc", width=18, outline="#e0e0e0")
        score = max(0, min(100, result.score))
        color = "#2e7d32" if score >= 85 else "#f9a825" if score >= 70 else "#ef6c00" if score >= 50 else "#c62828"
        c.create_arc(bbox, start=180, extent=(180 * score / 100), style="arc", width=18, outline=color)
        c.create_text(cx, 95, text=str(score), font=("Segoe UI", 26, "bold"), fill="#111111")
        c.create_text(cx, 125, text="/100", font=("Segoe UI", 11), fill="#666666")
        c.create_text(cx, 168, text=result.verdict, font=("Segoe UI", 12, "bold"), fill="#111111")
        c.create_text(cx, 190, text=result.indexability, font=("Segoe UI", 10), fill="#444444")

    def _draw_severity_chart(self, result: AuditAnyResult) -> None:
        c = self.severity_canvas
        c.delete("all")
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        findings = result.sitewide_findings if isinstance(result, SiteAuditResult) else result.findings
        for f in findings:
            counts[f.severity] += 1
        labels = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        max_count = max(max(counts.values()), 1)
        base_x = 40
        bottom = 180
        chart_height = 120
        bar_width = 42
        gap = 18
        for i, label in enumerate(labels):
            x1 = base_x + i * (bar_width + gap)
            x2 = x1 + bar_width
            value = counts[label]
            height = chart_height * (value / max_count) if max_count else 0
            y1 = bottom - height
            c.create_rectangle(x1, y1, x2, bottom, fill=SEVERITY_COLORS[label], outline="")
            c.create_text((x1 + x2) / 2, y1 - 12, text=str(value), font=("Segoe UI", 10, "bold"))
            c.create_text((x1 + x2) / 2, bottom + 15, text=label.title(), font=("Segoe UI", 9))
        c.create_line(25, bottom, 320, bottom, fill="#999999")
        c.create_text(170, 18, text="Issue count by severity", font=("Segoe UI", 12, "bold"), fill="#111111")

    def _format_page_technical_details(self, result: PageAuditResult) -> str:
        lines = [
            f"Input URL: {result.input_url}",
            f"Normalized URL: {result.normalized_url}",
            f"Final URL: {result.final_url}",
            f"Page type: {result.page_type}",
            f"Summary: {result.summary}",
            f"Error: {result.error or 'None'}",
            "",
            "Technical snapshot",
            "-" * 90,
            f"HTTP status: {result.final_status}",
            f"Response time: {result.response_time_ms} ms",
            f"Content-Type: {result.content_type or 'Unknown'}",
            f"Downloaded size: {result.content_bytes} bytes",
            f"HTTPS final URL: {result.https_ok}",
            f"robots.txt URL: {result.robots_url}",
            f"robots.txt status: {result.robots_status}",
            f"robots allows page: {result.robots_allows_page}",
            f"Sitemap URLs: {', '.join(result.sitemap_urls) if result.sitemap_urls else 'None'}",
            f"Sitemap accessible: {result.sitemap_accessible}",
            f"Meta robots: {result.meta_robots or 'None'}",
            f"X-Robots-Tag: {result.x_robots_tag or 'None'}",
            f"Canonical: {result.canonical or 'None'}",
            f"Canonical status: {result.canonical_status}",
            f"Title: {result.title_text or 'None'}",
            f"Meta description present: {bool(result.meta_description)}",
            f"Viewport tag present: {result.viewport_present}",
            f"Internal links found: {result.internal_link_count}",
            f"Crawlable internal links found: {result.crawlable_internal_link_count}",
            f"External links found: {result.external_link_count}",
            f"CSS/JS checked: {result.css_js_checked}",
            f"Blocked or broken resources: {result.css_js_blocked_or_broken}",
            f"Visible text length: {result.text_length}",
            f"Script tags: {result.script_count}",
            f"Mobile parity checked: {result.mobile_test_run}",
            f"Mobile/Desktop mismatch detected: {result.mobile_desktop_mismatch}",
            "",
            "All findings",
            "-" * 90,
        ]
        if not result.findings:
            lines.append("No findings.")
        else:
            for i, f in enumerate(sorted(result.findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), x.title.lower())), start=1):
                lines.append(f"{i}. [{f.severity}] {f.title}")
                lines.append(f"   Details: {f.details}")
                lines.append(f"   Why it matters: {f.why_it_matters}")
                lines.append(f"   What to do: {f.what_to_do}")
                lines.append(f"   Owner: {f.owner}")
                lines.append("")
        return "\n".join(lines)

    def _format_site_technical_details(self, site: SiteAuditResult) -> str:
        lines = [
            f"Input URL: {site.input_url}",
            f"Normalized URL: {site.normalized_url}",
            f"Final site URL: {site.final_site_url}",
            f"Domain: {site.site_domain}",
            f"Summary: {site.summary}",
            f"Error: {site.error or 'None'}",
            "",
            "Sitewide snapshot",
            "-" * 90,
            f"Pages requested limit: {site.pages_requested_limit}",
            f"Pages crawled: {site.pages_crawled}",
            f"HTML pages crawled: {site.html_pages_crawled}",
            f"Pages probably indexable: {site.pages_indexable}",
            f"Pages with noindex: {site.pages_noindex}",
            f"Pages disallowed in robots.txt: {site.pages_disallowed}",
            f"Pages returning errors: {site.pages_error}",
            f"Pages redirected: {site.pages_redirected}",
            f"Pages over 2 MB: {site.pages_over_2mb}",
            f"Pages with mobile/desktop mismatch: {site.pages_mobile_mismatch}",
            f"Pages that look JS-heavy: {site.pages_js_heavy}",
            f"Pages missing viewport: {site.pages_missing_viewport}",
            f"Pages missing title: {site.pages_missing_title}",
            f"Pages missing canonical: {site.pages_missing_canonical}",
            f"Parameterized URLs in crawl sample: {site.pages_with_parameter_urls}",
            "",
            "Crawl notes",
            "-" * 90,
        ]
        if site.crawl_notes:
            for note in site.crawl_notes:
                lines.append(f"- {note}")
        else:
            lines.append("- None")
        lines.extend(["", "Sitewide findings", "-" * 90])
        if not site.sitewide_findings:
            lines.append("No findings.")
        else:
            for i, f in enumerate(sorted(site.sitewide_findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), x.title.lower())), start=1):
                lines.append(f"{i}. [{f.severity}] {f.title}")
                lines.append(f"   Details: {f.details}")
                lines.append(f"   Why it matters: {f.why_it_matters}")
                lines.append(f"   What to do: {f.what_to_do}")
                lines.append(f"   Owner: {f.owner}")
                if f.sample_urls:
                    lines.append(f"   Sample URLs: {' | '.join(f.sample_urls)}")
                lines.append("")
        lines.extend(["", "Sampled page list", "-" * 90])
        for p in site.page_results:
            main_issue = self._highest_priority_finding(p)
            lines.append(f"- {p.final_url or p.input_url} | HTTP {p.final_status} | Score {p.score} | {p.indexability} | {main_issue.title if main_issue else 'No major issue'}")
        return "\n".join(lines)

    def sort_tree(self, col: str, reverse: bool) -> None:
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        def convert(value: str):
            try:
                return int(value)
            except ValueError:
                return value.lower()

        items.sort(key=lambda x: convert(x[0]), reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)
        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def export_csv(self) -> None:
        if not self.results:
            messagebox.showinfo("No data", "Run an audit first.")
            return
        path = filedialog.asksaveasfilename(title="Save CSV", defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["target", "mode", "pages_crawled", "score", "verdict", "indexability", "summary", "top_actions", "main_issue"])
                for r in self.results:
                    findings = r.sitewide_findings if isinstance(r, SiteAuditResult) else r.findings
                    main_issue = self._highest_priority_finding(r)
                    writer.writerow([
                        r.input_url,
                        "site" if isinstance(r, SiteAuditResult) else "page",
                        r.pages_crawled if isinstance(r, SiteAuditResult) else 1,
                        r.score,
                        r.verdict,
                        r.indexability,
                        r.summary,
                        " || ".join(r.top_actions),
                        main_issue.title if main_issue else "",
                    ])
                    if isinstance(r, SiteAuditResult):
                        writer.writerow([])
                        writer.writerow(["Sampled page URL", "HTTP", "Score", "Indexability", "Main issue"])
                        for p in r.page_results:
                            p_main = self._highest_priority_finding(p)
                            writer.writerow([p.final_url or p.input_url, p.final_status, p.score, p.indexability, p_main.title if p_main else ""])
                        writer.writerow([])
            self.status_var.set(f"CSV exported: {path}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export CSV error", str(e))

    def export_json(self) -> None:
        if not self.results:
            messagebox.showinfo("No data", "Run an audit first.")
            return
        path = filedialog.asksaveasfilename(title="Save JSON", defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in self.results], f, indent=2, ensure_ascii=False)
            self.status_var.set(f"JSON exported: {path}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export JSON error", str(e))

    def export_html_report(self) -> None:
        if not self.results:
            messagebox.showinfo("No data", "Run an audit first.")
            return
        path = filedialog.asksaveasfilename(title="Save HTML report", defaultextension=".html", filetypes=[("HTML files", "*.html")])
        if not path:
            return
        try:
            html_parts = [
                "<!doctype html><html><head><meta charset='utf-8'>",
                "<meta name='viewport' content='width=device-width, initial-scale=1'>",
                f"<title>{html.escape(APP_TITLE)} report</title>",
                "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f5f7fb;color:#162033;}"
                "h1,h2,h3{margin:0 0 12px;} .card{background:white;border-radius:14px;padding:18px 20px;margin:16px 0;box-shadow:0 8px 26px rgba(0,0,0,.08);}"
                ".pill{display:inline-block;padding:6px 10px;border-radius:999px;background:#eef2ff;margin-right:8px;margin-bottom:8px;font-size:12px;}"
                ".sev{font-weight:700;} .CRITICAL{color:#c62828;} .HIGH{color:#ef6c00;} .MEDIUM{color:#b78103;} .LOW{color:#666;} .INFO{color:#2e7d32;}"
                "table{border-collapse:collapse;width:100%;font-size:14px;} th,td{border:1px solid #e4e7ef;padding:8px 10px;text-align:left;vertical-align:top;} th{background:#f0f3f9;}"
                "ul{margin:8px 0 0 18px;} .mono{font-family:Consolas,monospace;font-size:12px;word-break:break-all;} .small{font-size:13px;color:#56627a;}" 
                "</style></head><body>",
                f"<h1>{html.escape(APP_TITLE)} - Report</h1>",
                "<p class='small'>This report converts public crawl/index signals into plain-English SEO actions.</p>",
            ]
            for result in self.results:
                findings = result.sitewide_findings if isinstance(result, SiteAuditResult) else result.findings
                html_parts.append("<div class='card'>")
                html_parts.append(f"<h2>{html.escape(result.input_url)}</h2>")
                mode = "Full website" if isinstance(result, SiteAuditResult) else "Single page"
                html_parts.append(f"<div class='pill'>{mode}</div><div class='pill'>Score: {result.score}/100</div><div class='pill'>{html.escape(result.verdict)}</div><div class='pill'>{html.escape(result.indexability)}</div>")
                html_parts.append(f"<p>{html.escape(result.executive_summary)}</p>")
                html_parts.append("<h3>Top actions</h3><ul>")
                for action in result.top_actions:
                    html_parts.append(f"<li>{html.escape(action)}</li>")
                html_parts.append("</ul>")
                html_parts.append("<h3>Issues</h3><table><tr><th>Priority</th><th>Issue</th><th>Why it matters</th><th>What to do</th><th>Owner</th><th>Sample URLs</th></tr>")
                for f in sorted(findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), x.title.lower())):
                    samples = "<br>".join(html.escape(u) for u in f.sample_urls)
                    html_parts.append(
                        f"<tr><td class='sev {html.escape(f.severity)}'>{html.escape(f.severity)}</td><td>{html.escape(f.title)}</td><td>{html.escape(f.why_it_matters)}</td><td>{html.escape(f.what_to_do)}</td><td>{html.escape(f.owner)}</td><td class='mono'>{samples}</td></tr>"
                    )
                html_parts.append("</table>")
                if isinstance(result, SiteAuditResult):
                    html_parts.append("<h3>Sampled pages</h3><table><tr><th>URL</th><th>HTTP</th><th>Score</th><th>Indexability</th><th>Main issue</th></tr>")
                    for p in result.page_results:
                        p_main = self._highest_priority_finding(p)
                        html_parts.append(
                            f"<tr><td class='mono'>{html.escape(p.final_url or p.input_url)}</td><td>{html.escape(str(p.final_status or ''))}</td><td>{p.score}</td><td>{html.escape(p.indexability)}</td><td>{html.escape(p_main.title if p_main else 'No major issue')}</td></tr>"
                        )
                    html_parts.append("</table>")
                html_parts.append("</div>")
            html_parts.append("</body></html>")
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join(html_parts))
            self.status_var.set(f"HTML report exported: {path}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export HTML error", str(e))


def main() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    AuditorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
