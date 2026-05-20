#!/usr/bin/env python3
"""
Google Crawl Auditor - SEO Team Edition v4

Author:  Ahmed Oueslati
Email:   ahmedoueslati6110@gmail.com
Owner:   Ahmed Oueslati — All rights reserved © 2026

Important:
- Keep this file in the same folder as google_crawl_auditor_gui_v3_sitewide.py
- This version extends the v3 auditor with:
  * clearer full-website mode for SEO teams
  * crawl path / navigation visibility
  * per-page explanations in site mode
  * minimum 3-level crawl support in the UI
  * extra Google-aligned crawl/index checks applied in both single-page and full-site audits

Current Google-aligned checks included in this version:
- mobile-first indexing parity
- robots.txt vs noindex interaction
- crawlable href link discovery
- lazy-loaded content clues
- pagination / load-more / infinite-scroll discovery risk
- current Googlebot fetch-size window checks (2 MB for supported file types, 64 MB for PDFs)
- sitemap/canonical/indexability consistency sampling
- text-based file / Content-Type sanity checks
"""

from __future__ import annotations

import csv
import json
import queue
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import google_crawl_auditor_gui_v3_sitewide as base
except ImportError as exc:
    raise SystemExit(
        "This script must be kept in the same folder as "
        "'google_crawl_auditor_gui_v3_sitewide.py'."
    ) from exc


APP_TITLE = "Google Crawl Auditor - SEO Team Edition v4  |  © Ahmed Oueslati"
DEFAULT_CRAWL_DEPTH = 3
MAX_CRAWL_DEPTH_ALLOWED = 6

CURRENT_GOOGLE_CHECKS_TEXT = """Checks included in this version (single page and full website):
- Mobile-first indexing parity: compares mobile-oriented and desktop fetch clues.
- Crawlable internal links: checks whether pages expose real <a href> links for discovery.
- robots.txt and noindex interaction: flags blocked+noindex conflicts.
- Pagination / load more / infinite scroll risk: checks whether deeper pages are discoverable through href URLs.
- Lazy-loaded content clues: warns when content looks overly dependent on data-src / JS-only loading.
- Current Googlebot fetch-size window: checks oversized HTML/resources and oversized PDFs.
- Sitemap + canonical sanity: samples whether sitemap URLs look live, indexable, and aligned.
- File-type / Content-Type sanity: checks whether text-based indexable files are served correctly.
- JavaScript rendering clues: warns when pages look like thin JS shells with weak HTML discovery.
"""

SEVERITY_ORDER = base.SEVERITY_ORDER
SEVERITY_COLORS = base.SEVERITY_COLORS
MAX_PAGES_ALLOWED = base.MAX_PAGES_ALLOWED
MAX_SITE_PAGES_DEFAULT = base.MAX_SITE_PAGES_DEFAULT
NON_HTML_FILE_EXTENSIONS = base.NON_HTML_FILE_EXTENSIONS


@dataclass
class CrawlVisit:
    seq: int
    url: str
    depth: int
    parent_url: str
    discovery_method: str
    page_type: str
    status: Optional[int]
    score: int
    indexability: str
    main_issue: str
    summary: str


