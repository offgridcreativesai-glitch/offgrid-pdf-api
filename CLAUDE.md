# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **OffGrid Creatives AI PDF API** — a Flask service deployed on Railway that generates branded PDF reports from Claude API JSON responses. It is part of an automation pipeline: Google Forms → Apify → Claude API → this Railway service → Gmail (via Make.com).

- **Production URL**: https://web-production-175d5.up.railway.app
- **GitHub repo**: offgridcreativesai-glitch/offgrid-pdf-api
- **Claude model used in pipeline**: claude-sonnet-4-20250514
- **Orchestration**: Make.com scenarios connect all pipeline stages

## Running Locally

```bash
pip install -r requirements.txt
python app.py                    # runs on port 10000 by default (or $PORT)
```

Production uses gunicorn (see `Procfile`): `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --preload`

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/generate-pdf` | POST | Report 2: 18-section Pre-Launch Ad Intelligence Report |
| `/generate-report1-pdf` | POST | Report 1: 15-section Social Media Audit |
| `/health` | GET | Health check |

All PDF endpoints accept JSON with `brand_name`, `brand_category`, `brand_market`, and either `claude_response` or `report_json`/`Report_json`. They return `{ status, filename, pdf_base64 }`.

## Architecture (single file: app.py)

The entire app lives in `app.py` (~845 lines). Key sections:

1. **Style constants & helpers** (lines 1–100): ReportLab paragraph styles (`S` dict), color palette, and reusable layout functions (`cl`, `sec_header`, `tag`, `chip_row`, `kv_table`, `hook_box`, `black_hdr`, `risk_box`).
2. **`build_pdf()`** (line 116): Builds the main 17-section report PDF using ReportLab Platypus. Sections are numbered 1–17 and map to keys in the Claude JSON response (e.g., `keyword_universe`, `market_saturation`, `creative_briefs`).
3. **`build_report1_pdf()`** (line 532): Builds Report 1 (Social Media Report) — different JSON schema, different sections.
4. **Route handlers** (lines 440, 764, 840): Extract JSON from various Claude response formats (nested `content[0].text`, raw JSON, markdown-fenced JSON), parse it, call the appropriate build function, and return base64-encoded PDF.
5. **Claude response extraction**: `extract_text_from_claude()` (defined inline in each route) handles multiple response shapes — raw string, Claude API `{content: [{text: ...}]}` wrapper, or pre-parsed dict.

## Key Patterns

- **All text must be XML-escaped** before passing to ReportLab Paragraphs — use the `cl()` helper.
- **`safe_dict()`** guards against non-dict values from JSON keys that should be objects.
- PDFs are built in a temp file, base64-encoded, then deleted — no persistent file storage.
- The JSON input often arrives with markdown code fences (` ```json ... ``` `) that are stripped via regex before parsing.

## Pipeline Architecture

```
Google Forms → Apify (scraping) → Claude API (analysis) → Make.com Module 13 (HTTP call to Railway) → Railway PDF generation → Make.com → Gmail (attachment delivery)
```

## Active Bugs

- **Railway 500 error on Module 13**: The Make.com HTTP module calling `/generate-pdf` or `/generate-report1-pdf` gets a 500 error. Claude API call succeeds upstream, but the Railway PDF generation crashes. This is the current priority fix.

## Dependencies

Only three: `flask`, `reportlab`, `gunicorn`. No database, no auth.
