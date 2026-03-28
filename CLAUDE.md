# OffGrid Creatives AI — Project Intelligence

## WHO IS WORKING ON THIS
- **GK (Gaurav Khanna)** = Founder + Strategist. Based in Surat, Gujarat.
- **Claude (claude.ai)** = Strategist, error diagnosis, skill design, instructions.
- **Claude Code** = ALL coding tasks. No exceptions.
- This division of labour is non-negotiable. Claude Code writes every line of code.

---

## WHAT THIS PROJECT IS
Pre-launch Ad Intelligence SaaS. Produces branded PDF reports from scraped Instagram/Meta data.
Positioning: The ONLY tool that tells brands what to advertise and WHY — before spending money.
Competitive window: 18–24 months. Biggest risk: Meta building this natively into Ads Manager.

---

## THREE BUSINESSES
- **Third Gen Tribe** — Graphic T-shirts, DTF print, Gen Z/Millennial market
- **Dhaga Ethnic House** — Women's ethnic wear B2C
- **OffGrid Creatives AI** — This project (primary build)

---

## FULL TECH STACK
```
Google Forms → Make.com → Apify → Claude API → Railway Flask → Gmail
```
- **Railway URL:** `https://web-production-175d5.up.railway.app`
- **GitHub Repo:** `offgridcreativesai-glitch/offgrid-pdf-api`
- **Local dev:** `~/Desktop/offgrid-pdf-api` (MacBook Air)
- **Claude model in pipeline:** `claude-sonnet-4-20250514`, max_tokens 16000
- **All accounts under:** offgridcreativesai@gmail.com

---

## PRODUCT SUITE

### Report 1 — Social Media Brand Intelligence (ACTIVE BUILD)
- **Option 1:** Brand Audit + Competitor Research
- **Option 2:** New Product Launch Intelligence
- **Make.com Scenario:** 4880492
- **Railway endpoint:** `/generate-report1-pdf`
- **Google Form ID:** `1iGNVUhcsgmFmiWsuRU5gO7EC4_mV4Ot7y9ujdzXRS6U`
- **Status:** Pipeline built. Last run status UNKNOWN — must check execution logs.

#### Report 1 — 10 Sections (JSON keys Railway expects):
1. `category_landscape`
2. `competitor_success_blueprint`
3. `brand_positioning`
4. `hook_format_intelligence`
5. `audience_intelligence`
6. `organic_to_paid_bridge`
7. `content_execution_plan`
8. `what_to_stop`
9. `priority_action_plan`
10. `emerging_signals`