class CrawlAuditor(base.CrawlAuditor):
    def _highest_finding_from_list(self, findings: List[base.Finding]) -> Optional[base.Finding]:
        non_info = [f for f in findings if f.severity != "INFO"]
        if not non_info:
            return None
        return sorted(non_info, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.title.lower()))[0]

    def _build_primary_directives_summary(self, result: base.PageAuditResult) -> str:
        directives: List[str] = []
        if result.meta_robots:
            directives.append(f"Meta robots: {result.meta_robots}")
        if result.x_robots_tag:
            directives.append(f"X-Robots-Tag: {result.x_robots_tag}")
        if result.canonical:
            directives.append(f"Canonical: {self._clean_url_for_display(result.canonical)}")
        if result.robots_allows_page is False:
            directives.append("Blocked in robots.txt")
        if not directives:
            directives.append("No major index-control directives detected")
        return " | ".join(directives)

    def _build_page_crawl_explanation(self, page: base.PageAuditResult) -> str:
        parts: List[str] = []
        if getattr(page, "crawl_depth", 0) == 0:
            parts.append("This page was the crawl starting point.")
        else:
            parent = getattr(page, "discovered_from", "") or "another page on the site"
            method = getattr(page, "discovery_method", "") or "internal discovery"
            parts.append(
                f"This page was reached at depth {getattr(page, 'crawl_depth', 0)} via {method} from "
                f"{self._clean_url_for_display(parent)}."
            )

        parts.append(f"Google-facing view: {page.executive_summary}")

        if page.meta_robots or page.x_robots_tag:
            parts.append(f"Index-control signals seen: {self._build_primary_directives_summary(page)}")
        elif page.indexability:
            parts.append(f"Current indexability assessment: {page.indexability}.")

        main_issue = self._highest_finding_from_list(page.findings)
        if main_issue:
            parts.append(
                f"Main issue for this page: {main_issue.title}. "
                f"Why it matters: {main_issue.why_it_matters} "
                f"What to do: {main_issue.what_to_do}"
            )
        else:
            parts.append("No major public crawl/index blocker was detected on this page.")
        return "\n\n".join(parts)

    def _check_content_clues(self, result: base.PageAuditResult, response) -> None:
        super()._check_content_clues(result, response)
        if not self._is_html_response(response):
            return
        soup = base.BeautifulSoup(response.text, "html.parser")

        lazy_candidates = 0
        for tag in soup.find_all(["img", "iframe", "source"]):
            attrs = {k.lower(): str(v).strip() for k, v in tag.attrs.items()}
            if any(key in attrs for key in ("data-src", "data-lazy-src", "data-srcset", "data-original")) and not attrs.get("src") and not attrs.get("srcset"):
                lazy_candidates += 1

        if lazy_candidates >= 5:
            result.add(
                "MEDIUM",
                "Lazy-loaded content may be hard to discover",
                f"Detected {lazy_candidates} media/content elements that rely on data-src/data-srcset style attributes without normal src/srcset values.",
                "Google can handle some lazy loading, but weak implementations can hide content and media from crawling or delay discovery.",
                "Use search-friendly lazy loading. Make sure important content and media can still be discovered through normal HTML patterns or tested rendering output.",
                "Developer / SEO",
                "Rendering",
            )

        if "application/pdf" in (response.headers.get("Content-Type", "").lower()):
            size = len(response.content or b"")
            if size > 64 * 1024 * 1024:
                result.add(
                    "HIGH",
                    "PDF exceeds Google's 64 MB fetch window",
                    f"Downloaded PDF size is about {size / (1024 * 1024):.2f} MB.",
                    "Google documents that PDFs have a larger fetch window than normal text-based files, but extremely large PDFs can still be partially processed.",
                    "Reduce PDF size or split the document if critical searchable content appears late in the file.",
                    "Developer / SEO",
                    "Rendering",
                )

    def _check_links(self, result: base.PageAuditResult, response) -> None:
        super()._check_links(result, response)
        if not self._is_html_response(response):
            return
        soup = base.BeautifulSoup(response.text, "html.parser")
        button_like = 0
        href_like = result.crawlable_internal_link_count
        for node in soup.find_all(["button", "div", "span"]):
            text = node.get_text(" ", strip=True).lower()
            onclick = str(node.get("onclick") or "").lower()
            role = str(node.get("role") or "").lower()
            if ("location" in onclick or "href" in onclick or role == "button") and text:
                button_like += 1
        if button_like >= 5 and href_like <= 3:
            result.add(
                "MEDIUM",
                "Navigation may rely too much on buttons or JS actions",
                f"Detected {button_like} button-like navigation elements but only {href_like} crawlable internal href links.",
                "Google documentation emphasizes crawlable href links for discovery. Heavy reliance on clicks or JS actions can reduce page discovery.",
                "Expose important navigation and deeper pages through real <a href> links in the HTML.",
                "Developer / SEO",
                "Internal linking",
            )

    def audit_page(self, raw_url: str, shared_robots=None, run_mobile_check: bool = True):
        result = super().audit_page(raw_url, shared_robots=shared_robots, run_mobile_check=run_mobile_check)
        result.primary_directives = self._build_primary_directives_summary(result)
        if not getattr(result, "crawl_explanation", ""):
            result.crawl_explanation = result.executive_summary
        return result

    def audit_site(
        self,
        raw_url: str,
        max_pages: int = MAX_SITE_PAGES_DEFAULT,
        depth_limit: int = DEFAULT_CRAWL_DEPTH,
        stop_checker=None,
        progress_callback=None,
    ):
        site = base.SiteAuditResult(
            input_url=raw_url.strip(),
            pages_requested_limit=max(1, min(MAX_PAGES_ALLOWED, int(max_pages))),
        )
        site.crawl_depth_limit = max(1, min(MAX_CRAWL_DEPTH_ALLOWED, int(depth_limit)))
        site.crawl_visits = []
        site.max_depth_reached = 0

        try:
            home = self._normalize_url(raw_url)
            site.normalized_url = home
            parsed = urlparse(home)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            site.final_site_url = base_url
            site.site_domain = parsed.netloc.lower()

            robots = self._load_robots_context(base_url)

            crawl_queue: List[Dict[str, object]] = []
            seen_queue = set()
            crawled_signatures = set()

            def enqueue(url: str, depth: int, parent_url: str, discovery_method: str, path: List[str]) -> None:
                if depth > site.crawl_depth_limit or not url:
                    return
                try:
                    absolute = self._normalize_url(url)
                except Exception:
                    return
                if not self._same_domain(absolute, site.site_domain):
                    return
                parsed_u = urlparse(absolute)
                if any(parsed_u.path.lower().endswith(ext) for ext in NON_HTML_FILE_EXTENSIONS):
                    return
                cleaned = urlunparse((parsed_u.scheme, parsed_u.netloc, parsed_u.path or "/", "", parsed_u.query, ""))
                sig = self._url_signature(cleaned)
                if sig in seen_queue or sig in crawled_signatures:
                    return
                seen_queue.add(sig)
                crawl_queue.append(
                    {
                        "url": cleaned,
                        "depth": depth,
                        "parent_url": parent_url,
                        "discovery_method": discovery_method,
                        "path": list(path),
                    }
                )

            enqueue(home, 0, "", "start URL", [])

            if robots.sitemap_urls:
                sitemap_urls = self._collect_sitemap_urls(base_url, robots.sitemap_urls)
                if sitemap_urls:
                    site.crawl_notes.append(f"Loaded {len(sitemap_urls)} same-domain URL(s) from the XML sitemap set.")
                    for sm_url in sitemap_urls:
                        enqueue(sm_url, 1, robots.robots_url, "sitemap", [home])
                else:
                    site.crawl_notes.append("Sitemap files were found, but no same-domain URLs were extracted.")
            else:
                site.crawl_notes.append("No sitemap discovered in robots.txt or common sitemap paths.")

            crawl_round = 0
            while crawl_queue and site.pages_crawled < site.pages_requested_limit:
                if stop_checker and stop_checker():
                    site.crawl_notes.append("Stopped early by user request.")
                    break

                item = crawl_queue.pop(0)
                target = str(item["url"])
                depth = int(item["depth"])
                parent_url = str(item["parent_url"])
                discovery_method = str(item["discovery_method"])
                path = list(item["path"])

                sig = self._url_signature(target)
                if sig in crawled_signatures:
                    continue

                crawl_round += 1
                if progress_callback:
                    progress_callback(
                        f"Crawling page {site.pages_crawled + 1}/{site.pages_requested_limit} | "
                        f"depth {depth}/{site.crawl_depth_limit} | {target}"
                    )

                page = self.audit_page(target, shared_robots=robots, run_mobile_check=(crawl_round <= min(10, site.pages_requested_limit)))
                crawled_signatures.add(sig)

                page.crawl_depth = depth
                page.discovered_from = parent_url
                page.discovery_method = discovery_method
                page.crawl_path = path + [page.final_url or target]
                page.crawl_explanation = self._build_page_crawl_explanation(page)

                site.page_results.append(page)
                site.pages_crawled += 1
                site.max_depth_reached = max(site.max_depth_reached, depth)

                main_issue = self._highest_finding_from_list(page.findings)
                site.crawl_visits.append(
                    CrawlVisit(
                        seq=site.pages_crawled,
                        url=page.final_url or page.input_url,
                        depth=depth,
                        parent_url=parent_url,
                        discovery_method=discovery_method,
                        page_type=page.page_type,
                        status=page.final_status,
                        score=page.score,
                        indexability=page.indexability,
                        main_issue=(main_issue.title if main_issue else "No major issue"),
                        summary=page.executive_summary,
                    )
                )

                site.crawl_notes.append(
                    f"[{site.pages_crawled}] depth {depth} -> {self._clean_url_for_display(page.final_url or page.input_url)} "
                    f"(found via {discovery_method}{' from ' + self._clean_url_for_display(parent_url) if parent_url else ''})"
                )

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

                if depth < site.crawl_depth_limit:
                    for discovered in page.discovered_internal_urls:
                        enqueue(discovered, depth + 1, page.final_url or page.input_url, "internal href", page.crawl_path)

            super()._aggregate_site_findings(site, robots)
            self._add_v4_sitewide_findings(site)
            self._calculate_site_score(site)
            self._build_site_summary(site)
        except Exception as exc:  # noqa: BLE001
            site.error = str(exc)
            site.sitewide_findings.append(
                base.Finding(
                    severity="CRITICAL",
                    title="Site audit failed",
                    details=str(exc),
                    why_it_matters="The sitewide crawl could not finish cleanly.",
                    what_to_do="Retry the crawl. If this repeats, test the homepage manually and check whether the site blocks automated requests or has unstable responses.",
                    owner="Developer / DevOps",
                    category="Tooling",
                    sample_urls=[],
                )
            )
            self._calculate_site_score(site)
            self._build_site_summary(site)

        return site

    def _add_v4_sitewide_findings(self, site) -> None:
        if getattr(site, "max_depth_reached", 0) < site.crawl_depth_limit and site.pages_crawled < site.pages_requested_limit:
            site.sitewide_findings.append(
                base.Finding(
                    severity="LOW",
                    title="Site sample did not naturally reach the full requested depth",
                    details=f"Requested crawl depth was {site.crawl_depth_limit}, but the deepest sampled page reached depth {getattr(site, 'max_depth_reached', 0)}.",
                    why_it_matters="This usually means the visible internal linking structure is shallow or the sampled area is tightly interlinked.",
                    what_to_do="Review whether important deeper sections are linked from category, hub, or navigation pages. If needed, increase crawl limits or improve internal linking.",
                    owner="SEO / Developer",
                    category="Internal linking",
                    sample_urls=[],
                )
            )

        sitemap_problem_pages = [
            p for p in site.page_results
            if getattr(p, "discovery_method", "") == "sitemap"
            and (
                (p.final_status or 0) >= 300
                or self._page_has_noindex(p)
                or any(f.title == "Canonical points to another page" for f in p.findings)
            )
        ]
        if sitemap_problem_pages:
            site.sitewide_findings.append(
                base.Finding(
                    severity="MEDIUM",
                    title="Some sitemap URLs do not look like clean canonical indexable URLs",
                    details=f"{len(sitemap_problem_pages)} sampled sitemap-discovered URL(s) redirected, were noindex, or hinted at another canonical target.",
                    why_it_matters="Google recommends that XML sitemaps focus on the preferred live canonical URL set.",
                    what_to_do="Keep only final canonical 200 URLs in XML sitemaps. Remove URLs that redirect, are intentionally noindex, or consolidate elsewhere.",
                    owner="SEO / Developer",
                    category="Discovery",
                    sample_urls=[p.final_url or p.input_url for p in sitemap_problem_pages[:5]],
                )
            )

    def _build_site_summary(self, site) -> None:
        super()._build_site_summary(site)
        site.executive_summary = (
            f"This full-website audit crawled {site.pages_crawled} URL(s) on {site.site_domain}, "
            f"reached depth {getattr(site, 'max_depth_reached', 0)} of the requested {getattr(site, 'crawl_depth_limit', DEFAULT_CRAWL_DEPTH)}, "
            "and keeps the crawl path visible so the SEO team can see how discovery happened page by page.\n\n"
            f"{site.executive_summary}"
        )
        if not site.top_actions:
            site.top_actions = []
        site.top_actions = [
            f"Use the Pages tab to review every visited URL with its explanation.",
            f"Use the Navigation tab to see how the crawler moved from page to page and where discovery came from.",
        ] + site.top_actions[:5]
        site.summary = (
            f"{site.verdict}. Score: {site.score}/100. Pages crawled: {site.pages_crawled}. "
            f"Depth reached: {getattr(site, 'max_depth_reached', 0)}/{getattr(site, 'crawl_depth_limit', DEFAULT_CRAWL_DEPTH)}. "
            f"Critical: {sum(1 for f in site.sitewide_findings if f.severity == 'CRITICAL')}, "
            f"High: {sum(1 for f in site.sitewide_findings if f.severity == 'HIGH')}, "
            f"Medium: {sum(1 for f in site.sitewide_findings if f.severity == 'MEDIUM')}."
        )


