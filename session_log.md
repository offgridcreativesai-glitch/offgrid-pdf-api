# OffGrid Creatives AI — Session Log
> Append a new entry at the end of every session. Never edit past entries.
> Command to sync at session start: `/sync` — Claude reads this file + context.md + pulls Make.com execution status.

---

## Phase 1 — Ideation & Product Design
**Period:** Early sessions (pre-build)

- Defined core product concept: Pre-Launch Ad Intelligence Engine — answers "what should I advertise and why" BEFORE spending
- Competitive analysis completed: 30+ tools mapped (Minea, BigSpy, Foreplay, AdSpy, Motion, Triple Whale, AdRating, GetHookd, Foreplay Spyder, DeepSeek)
- No direct replicator found. DeepSeek closest free competitor. Competitive window: 18–24 months
- Biggest risk identified: Meta building natively into Ads Manager
- Product scored 9.1 vs Perplexity 5.2, ChatGPT 6.8, Gemini 7.4, Copilot 5.6, Meta AI 4.1, DeepSeek 7.8
- Product moat locked: (1) Real Apify scraped data, (2) Branded PDF quality, (3) India/SEA specificity, (4) 10-min automation, (5) Proprietary hook taxonomy
- V1/V2/V3 versioning decided: V1 = Report only, V2 = Report + Campaign Plan, V3 = Full creative production
- 4-report product suite designed: Report 1 (Social Media Brand Intelligence), Report 2 (Pre-Ads Intelligence), Report 3 (Post-Ads Intelligence)
- Tech stack finalised: Google Forms → Make.com → Apify → Claude API → Railway Flask → Gmail
- All tool accounts created under offgridcreativesai@gmail.com: Make.com, Apify, Bubble, Razorpay
- Pricing locked: India Rs.6,999 | US/UK $179 | UAE $129 | SEA $99. Early access (first 10): Rs.2,500
- Global Day 1 launch across India, US, UK, UAE, SEA simultaneously decided
- Frontend: Bubble (build last)

---

## Phase 2 — Report 2 Build (Pre-Ads Intelligence)
**Period:** Mid sessions