#### Report 1 Make.com Pipeline — 11 Modules:
| Module | Function |
|--------|----------|
| 1 | Google Forms trigger |
| 11 | Railway `/generate-hashtags` → returns first_hashtag + hashtag_list + apify_body |
| 2 | Apify instagram-hashtag-scraper (resultsLimit 50) |
| 3 | Sleep 120 seconds |
| 4 | Fetch hashtag scraper results using run ID from Module 2 |
| 8 | Apify instagram-post-scraper (brand's own handle, resultsLimit 20) |
| 9 | Sleep 60 seconds |
| 10 | Fetch brand post results using run ID from Module 8 |
| 5 | Claude API — 10-section JSON analysis, parseResponse: true |
| 6 | Railway `/generate-report1-pdf` — `{{formatJSON(5.data)}}` |
| 7 | Gmail — sends PDF to client |

---

### Report 2 — Pre-Ads Intelligence (BROKEN — FIX LATER)
- **Make.com Scenario:** 4727543 (DEACTIVATED)
- **Railway endpoint:** `/generate-pdf`
- **Status:** Railway 500 error. Fix deployed but untested. DO NOT TOUCH until Report 1 is confirmed working.
- **18 sections:** Keyword Universe, Market Saturation, Market Benchmarks, Competitive Ad Intelligence, Hook Intelligence, Narrative Landscape, Creative Format, Creative Volume Requirements, Platform Intelligence, Audience Intelligence, Offer Architecture, Unit Economics, Creative Test Matrix, Creative Execution Briefs, Landing Page Intelligence, Launch Recommendations, Budget Deployment, Risk Factors.

### Report 3 — Post-Ads Intelligence (PLANNED — NOT BUILT)

---

## PRODUCT VERSIONS
- **V1** — Intelligence Report only (CURRENT BUILD)
- **V2** — Report + Ad Campaign Plan
- **V3** — V1 + V2 + AI Image Assets

---

## PRICING
| Market | Early Access (first 10) | Standard | Agency (3 reports) |
|--------|------------------------|----------|-------------------|
| India | Rs.2,500 | Rs.6,999 | Rs.24,000 |
| US/UK | — | $179 | $297 |
| UAE | — | $129 | — |
| SEA | — | $99 | — |

---

## APIFY ACTORS
- `apify/instagram-hashtag-scraper` — category scraping (primary)
- `apify/instagram-post-scraper` — brand's own profile scraping
- `apify/facebook-ads-scraper` — Meta Ad Library (planned, Report 2)
- **Apify Token:** `[REDACTED — stored in Make.com HTTP module URL, do not commit]`

---

## GOOGLE FORM FIELD IDs

### Shared Fields (both report types):
- `928831475` = Full name
- `814629440` = Email
- `804063641` = Brand name
- `1077123836` = Product category
- `1266467907` = Website URL
- `1144839073` = Target market
- `88254771` = Top 3 cities
- `58737585` = Report type

### Brand Audit Fields:
- `1471862954` = Instagram handle
- `859200824` = YouTube
- `568327976` = LinkedIn
- `607881655` = Biggest issue
- `1885978502` = Competitor brand names
- `1872177727` = Competitor Instagram handles

### New Product Launch Fields:
- `330465770` = Product name
- `534279638` = Product description
- `1684427438` = Price point
- `1306444110` = Competitor brand names
- `609404377` = Competitor Instagram handles
- `599876104` = Launch platforms

---

## RAILWAY ENVIRONMENT VARIABLES (Must be set in Variables tab)
- `ANTHROPIC_API_KEY` ✅ (added — was missing, caused all Module 11 failures)
- Never inherit from GitHub or local `.env` — Railway Variables tab only.

---

## CRITICAL RULES — READ BEFORE EVERY CODING SESSION

### Railway Rules:
1. SMTP port 465 is BLOCKED on Railway. Never use `smtplib`. PDF delivery = base64 via Make.com only.
2. Procfile must use `$PORT` not hardcoded port: `web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --preload`
3. All env variables must be set in Railway Variables tab explicitly.
4. Railway URL: `https://web-production-175d5.up.railway.app`

### Make.com Rules:
1. `jsonStringBodyContent` cannot accept raw object references — string interpolation only inside static JSON.
2. `{{formatJSON(5.data)}}` is the correct way to pass Claude API response to Railway.
3. `ifempty()` works reliably as fallback.
4. **Operation count in execution logs = definitive failure diagnostic.** 2 ops = fails at Module 11, 3 ops = Module 2, etc.
5. Make.com labels ALL non-2xx responses as "Bad Request" — always check operation count, not just error message.
6. Gmail attachment filename = hardcoded `Report.pdf` (dynamic filename causes BundleValidationError).
7. Gmail attachment data = `{{toBinary(MODULE_NUMBER.data.pdf_base64; "base64")}}`
8. Total scenario execution limit = 300 seconds.
9. Sleep modules: max 60 seconds each.

### Claude API in Pipeline Rules:
1. Parse response: ON in Make.com Claude module.
2. Handle both dict AND string cases for claude_response in Railway.
3. Always include JSON repair block in app.py.
4. System prompt must enforce: "Return only valid JSON. Do not use double quotes inside string values."

### Data Quality Rules:
1. Bot filter: exclude accounts under 500 followers OR under 0.5% ER.
2. Zero AI fabrication. Zero assumptions. Real scraped data only.
3. Confidence indicators on all output sections.
4. Graceful fallback messaging if brand has no Instagram posts.

### Report Design Rules:
1. No methodology language in reports.
2. No preamble.
3. Branded PDF only.
4. Legal disclaimer on every report.

---

## MAKE.COM CONNECTION IDs
- Gmail: `5716060`
- Google Forms: `5759757`
- Make.com Team ID: `1153060`
- Make.com Org ID: `6775483`

---

## CURRENT STATUS SNAPSHOT
| Component | Status |
|-----------|--------|
| Report 1 Pipeline (4880492) | Built. Last run unconfirmed. Check execution logs. |
| Report 2 Pipeline (4727543) | Deactivated. 500 error. Fix deployed, untested. |
| Keep-alive scenario (4798305) | Active |
| Railway app | Deployed. ANTHROPIC_API_KEY set. |
| Bubble frontend | NOT STARTED. Build last. |
| Sample reports | 2 complete (Select Style + Aarvie The Atelier) |

---

## PENDING WORK (IN ORDER)
1. Check Report 1 pipeline — confirm end-to-end working
2. Fix Report 2 Railway 500 error
3. 3 agency meetings pending
4. Bubble frontend (last)
5. Phase 2 (after 20–30 paying clients): Meta Graph API OAuth for demographic data

---

## SAMPLE REPORTS COMPLETED
- **Select Style** — Women's Indian wear, mass market Rs.899–1,599
- **Aarvie The Atelier** — Premium Indo-Western + Couture, Rs.1,950–19,678
- Both saved in `/mnt/user-data/outputs/`

