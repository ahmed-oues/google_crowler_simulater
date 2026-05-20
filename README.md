# Google Crawl Auditor — User Guide
### SEO Team Edition v4

> **Owner:** Ahmed Oueslati · ahmedoueslati6110@gmail.com  
> **Version:** v4 · Last updated: April 2026

---

## Table of Contents

1. [What is this tool?](#1-what-is-this-tool)
2. [Requirements](#2-requirements)
3. [How to launch the app](#3-how-to-launch-the-app)
4. [The interface at a glance](#4-the-interface-at-a-glance)
5. [Running your first audit](#5-running-your-first-audit)
6. [Audit modes explained](#6-audit-modes-explained)
7. [Understanding the results table](#7-understanding-the-results-table)
8. [The detail tabs (right panel)](#8-the-detail-tabs-right-panel)
9. [Severity levels explained](#9-severity-levels-explained)
10. [All Google-aligned checks included](#10-all-google-aligned-checks-included)
11. [Exporting your results](#11-exporting-your-results)
12. [Tips & best practices](#12-tips--best-practices)
13. [Frequently asked questions](#13-frequently-asked-questions)

---

## 1. What is this tool?

**Google Crawl Auditor** is a desktop SEO auditing application that simulates how Googlebot crawls and evaluates your website. It checks every important signal Google uses to decide whether to **crawl, index, and rank** your pages.

It is designed for **SEO teams, developers, and site owners** who want clear, actionable answers to questions like:

- Is Google blocked from crawling my pages?
- Are my pages actually indexable?
- Why is Google not finding my deeper pages?
- Do my pages have mobile/desktop mismatch issues?
- Is my sitemap clean and aligned with my canonical URLs?

---

## 2. Requirements

| Item | Details |
|---|---|
| **Operating system** | Windows 10 / 11 (or macOS / Linux if running from Python) |
| **EXE version** | No installation needed — just double-click `GoogleCrawlAuditor.exe` |
| **Python version** (source only) | Python 3.10 or higher |
| **Python dependencies** (source only) | `requests`, `beautifulsoup4` — install with `pip install requests beautifulsoup4` |
| **Internet connection** | Required — the app fetches live pages |

---

## 3. How to launch the app

### Option A — Using the EXE (recommended)
1. Go to the `dist` folder
2. Double-click **`GoogleCrawlAuditor.exe`**
3. The app opens immediately — no installation required

### Option B — Running from Python source
```bash
# Make sure both files are in the same folder:
# - google_crawl_auditor_gui_v4_sitewide.py  ← main file
# - google_crawl_auditor_gui_v3_sitewide.py  ← required base file

pip install requests beautifulsoup4
python google_crawl_auditor_gui_v4_sitewide.py
```

> ⚠️ Both Python files **must be in the same folder**. The v4 file depends on v3.

---

## 4. The interface at a glance

```
┌──────────────────────────────────────────────────────────────────┐
│  URL input box  (paste one URL per line)                         │
│  [Run audit] [Stop] [Load TXT/CSV] [Clear] [Export CSV/JSON/HTML]│
│  Mode: ○ Full website  ○ Single page   Max pages: [40]  Depth:[3]│
├────────────────────────┬─────────────────────────────────────────┤
│                        │  Overview  │ Issues │ Pages │ Nav │ Tech│
│   Results table        │                                         │
│   (all audited URLs)   │   Detail panel for selected result      │
│                        │                                         │
├────────────────────────┴─────────────────────────────────────────┤
│  © 2026  Ahmed Oueslati  |  ahmedoueslati6110@gmail.com          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Running your first audit

### Step 1 — Enter your URL(s)
- Click inside the **URL input box** at the top
- Type or paste your website URL, for example: `https://example.com`
- You can paste **multiple URLs**, one per line, to audit several sites at once

### Step 2 — Choose your mode
- **Full website** — crawls the entire site (homepage + sitemap + internal links) *(recommended)*
- **Single page** — audits only the exact URL you typed

### Step 3 — Set crawl limits *(Full website mode only)*
| Setting | What it does | Recommended |
|---|---|---|
| **Max pages** | Maximum number of pages to crawl | Start with `40`, increase for larger sites |
| **Depth** | How many link levels deep to follow from the homepage | `3` is the default, `1–6` allowed |

### Step 4 — Click **Run audit**
- A progress bar and status message will update as the crawl runs
- Click **Stop** at any time to safely halt the crawl and keep results so far

### Step 5 — Read your results
- Click any row in the **results table** to see the full SEO explanation in the right panel

---

## 6. Audit modes explained

### 🌐 Full Website Mode
The crawler starts at your homepage, reads your `robots.txt`, loads your XML sitemap(s), then follows all internal links up to the depth and page limits you set.

For each page visited you will see:
- How the page was discovered (sitemap, internal link, start URL)
- Which page it came from
- The crawl depth it was reached at
- Every crawl/index issue found on that page

**Use this mode** for regular site-health checks and pre-launch audits.

### 📄 Single Page Mode
Audits one specific page in isolation. Useful for:
- Quickly checking a page you just published
- Diagnosing a specific indexing problem
- Testing a landing page before a campaign

---

## 7. Understanding the results table

Each row in the left table represents one audited target (a full site or a single page).

| Column | Meaning |
|---|---|
| **Target** | The URL or domain you audited |
| **Mode** | `site` (full website) or `page` (single page) |
| **Pages** | Number of pages crawled for this target |
| **Score** | Overall crawlability score out of 100 |
| **Verdict** | Plain-language summary (e.g. *"Critical issues found"*, *"No major blockers"*) |
| **Indexability** | Google's likely ability to index the site |
| **Main issue** | The single most important problem found |
| **Next step** | The first action you should take |

> 💡 Click any column header to **sort** the table by that column.

---

## 8. The detail tabs (right panel)

When you click a result row, the right panel shows 5 tabs:

### 📋 Overview tab
- Score visualisation (colour-coded gauge)
- Severity breakdown chart (how many Critical / High / Medium / Low issues)
- Plain-language executive summary
- Top 5 actions — the most important things to fix, in priority order

### ⚠️ Issues & Actions tab
A full list of every finding, sorted by severity. For each issue you see:
- **Severity** (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- **What the issue is**
- **Why it matters for Google**
- **Exactly what to do to fix it**
- **Who should fix it** (SEO, Developer, Content, etc.)

### 📑 Pages tab *(Full website mode)*
A table of every page crawled, showing:
- Crawl depth
- Page URL
- HTTP status code
- Score
- Indexability
- Page type
- Main issue

Click any page row to see a **full explanation** of that specific page — how it was found, what issues it has, and what to do.

### 🗺️ Navigation tab *(Full website mode)*
Shows the exact **crawl trail** — how the crawler moved from page to page:
- Which page each URL was discovered from
- What discovery method was used (sitemap, internal href, start URL)
- The HTTP status and score at each hop

Click any navigation row for a plain-language explanation of that specific hop.

### 🔧 Technical tab
- Full list of all Google-aligned checks the tool performs
- Complete technical dump for advanced users (all headers, directives, link counts, etc.)

---

## 9. Severity levels explained

| Level | Colour | Meaning |
|---|---|---|
| 🔴 **CRITICAL** | Red | Googlebot is blocked or the page cannot be indexed at all. Fix immediately. |
| 🟠 **HIGH** | Orange | Serious issue that will significantly hurt crawling or ranking. Fix soon. |
| 🟡 **MEDIUM** | Yellow | Notable problem that reduces crawl efficiency or indexability. Fix when possible. |
| ⚫ **LOW** | Grey | Minor issue or best-practice gap. Fix as part of routine maintenance. |
| 🟢 **INFO** | Green | Informational — no action required, just good to know. |

---

## 10. All Google-aligned checks included

The app runs the following checks on every page, aligned with Google's public documentation (up to April 2026):

| Check | What it looks for |
|---|---|
| **robots.txt access** | Can Google fetch your robots.txt? Is your page allowed? |
| **robots.txt + noindex conflict** | Pages blocked in robots.txt AND marked noindex — Google can't process the noindex if it can't crawl |
| **Meta robots / X-Robots-Tag** | noindex, nofollow, none, nosnippet, unavailable_after |
| **Canonical tag** | Is the canonical present, self-referencing, and pointing to a live URL? |
| **HTTPS** | Is the final URL served over HTTPS? |
| **HTTP status codes** | 200 OK, redirects (3xx), errors (4xx/5xx), soft 404s |
| **Crawlable internal links** | Does the page expose real `<a href>` links for Googlebot to follow? |
| **Mobile-first indexing parity** | Does the mobile version serve substantially similar content to desktop? |
| **Viewport meta tag** | Is the page mobile-friendly? |
| **Page title** | Is a title tag present? |
| **Fetch-size limits** | HTML/resources over 2 MB; PDFs over 64 MB |
| **JavaScript-heavy shell detection** | Does the page look like a thin JS wrapper with little crawlable HTML? |
| **Lazy-loaded content** | Are images/content overly dependent on JavaScript `data-src` attributes? |
| **Pagination / infinite scroll risk** | Are deeper pages reachable through real href links? |
| **XML sitemap health** | Are sitemap URLs live, canonical, and indexable? |
| **Content-Type sanity** | Are text-based files served with the correct Content-Type headers? |
| **Blocked CSS/JS resources** | Are important stylesheets or scripts blocked from Googlebot? |
| **Parameter / faceted URL management** | Are query-string URLs likely to create crawl waste? |

---

## 11. Exporting your results

After running an audit, use the toolbar buttons to export:

| Button | Format | Best for |
|---|---|---|
| **Export CSV** | `.csv` | Excel, Google Sheets, data analysis |
| **Export JSON** | `.json` | Developers, API pipelines, archiving |
| **Export HTML report** | `.html` | Sharing with clients or stakeholders — opens in any browser |

The CSV and JSON exports include **every page crawled**, with all scores, issues, depth, and discovery information.

---

## 12. Tips & best practices

- **Start with depth 3 and 40 pages** for a representative sample of most sites.
- **Increase max pages to 100–200** for large e-commerce or news sites.
- **Use depth 1** if you only want to check the homepage and pages linked directly from it.
- **Load a TXT or CSV file** with the "Load TXT/CSV" button to bulk-audit many URLs at once — put one URL per line in the file.
- **Sort the Issues & Actions tab by severity** to always tackle the most critical problems first.
- **Use the Navigation tab** to diagnose why Google isn't finding deep pages — look for shallow depth reached vs. the limit you set.
- **Run the audit again after fixes** to confirm issues are resolved and watch the score go up.
- If your site requires login or has aggressive bot-blocking, results may be limited — test with a staging environment if needed.

---

## 13. Frequently asked questions

**Q: The score is low — does that mean my site won't rank?**  
A: The score reflects crawlability and indexability health, not ranking directly. A low score means Google may have trouble crawling or indexing your pages, which will hurt ranking. Fix the CRITICAL and HIGH issues first.

**Q: The tool says my page is "Blocked in robots.txt" — what should I do?**  
A: Open your `robots.txt` file (usually at `yourdomain.com/robots.txt`) and look for a `Disallow:` rule that covers the blocked page. Remove or adjust the rule if you want Google to crawl it.

**Q: What does "noindex" mean?**  
A: A `noindex` directive tells Google not to include the page in search results. If this is unintentional, remove the `<meta name="robots" content="noindex">` tag or the `X-Robots-Tag: noindex` header from the page.

**Q: The crawl stopped before reaching all my pages — why?**  
A: Either the **Max pages** limit was reached, or you clicked **Stop**, or the site's internal link structure didn't expose more pages within the crawl depth. Try increasing Max pages or Depth, or check the Navigation tab to see where discovery stopped.

**Q: Can I audit a password-protected site?**  
A: Not directly. The tool audits pages as a public user (similar to Googlebot). For protected pages, test them from a staging or pre-production environment that is publicly accessible.

**Q: Why do I see "robots.txt + noindex conflict"?**  
A: Google says: if a page is blocked in robots.txt, it cannot read the noindex tag on that page. This means the page might stay in Google's index even though you intended it to be removed. Either allow robots to crawl the page so it can read the noindex, or remove both the block and noindex and use other methods.

**Q: What is "mobile-first indexing parity"?**  
A: Google primarily crawls and indexes the mobile version of your pages. If your mobile page has significantly less content than your desktop page, Google may under-index your content. The tool checks for visible signs of this mismatch.

---

*© 2026 Ahmed Oueslati — All rights reserved.*