- 18 sections designed and locked (see context.md for full list)
- Sample report generated manually for Select Style (women's Indian wear, Rs.899–1,599)
- Sample report generated for Aarvie The Atelier (premium Indo-Western, Rs.1,950–19,678)
- Both PDFs used as proof of concept for agency validation
- Tech stack implemented: Apify `facebook-ads-scraper` → Claude API → Railway ReportLab PDF
- Make.com scenario 4727543 built and connected
- Railway 500 error encountered — root cause: control character sanitization issue in JSON response
- Python 3.11.9 fix pushed via `.python-version` file (Railway + ReportLab compatibility)
- Scenario 4727543 deactivated pending Railway fix — Report 2 status: COMPLETE BUT BLOCKED
- Decision: Pause Report 2 fix, build Report 1 first

---

## Phase 3 — Report 1 Design & Section Lock
**Period:** Mid-to-late sessions

- Report 1 split into two options: Option 1 (Brand Audit + Competitor Research), Option 2 (New Product Launch Intelligence)
- Google Form designed with branching logic (section per option)
- 10 sections locked for both options:
  - S1: Category Landscape Overview
  - S2: Organic to Paid Content Bridge (includes ad duration)
  - S3: Competitor Success Blueprint
  - S4: Brand Positioning & Content Differentiation (includes competitor matrix)
  - S5: Hook & Format Intelligence + trending audio
  - S6: Audience Intelligence
  - S7: Content & Launch Execution Plan
  - S8: What To Stop Immediately
  - S9: Priority Action Plan (top 5 actions, step-by-step, keywords+hashtags, effort+impact score)
  - S10: Emerging Content Signals & Whitespace Map
- Global report rules: legal disclaimer, bot filter (min 500 followers + 0.5% ER), confidence indicators
- Scraping strategy decided: `apify/instagram-hashtag-scraper` for category data (keyword + hashtag mode), `apify/instagram-post-scraper` for brand + competitor profiles
- Data philosophy locked: 100% real scraped data. Zero assumptions. Zero AI fabrication. Confidence indicators on all outputs
- `report1_prompt.md` created: 10-section Claude system prompt with bot filter, PII block, zero assumptions enforcement
- `build_report1_pdf()` in `app.py` rebuilt for 10 new sections

---

## Phase 4 — Skills, Claude Code Setup & Pipeline Infrastructure
**Period:** Session March 27, 2026

- Division of labour formally locked: GK + Claude = strategists. Claude Code = all coding. Non-negotiable
- Claude Code installed on MacBook Air
- Repo cloned to `~/Desktop/offgrid-pdf-api`
- `CLAUDE.md` rewritten with full pipeline documentation
- 5 new project skills built and installed via Claude Code:
  - `make-debugger` — Make.com failure diagnosis by operation count
  - `railway-ops` — Railway deployment and endpoint management
  - `report-qa` — Report content validation per section
  - `apify-strategy` — Apify actor config and data quality rules
  - `offgrid-pipeline` (updated) — Full pipeline skill with Report 1 module structure
- GitHub PAT + osxkeychain configured
- Env variables set in `.zshrc`
- `/generate-hashtags` Railway endpoint built: accepts category string, returns hashtags array via Claude API
- Make.com scenario 4880492 built for Report 1 pipeline
- ANTHROPIC_API_KEY missing from Railway Variables discovered as root cause of all Module 11 failures — added
- Scenario 4880492 stuck `isinvalid: true` permanently — could not be fixed via blueprint patches
- New scenario 5018346 cloned from 4880492 — runs clean, 11 ops, status 1
- Scenario 4880492 flagged for deletion (pending confirmation)

---

## Phase 5 — Pipeline Debug & Report Quality Audit
**Period:** Session March 27–28, 2026

- Two test runs confirmed: scenario 5018346 status 1, 11 ops, ~236s each — pipeline working end-to-end
- Hard audit of report output revealed 6 critical failures:
  1. 🔴 Competitor handles never scraped — pipeline had no competitor scraping module. Claude fabricating all competitor data
  2. 🔴 Numbers changed every run — Claude receiving flat joined text strings, not structured per-post data. No follower counts = no real ER calculation
  3. 🔴 Brand with 0 posts shows broken sections — no zero-post graceful fallback
  4. 🟡 PDF header blank — brand name + market not rendering (`answers[1]` bug)
  5. 🟡 Section 8 "What To Stop" fabricated — no brand data to base it on
  6. 🟡 Report unreadable — raw data dump with no plain English "what this means"
- New AI social media automation company concept introduced by GK — 8 AI agents (strategy, content planning, content creation, scheduling, approval, ads, SEO, performance monitoring). Queued for after report fixes

---

## Phase 6 — Pipeline Fixes Pushed
**Period:** Session March 28, 2026 (today)

### Fix 1 — Blueprint audit + data restructure (pushed directly via Make.com MCP)
- All Google Form field IDs confirmed and documented (see context.md)
- `answers[1]` → `answers[]` fixed in Module 6 — PDF header now receives brand name + market ✅
- Flat `join(map())` strings replaced with structured per-post pipe-delimited format in Module 5 ✅
- `followersCount` added to all data mappings — real ER calculation now possible ✅
- No-fabrication instruction hardcoded in Claude system prompt — `null` if data not present ✅
- Competitor section honest fallback added — `NOT YET ACTIVE` flag when no competitor data ✅

### Fix 2 — Competitor scraping modules added (pushed via Make.com MCP)
- Module 12: Apify `instagram-post-scraper` for competitor handles (form field `1872177727`) ✅
- Module 13: Sleep 60s ✅
- Module 14: Fetch competitor dataset ✅
- Module 5 Claude prompt updated — COMPETITOR_DATA now uses real `14.data` ✅
- Pipeline now: 14 modules total. Sleep timings: 90s + 45s + 60s = 195s total — under 300s cap ✅

### Fix 3 — Async architecture for timeout prevention
- New delivery scenario 5027884 created: Webhook trigger → Gmail send ✅
- Webhook hook ID 2733833 created and linked: `https://hook.eu1.make.com/7x32y9nocrnnriif4q9dj38lursxlxln` ✅
- Module 7 (Gmail) removed from main scenario — Gmail now handled by delivery scenario ✅
- Module 6 updated with `email` field from form field `814629440` ✅
- Railway commit `05dda71`: async mode activated when `MAKE_WEBHOOK_URL` env var is set ✅
- `MAKE_WEBHOOK_URL` set in Railway Variables ✅
- Both scenarios activated ✅

### First live run result
- Status 3 (error) at operation 12 — Module 5 Claude API
- Error: `Function 'string' not found` — Make.com IML does not have `string()` function
- Fix required: Replace all `string()` calls with `toString()` in Module 5 `jsonStringBodyContent`
- **Fix pending — Codex task**

---

## Pending Next Steps (in order)
1. ❌ Fix `string()` → `toString()` in Module 5 — Codex task
2. ❌ Fix zero-post brand handling — Codex task (Railway `app.py`)
3. ❌ Add plain English summaries per section — Codex task (Railway `app.py`)
4. ❌ Delete old scenario 4880492
5. ❌ Fix Report 2 Railway 500 error (scenario 4727543)
6. ❌ Build AI social media automation system (8 agents) — queued after report fixes
7. ❌ Bubble frontend build (last)
8. ❌ Phase 2 upgrade: Add Report 1 demographic data via OAuth Meta Graph API (after first 20–30 paying clients)