class AuditorGUI(base.AuditorGUI):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1700x1020")
        self.root.minsize(1280, 800)

        self.auditor = CrawlAuditor()
        self.results: List[object] = []
        self.result_map: Dict[str, object] = {}
        self.queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_requested = False
        self.page_row_map: Dict[str, object] = {}
        self.nav_row_map: Dict[str, CrawlVisit] = {}

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=0)

        top = ttk.Frame(self.root, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Paste one website or page URL per line", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.url_text = tk.Text(top, height=5, wrap="word")
        self.url_text.grid(row=1, column=0, columnspan=12, sticky="nsew", pady=(6, 8))
        self.url_text.insert("1.0", "https://example.com")

        controls = ttk.Frame(top)
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(20, weight=1)

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

        ttk.Label(controls, text="Depth:").grid(row=0, column=12, padx=(0, 4))
        self.depth_var = tk.IntVar(value=DEFAULT_CRAWL_DEPTH)
        self.depth_spin = ttk.Spinbox(controls, from_=1, to=MAX_CRAWL_DEPTH_ALLOWED, increment=1, textvariable=self.depth_var, width=4)
        self.depth_spin.grid(row=0, column=13, padx=(0, 12))

        self.progress = ttk.Progressbar(controls, mode="determinate", length=220)
        self.progress.grid(row=0, column=14, padx=(0, 8))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=20, sticky="w")

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
        self.pages_tab = ttk.Frame(self.notebook, padding=10)
        self.navigation_tab = ttk.Frame(self.notebook, padding=10)
        self.technical_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.overview_tab, text="Overview")
        self.notebook.add(self.actions_tab, text="Issues & Actions")
        self.notebook.add(self.pages_tab, text="Pages")
        self.notebook.add(self.navigation_tab, text="Navigation")
        self.notebook.add(self.technical_tab, text="Technical")

        self._build_overview_tab()
        self._build_actions_tab()
        self._build_pages_tab()
        self._build_navigation_tab()
        self._build_technical_tab()

        main_pane.add(left_frame, weight=3)
        main_pane.add(right_frame, weight=4)

    def _build_pages_tab(self) -> None:
        self.pages_tab.columnconfigure(0, weight=1)
        self.pages_tab.rowconfigure(0, weight=1)
        pane = ttk.Panedwindow(self.pages_tab, orient=tk.VERTICAL)
        pane.grid(row=0, column=0, sticky="nsew")

        top_frame = ttk.Frame(pane)
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(0, weight=1)
        self.pages_tree = ttk.Treeview(
            top_frame,
            columns=("depth", "url", "http", "score", "indexability", "page_type", "main_issue"),
            show="headings",
            height=16,
        )
        headings = {
            "depth": "Depth",
            "url": "Page URL",
            "http": "HTTP",
            "score": "Score",
            "indexability": "Indexability",
            "page_type": "Page type",
            "main_issue": "Main issue",
        }
        widths = {"depth": 60, "url": 500, "http": 60, "score": 60, "indexability": 180, "page_type": 170, "main_issue": 300}
        for col in headings:
            self.pages_tree.heading(col, text=headings[col])
            self.pages_tree.column(col, width=widths[col], anchor="w")
        self.pages_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(top_frame, orient="vertical", command=self.pages_tree.yview)
        self.pages_tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.pages_tree.bind("<<TreeviewSelect>>", self.on_page_select)

        detail_frame = ttk.LabelFrame(pane, text="Visited page explanation")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.page_detail_text = tk.Text(detail_frame, wrap="word", height=14)
        self.page_detail_text.grid(row=0, column=0, sticky="nsew")
        y2 = ttk.Scrollbar(detail_frame, orient="vertical", command=self.page_detail_text.yview)
        self.page_detail_text.configure(yscrollcommand=y2.set, state="disabled")
        y2.grid(row=0, column=1, sticky="ns")

        pane.add(top_frame, weight=3)
        pane.add(detail_frame, weight=2)

    def _build_navigation_tab(self) -> None:
        self.navigation_tab.columnconfigure(0, weight=1)
        self.navigation_tab.rowconfigure(0, weight=1)
        pane = ttk.Panedwindow(self.navigation_tab, orient=tk.VERTICAL)
        pane.grid(row=0, column=0, sticky="nsew")

        top_frame = ttk.Frame(pane)
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(0, weight=1)
        self.nav_tree = ttk.Treeview(
            top_frame,
            columns=("seq", "depth", "from_url", "to_url", "method", "http", "score"),
            show="headings",
            height=16,
        )
        headings = {
            "seq": "#",
            "depth": "Depth",
            "from_url": "From",
            "to_url": "To",
            "method": "Discovery",
            "http": "HTTP",
            "score": "Score",
        }
        widths = {"seq": 45, "depth": 55, "from_url": 330, "to_url": 420, "method": 110, "http": 60, "score": 60}
        for col in headings:
            self.nav_tree.heading(col, text=headings[col])
            self.nav_tree.column(col, width=widths[col], anchor="w")
        self.nav_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(top_frame, orient="vertical", command=self.nav_tree.yview)
        self.nav_tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.nav_tree.bind("<<TreeviewSelect>>", self.on_nav_select)

        detail_frame = ttk.LabelFrame(pane, text="Navigation explanation")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.nav_detail_text = tk.Text(detail_frame, wrap="word", height=14)
        self.nav_detail_text.grid(row=0, column=0, sticky="nsew")
        y2 = ttk.Scrollbar(detail_frame, orient="vertical", command=self.nav_detail_text.yview)
        self.nav_detail_text.configure(yscrollcommand=y2.set, state="disabled")
        y2.grid(row=0, column=1, sticky="ns")

        pane.add(top_frame, weight=3)
        pane.add(detail_frame, weight=2)

    def _build_technical_tab(self) -> None:
        self.technical_tab.columnconfigure(0, weight=1)
        self.technical_tab.rowconfigure(0, weight=1)
        pane = ttk.Panedwindow(self.technical_tab, orient=tk.VERTICAL)
        pane.grid(row=0, column=0, sticky="nsew")

        checks_frame = ttk.LabelFrame(pane, text="Google-aligned checks included")
        checks_frame.columnconfigure(0, weight=1)
        checks_frame.rowconfigure(0, weight=1)
        self.checks_text = tk.Text(checks_frame, wrap="word", height=10)
        self.checks_text.grid(row=0, column=0, sticky="nsew")
        self.checks_text.insert("1.0", CURRENT_GOOGLE_CHECKS_TEXT)
        self.checks_text.configure(state="disabled")
        ys1 = ttk.Scrollbar(checks_frame, orient="vertical", command=self.checks_text.yview)
        self.checks_text.configure(yscrollcommand=ys1.set)
        ys1.grid(row=0, column=1, sticky="ns")

        detail_frame = ttk.LabelFrame(pane, text="Technical details")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(detail_frame, wrap="word")
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=yscroll.set, state="disabled")
        yscroll.grid(row=0, column=1, sticky="ns")

        pane.add(checks_frame, weight=1)
        pane.add(detail_frame, weight=3)

        # ── Ownership footer ─────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg="#1a1a2e", pady=4)
        footer.grid(row=2, column=0, sticky="ew")
        tk.Label(
            footer,
            text="© 2026  Ahmed Oueslati  |  ahmedoueslati6110@gmail.com  |  All rights reserved",
            bg="#1a1a2e",
            fg="#c8d3e8",
            font=("Segoe UI", 9),
        ).pack()

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
        self.page_row_map.clear()
        self.nav_row_map.clear()
        self.tree.delete(*self.tree.get_children())
        self.pages_tree.delete(*self.pages_tree.get_children())
        self.nav_tree.delete(*self.nav_tree.get_children())
        self.issues_tree.delete(*self.issues_tree.get_children())
        self._set_text(self.summary_text, "")
        self._set_text(self.top_actions_text, "")
        self._set_text(self.detail_text, "")
        self._set_text(self.page_detail_text, "")
        self._set_text(self.nav_detail_text, "")
        self.score_canvas.delete("all")
        self.severity_canvas.delete("all")

        mode = self.mode_var.get()
        max_pages = max(1, min(MAX_PAGES_ALLOWED, int(self.max_pages_var.get() or MAX_SITE_PAGES_DEFAULT)))
        depth = max(1, min(MAX_CRAWL_DEPTH_ALLOWED, int(self.depth_var.get() or DEFAULT_CRAWL_DEPTH)))
        self.progress.configure(maximum=len(urls), value=0)
        self.status_var.set(f"Starting {mode} audit for {len(urls)} target(s)...")

        def worker() -> None:
            for idx, url in enumerate(urls, start=1):
                if self.stop_requested:
                    break
                self.queue.put(("status", f"Auditing {idx}/{len(urls)}: {url}"))
                if mode == "site":
                    result = self.auditor.audit_site(
                        url,
                        max_pages=max_pages,
                        depth_limit=depth,
                        stop_checker=lambda: self.stop_requested,
                        progress_callback=lambda msg: self.queue.put(("status", msg)),
                    )
                else:
                    result = self.auditor.audit_page(url)
                self.queue.put(("result", result))
                self.queue.put(("progress", idx))
            self.queue.put(("done", None))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def on_tree_select(self, event: object | None = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        result = self.result_map.get(selected[0])
        if not result:
            return

        self.detail_title.set(f"SEO view for {result.input_url}")
        self._draw_score_chart(result)
        self._draw_severity_chart(result)

        self.issues_tree.delete(*self.issues_tree.get_children())
        self.pages_tree.delete(*self.pages_tree.get_children())
        self.nav_tree.delete(*self.nav_tree.get_children())
        self.page_row_map.clear()
        self.nav_row_map.clear()

        if isinstance(result, base.SiteAuditResult):
            summary_lines = [
                "Mode: Full website",
                f"Site: {result.site_domain}",
                f"Pages crawled: {result.pages_crawled}/{result.pages_requested_limit}",
                f"Depth reached: {getattr(result, 'max_depth_reached', 0)}/{getattr(result, 'crawl_depth_limit', DEFAULT_CRAWL_DEPTH)}",
                f"Verdict: {result.verdict}",
                f"Indexability: {result.indexability}",
                "",
                result.executive_summary,
                "",
                f"Quick summary: {result.summary}",
            ]
            self._set_text(self.summary_text, "\n".join(summary_lines))
            self._set_text(self.top_actions_text, "\n\n".join(f"{i}. {a}" for i, a in enumerate(result.top_actions, start=1)))

            for f in sorted(result.sitewide_findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), x.title.lower())):
                self.issues_tree.insert(
                    "",
                    "end",
                    values=(f.severity, f.title, f.why_it_matters, f.what_to_do, f.owner, " | ".join(self.auditor._clean_url_for_display(u) for u in f.sample_urls)),
                )

            for p in result.page_results:
                main_issue = self._highest_priority_finding(p)
                item_id = self.pages_tree.insert(
                    "",
                    "end",
                    values=(
                        getattr(p, "crawl_depth", 0),
                        p.final_url or p.input_url,
                        p.final_status or "",
                        p.score,
                        p.indexability,
                        p.page_type,
                        main_issue.title if main_issue else "No major issue",
                    ),
                )
                self.page_row_map[item_id] = p

            for visit in getattr(result, "crawl_visits", []):
                item_id = self.nav_tree.insert(
                    "",
                    "end",
                    values=(
                        visit.seq,
                        visit.depth,
                        self.auditor._clean_url_for_display(visit.parent_url) if visit.parent_url else "Start URL",
                        self.auditor._clean_url_for_display(visit.url),
                        visit.discovery_method,
                        visit.status or "",
                        visit.score,
                    ),
                )
                self.nav_row_map[item_id] = visit

            self._set_text(self.page_detail_text, "Select a page row to see the explanation for that visited page.")
            self._set_text(self.nav_detail_text, self._format_navigation_overview(result))
            self._set_text(self.detail_text, self._format_site_technical_details(result))
        else:
            summary_lines = [
                "Mode: Single page",
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

            for f in sorted(result.findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 99), x.title.lower())):
                self.issues_tree.insert("", "end", values=(f.severity, f.title, f.why_it_matters, f.what_to_do, f.owner, ""))

            item_id = self.pages_tree.insert(
                "",
                "end",
                values=(0, result.final_url or result.input_url, result.final_status or "", result.score, result.indexability, result.page_type, (self._highest_priority_finding(result).title if self._highest_priority_finding(result) else "No major issue")),
            )
            self.page_row_map[item_id] = result
            self._set_text(self.page_detail_text, self._format_page_visit_details(result))
            self._set_text(self.nav_detail_text, "Single page mode does not perform site navigation. Use full website mode to see page-to-page discovery.")
            self._set_text(self.detail_text, self._format_page_technical_details(result))

    def on_page_select(self, event: object | None = None) -> None:
        selected = self.pages_tree.selection()
        if not selected:
            return
        page = self.page_row_map.get(selected[0])
        if not page:
            return
        self._set_text(self.page_detail_text, self._format_page_visit_details(page))

    def on_nav_select(self, event: object | None = None) -> None:
        selected = self.nav_tree.selection()
        if not selected:
            return
        visit = self.nav_row_map.get(selected[0])
        if not visit:
            return
        lines = [
            f"Visit #{visit.seq}",
            f"Depth: {visit.depth}",
            f"From: {visit.parent_url or 'Start URL'}",
            f"To: {visit.url}",
            f"Discovery method: {visit.discovery_method}",
            f"Page type: {visit.page_type}",
            f"HTTP status: {visit.status}",
            f"Score: {visit.score}/100",
            f"Indexability: {visit.indexability}",
            f"Main issue: {visit.main_issue}",
            "",
            visit.summary,
        ]
        self._set_text(self.nav_detail_text, "\n".join(lines))

    def _format_navigation_overview(self, site) -> str:
        lines = [
            f"Requested crawl depth: {getattr(site, 'crawl_depth_limit', DEFAULT_CRAWL_DEPTH)}",
            f"Depth reached: {getattr(site, 'max_depth_reached', 0)}",
            "",
            "Crawl trail:",
        ]
        if site.crawl_notes:
            lines.extend(f"- {note}" for note in site.crawl_notes)
        else:
            lines.append("- No crawl notes recorded.")
        return "\n".join(lines)

    def _format_page_visit_details(self, page) -> str:
        main_issue = self._highest_priority_finding(page)
        lines = [
            f"URL: {page.final_url or page.input_url}",
            f"Depth: {getattr(page, 'crawl_depth', 0)}",
            f"Discovered from: {getattr(page, 'discovered_from', '') or 'Start URL / direct page check'}",
            f"Discovery method: {getattr(page, 'discovery_method', '') or 'Direct check'}",
            f"Page type: {page.page_type}",
            f"HTTP status: {page.final_status}",
            f"Score: {page.score}/100",
            f"Indexability: {page.indexability}",
            f"Primary directives: {getattr(page, 'primary_directives', '') or 'None'}",
            f"Main issue: {main_issue.title if main_issue else 'No major issue'}",
            "",
            getattr(page, "crawl_explanation", page.executive_summary),
        ]
        if getattr(page, "crawl_path", None):
            lines.extend(["", "Path so far:"] + [f"- {u}" for u in page.crawl_path])
        return "\n".join(lines)

    def _format_page_technical_details(self, result) -> str:
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
            f"Meta robots: {result.meta_robots or 'None'}",
            f"X-Robots-Tag: {result.x_robots_tag or 'None'}",
            f"Canonical: {result.canonical or 'None'}",
            f"Title: {result.title_text or 'None'}",
            f"Viewport tag present: {result.viewport_present}",
            f"Internal links found: {result.internal_link_count}",
            f"Crawlable internal links found: {result.crawlable_internal_link_count}",
            f"CSS/JS checked: {result.css_js_checked}",
            f"Broken/blocked CSS/JS: {result.css_js_blocked_or_broken}",
            f"Visible text length: {result.text_length}",
            f"Script tags: {result.script_count}",
            f"Mobile parity checked: {result.mobile_test_run}",
            f"Mobile/Desktop mismatch detected: {result.mobile_desktop_mismatch}",
            "",
            "Findings",
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

    def _format_site_technical_details(self, site) -> str:
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
            f"Crawl depth limit: {getattr(site, 'crawl_depth_limit', DEFAULT_CRAWL_DEPTH)}",
            f"Pages crawled: {site.pages_crawled}",
            f"HTML pages crawled: {site.html_pages_crawled}",
            f"Max depth reached: {getattr(site, 'max_depth_reached', 0)}",
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
            lines.extend(f"- {note}" for note in site.crawl_notes)
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
        lines.extend(["", "Visited page list", "-" * 90])
        for p in site.page_results:
            issue = self._highest_priority_finding(p)
            lines.append(
                f"- depth {getattr(p, 'crawl_depth', 0)} | {p.final_url or p.input_url} | "
                f"HTTP {p.final_status} | Score {p.score} | {p.indexability} | "
                f"{issue.title if issue else 'No major issue'}"
            )
        return "\n".join(lines)

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
                writer.writerow(["target", "mode", "pages_crawled", "score", "verdict", "indexability", "summary", "main_issue"])
                for r in self.results:
                    main_issue = self._highest_priority_finding(r)
                    writer.writerow([
                        r.input_url,
                        "site" if isinstance(r, base.SiteAuditResult) else "page",
                        r.pages_crawled if isinstance(r, base.SiteAuditResult) else 1,
                        r.score,
                        r.verdict,
                        r.indexability,
                        r.summary,
                        main_issue.title if main_issue else "",
                    ])
                    if isinstance(r, base.SiteAuditResult):
                        writer.writerow([])
                        writer.writerow(["seq", "depth", "page_url", "from_url", "discovery", "http", "score", "indexability", "page_type", "main_issue"])
                        for visit in getattr(r, "crawl_visits", []):
                            writer.writerow([
                                visit.seq, visit.depth, visit.url, visit.parent_url, visit.discovery_method,
                                visit.status, visit.score, visit.indexability, visit.page_type, visit.main_issue,
                            ])
                        writer.writerow([])
            self.status_var.set(f"CSV exported: {path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export CSV error", str(exc))

    def _serialize_result(self, r):
        if isinstance(r, base.SiteAuditResult):
            payload = asdict(r)
            payload["crawl_depth_limit"] = getattr(r, "crawl_depth_limit", DEFAULT_CRAWL_DEPTH)
            payload["max_depth_reached"] = getattr(r, "max_depth_reached", 0)
            payload["crawl_visits"] = [asdict(v) for v in getattr(r, "crawl_visits", [])]
            payload["page_results"] = [self._serialize_result(p) for p in r.page_results]
            return payload
        payload = asdict(r)
        payload["crawl_depth"] = getattr(r, "crawl_depth", 0)
        payload["discovered_from"] = getattr(r, "discovered_from", "")
        payload["discovery_method"] = getattr(r, "discovery_method", "")
        payload["crawl_path"] = list(getattr(r, "crawl_path", []))
        payload["crawl_explanation"] = getattr(r, "crawl_explanation", "")
        payload["primary_directives"] = getattr(r, "primary_directives", "")
        return payload

    def export_json(self) -> None:
        if not self.results:
            messagebox.showinfo("No data", "Run an audit first.")
            return
        path = filedialog.asksaveasfilename(title="Save JSON", defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([self._serialize_result(r) for r in self.results], f, indent=2, ensure_ascii=False)
            self.status_var.set(f"JSON exported: {path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export JSON error", str(exc))


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
