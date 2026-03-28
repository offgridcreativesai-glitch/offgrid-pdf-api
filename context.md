# OffGrid Creatives AI — Context File
> This file defines the full system state. Read this + session_log.md every session start.
> Last updated: 2026-03-28

---

## 1. Product Vision

**OffGrid Creatives AI** is a pre-launch ad intelligence SaaS.
It tells brands *what* to advertise and *why* — before they spend a single rupee/dollar.

**Core promise:** Submit a form → receive a branded PDF intelligence report in under 10 minutes — built entirely from real scraped data. Zero human involvement after submission.

**Not a campaign planning tool.** Not a creative generator. Pure intelligence, delivered before the decision is made.

---

## 2. Founder & Business Context

- **Founder:** Gaurav Khanna (GK), Surat, Gujarat
- **Other businesses:** Third Gen Tribe (graphic t-shirts, DTF print), Dhaga Ethnic House (women's ethnic wear B2C)
- **Working style:** GK + Claude = strategists. Claude Code = all coding. Non-negotiable division of labour
- **Tone:** Direct, mentor-level, capital-builder mindset. No cushioning
- **Accounts:** All under `offgridcreativesai@gmail.com`

---

## 3. Product Suite

| Report | Name | Status | Trigger |
|--------|------|--------|---------|
| Report 1 Option 1 | Social Media Brand Audit + Competitor Research | 🟡 Pipeline built, quality fixes pending | Instagram data |
| Report 1 Option 2 | New Product Launch Intelligence | 🔴 Not built yet | Instagram data |
| Report 2 | Pre-Ads Intelligence (18 sections) | 🟡 Built, Railway 500 error blocking | Meta Ad Library |
| Report 3 | Post-Ads Intelligence | 🔴 Not started | TBD |

**Data flow:** Report 1 → feeds context into Report 2 → Report 2 predictions validated by Report 3

---

## 4. Tech Stack

```
Google Forms → Make.com → Apify → Claude API → Railway Flask API → Gmail
```

| Component | Tool | Detail |
|-----------|------|--------|
| Client input | Google Forms | Branching form — Option 1 or Option 2 |
| Automation | Make.com | Orchestrates all modules |
| Data scraping | Apify | Instagram scrapers (see actors below) |
| AI analysis | Claude API | claude-sonnet-4-20250514, max_tokens 16000 |
| PDF generation | Railway Flask + ReportLab | `https://web-production-175d5.up.railway.app` |
| Email delivery | Gmail via Make.com | PDF as base64 attachment |
| Frontend | Bubble | Blank — build last |
| Payments | Razorpay | Existing account |

### Apify Actors in Use
- `apify/instagram-hashtag-scraper` — Category scrape (keyword + hashtag mode, 50 posts)
- `apify/instagram-post-scraper` — Brand profile + competitor profiles (20 posts each)
- `apify/facebook-ads-scraper` — Meta Ad Library (Report 2)

### Railway
- URL: `https://web-production-175d5.up.railway.app`
- Repo: `offgridcreativesai-glitch/offgrid-pdf-api` (local: `~/Desktop/offgrid-pdf-api`)
- Key endpoints: `/generate-hashtags`, `/generate-report1-pdf`, `/health`
- SMTP blocked on Railway — never use smtplib. Always return base64 PDF to Make.com
- Env vars required: `ANTHROPIC_API_KEY`, `MAKE_WEBHOOK_URL`

---

## 5. Make.com Scenarios

| Scenario ID | Name | Status | Role |
|-------------|------|--------|------|
| 5018346 | OffGrid Report 1 - Social Media Brand Intelligence | ✅ Active | Main pipeline — scrape → Claude → Railway |
| 5027884 | OffGrid PDF Delivery Webhook | ✅ Active | Receives PDF from Railway → Gmail to client |
| 4727543 | Report 2 pipeline | ⛔ Deactivated | Railway 500 error pending fix |
| 4880492 | Old Report 1 pipeline | ⛔ isinvalid:true | Delete — replaced by 5018346 |

### Scenario 5018346 — Module Map (14 modules)

| Module ID | Role | Key Reference |
|-----------|------|---------------|
| 1 | Google Forms trigger | Form ID: `1iGNVUhcsgmFmiWsuRU5gO7EC4_mV4Ot7y9ujdzXRS6U` |
| 11 | Railway `/generate-hashtags` | Form field `1077123836` |
| 2 | Apify hashtag-scraper START | Uses `11.data.first_hashtag` |
| 3 | Sleep 90s | Category scraper wait |
| 4 | Apify hashtag dataset FETCH | Uses `2.data.data.id` |
| 8 | Apify post-scraper START (brand) | Form field `1471862954` |
| 9 | Sleep 45s | Brand scraper wait |
| 10 | Apify brand dataset FETCH | Uses `8.data.data.id` |
| 12 | Apify post-scraper START (competitors) | Form field `1872177727` |
| 13 | Sleep 60s | Competitor scraper wait |
| 14 | Apify competitor dataset FETCH | Uses `12.data.data.id` |
| 5 | Claude API | Uses `4.data`, `10.data`, `14.data` |
| 6 | Railway `/generate-report1-pdf` | Uses `5.data.content[1].text` (base64 encoded) |
| — | Module 7 removed | Gmail now handled by delivery scenario 5027884 |

### Scenario 5027884 — PDF Delivery Webhook

| Module | Role |
|--------|------|
| 1 | Custom webhook trigger — `https://hook.eu1.make.com/7x32y9nocrnnriif4q9dj38lursxlxln` (hook ID: 2733833) |
| 2 | Gmail send — `{{1.email}}`, attachment `{{toBinary(1.pdf_base64; "base64")}}` |

---

## 6. Google Form Field IDs

**Form ID:** `1iGNVUhcsgmFmiWsuRU5gO7EC4_mV4Ot7y9ujdzXRS6U`

| Field ID | Question |
|----------|----------|
| 928831475 | Full name |
| 814629440 | Email |
| 804063641 | Brand name |
| 1077123836 | Product category |
| 1266467907 | Website URL |
| 1144839073 | Target market |
| 88254771 | Top 3 cities |
| 58737585 | Report type |
| **Brand Audit fields** | |
| 1471862954 | Instagram handle |
| 859200824 | YouTube |
| 568327976 | LinkedIn |
| 607881655 | Biggest issue |
| 1885978502 | Competitor brand names |
| 1872177727 | Competitor Instagram handles |
| **New Product Launch fields** | |
| 330465770 | Product name |
| 534279638 | Product description |
| 1684427438 | Price point |
| 1306444110 | Competitor brand names |
| 609404377 | Competitor Instagram handles |
| 599876104 | Launch platforms |

---

## 7. Report 1 — Section Structure (Locked)

Both options share all 10 sections. Output: branded PDF only. No methodology language. No preamble.

| # | Section | Data Source |
|---|---------|-------------|
| S1 | Category Landscape Overview | Hashtag scrape (Module 4) |
| S2 | Organic to Paid Content Bridge | Hashtag scrape + competitor data |
| S3 | Competitor Success Blueprint | Competitor scrape (Module 14) |
| S4 | Brand Positioning & Content Differentiation | Brand scrape (Module 10) + category |
| S5 | Hook & Format Intelligence | Hashtag scrape + competitor |
| S6 | Audience Intelligence | Comments from all scraped data |
| S7 | Content & Launch Execution Plan | All data |
| S8 | What To Stop Immediately | Brand scrape only |
| S9 | Priority Action Plan | All data — top 5 actions with effort+impact score |
| S10 | Emerging Content Signals & Whitespace Map | Hashtag scrape |

**Global rules:** Legal disclaimer, bot filter (min 500 followers + 0.5% ER), confidence indicators

---

## 8. Report 2 — Section Structure (Locked, 18 sections)

1. Keyword Universe
2. Market Saturation
3. Market Benchmarks
4. Competitive Ad Intelligence
5. Hook Intelligence
6. Narrative Landscape
7. Creative Format Intelligence
8. Creative Volume Requirements
9. Platform Intelligence
10. Audience Intelligence
11. Offer Architecture
12. Unit Economics
13. Creative Test Matrix
14. Creative Execution Briefs (5 ready-to-shoot)
15. Landing Page Intelligence
16. Launch Recommendations
17. Budget Deployment
18. Risk Factors

---

## 9. Pricing

| Market | Early Access (first 10) | Standard | Agency Bulk (3 reports) |
|--------|------------------------|----------|------------------------|
| India | Rs.2,500 | Rs.6,999 | Rs.24,000 |
| US/UK | — | $179 | $297 |
| UAE | — | $129 | — |
| SEA | — | $99 | — |

---

## 10. Make.com & Railway — Critical Rules

- `isinvalid: true` on a scenario = unrecoverable via blueprint patch. Clone into new scenario
- Operation count = definitive diagnostic. 5018346 full success = 14 ops (updated from 11)
- `scheduling` key must NOT be inside blueprint object — separate parameter
- `jsonStringBodyContent` only accepts scalar IML interpolation — no raw objects, no `parseJSON()`
- `string()` does NOT exist in Make.com IML — use `toString()`
- `formatJSON()` does NOT exist in Make.com IML — use `base64()` + Railway decode
- Claude API response path: `5.data.content[1].text` (1-based index)
- Gmail attachment: `{{toBinary(6.data.pdf_base64; "base64")}}` — hardcoded filename `Report.pdf`
- Railway env vars must be set in Variables tab — not inherited from GitHub or local env
- Make.com max execution time: 300 seconds. Total sleep budget: 195s currently (90+45+60)

---

## 11. System Status

### ✅ Built & Working
- Report 1 pipeline end-to-end (scrape → Claude → Railway → async PDF delivery via webhook)
- Hashtag generation Railway endpoint
- Competitor scraping modules (14.data live)
- Async PDF delivery architecture (Railway → webhook → Gmail)
- Structured per-post data format sent to Claude (with followersCount)
- No-fabrication instruction in Claude system prompt
- Both scenarios active

### 🟡 Built but Broken / Incomplete
- Module 5 crashes at op 12: `string()` function not found — needs `toString()` fix (Codex)
- Zero-post brand handling: no graceful fallback yet (Codex)
- Report plain English summaries: not added to PDF renderer yet (Codex)
- Report 2 pipeline: deactivated, Railway 500 error unresolved
- Old scenario 4880492: stuck `isinvalid:true`, not yet deleted

### 🔴 Not Started
- Report 1 Option 2 (New Product Launch) pipeline
- Report 3 (Post-Ads Intelligence)
- AI social media automation system (8 agents — queued after report fixes)
- Bubble frontend
- Phase 2: Meta Graph API OAuth for demographic data (after 20–30 paying clients)
- Razorpay payment integration

---

## 12. Gaps & Bottlenecks

| Gap | Impact | Fix Owner |
|-----|--------|-----------|
| `toString()` fix in Module 5 | Pipeline crashes every run | Codex |
| Zero-post brand fallback | Broken report for brands with no posts | Codex |
| Plain English section summaries | Report unreadable for non-technical clients | Codex |
| Report 2 Railway 500 error | Second product completely blocked | Codex |
| No Bubble frontend | No client-facing product page | Codex (last) |
| No payment flow | Cannot charge clients | Codex (after frontend) |
| 3 pending agency meetings | Validation + first paying clients pending | GK |

---

## 13. Next Steps — Immediate (in order)

1. **Codex: Fix `string()` → `toString()`** in Module 5 `jsonStringBodyContent` — all 3 data blocks (CATEGORY_DATA, BRAND_DATA, COMPETITOR_DATA)
2. **Codex: Zero-post brand fallback** in `app.py` — if `BRAND_DATA` length = 0, brand sections = null with clear notice
3. **Codex: Plain English summaries** — add interpretation paragraph after each section in PDF renderer
4. **Me: Delete scenario 4880492** — cleanup
5. **Codex: Fix Report 2 Railway 500 error** — unblock second product
6. **GK: 3 pending agency meetings** — close first paying clients
7. **Post-client milestone: AI social media automation build** — 8 agents

---

## 14. Queued Future Build — AI Social Media Automation

**Concept:** Full AI-automated social media company for OffGrid Creatives running on 8 AI agents:
1. Platform strategy
2. Content planning
3. Content creation
4. Scheduling
5. Human approval (GK sign-off required)
6. Ads planning
7. SEO
8. Performance monitoring

**Platforms:** Instagram, LinkedIn, YouTube + international
**Integration:** Will feed real brand data back into report intelligence over time
**Status:** Concept captured. Build after first 20–30 paying report clients

---

## 15. Sample Reports Completed

| Brand | Category | Price Range | Status |
|-------|----------|-------------|--------|
| Select Style | Women's Indian wear (mass market) | Rs.899–1,599 | ✅ PDF done |
| Aarvie The Atelier | Premium Indo-Western + Couture | Rs.1,950–19,678 | ✅ PDF done and fixed |
