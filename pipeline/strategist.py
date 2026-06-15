"""
Claude Opus analysis engine.
Sends scraped data to Claude and returns structured 11-section report JSON.
"""

import os
import re
import json
import logging

logger = logging.getLogger(__name__)


def _escape_literal_newlines(json_str):
    """Escape literal newline/tab/CR chars that appear inside JSON string values."""
    result = []
    in_string = False
    i = 0
    while i < len(json_str):
        c = json_str[i]
        if in_string:
            if c == '\\':
                result.append(c)
                i += 1
                if i < len(json_str):
                    result.append(json_str[i])
            elif c == '"':
                in_string = False
                result.append(c)
            elif c == '\n':
                result.append('\\n')
            elif c == '\r':
                result.append('\\r')
            elif c == '\t':
                result.append('\\t')
            else:
                result.append(c)
        else:
            if c == '"':
                in_string = True
            result.append(c)
        i += 1
    return ''.join(result)


def run_claude_analysis(form_data, scraped_data):
    """Send all scraped data to Claude Opus for 11-section analysis. Returns parsed dict."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

    scraped_json = json.dumps(scraped_data, indent=2, default=str)
    if len(scraped_json) > 100000:
        scraped_json = scraped_json[:100000] + "\n... [trimmed for length]"

    target_mkt = (form_data.get('target_market') or '').lower()
    tiktok_note = ("TikTok is BANNED in India. Do NOT recommend TikTok in platform expansion."
                   if target_mkt in ('india',) else
                   "TikTok is available in this market. Include it in platform expansion if relevant.")

    system_prompt = f"""You are a senior brand intelligence strategist at OffGrid Creatives AI.
You write brutally honest, data-backed brand audit reports that justify a Rs.6,999 / $179 price tag.
You think like a founder-advisor, not a generic marketing AI. Your advice must motivate the brand owner to take action.
The report is for the BRAND OWNER — a business person, not a marketer or data analyst. Write like a consultant speaking to a CEO.

ABSOLUTE RULES — BREAK ANY AND THE REPORT IS WORTHLESS:

1. DATA-FIRST: EVERY paragraph must cite specific numbers from the scraped data.
2. BAN GENERIC: NEVER write these phrases: "post consistently", "engage with your audience", "leverage trends", "increase engagement", "create quality content", "build a community".
3. CATEGORY COMPARISON IN EVERY SECTION: This brand exists in a CATEGORY. Every section must compare the brand against:
   - The user-submitted competitors (from competitor_1_instagram, competitor_2_instagram)
   - Category leaders discovered from hashtag data (from category_data, category_leader_* keys)
   - Category benchmarks/averages
   Show the brand owner WHO in their category is doing it better and HOW.
4. NO FABRICATION: Only use numbers from the scraped data. If data is missing, say: "Data not available for this metric."
5. MOTIVATE THE OWNER: End sections with a clear, specific picture of what winning looks like.
6. USE ALL DATA SOURCES: Use brand_instagram, competitor data, category_data (top_accounts, category_benchmarks), category_leader data, and brand_youtube data.
7. SPECIFICITY: Name specific @handles, specific post captions, specific hooks, specific formats.
8. EACH SECTION: 250-450 words. No section should feel thin.
9. NO TECHNICAL JARGON: Never say "X posts analyzed", "scraping", "data points", "engagement rate formula". Write in plain business language. Say "your best-performing post got X views" not "analysis of N posts reveals..."
10. WRITE FOR ACTION: Every paragraph should lead to "here's what you should do about it."

{tiktok_note}

FORMAT: Use **text** for bold, - for bullets, ## for sub-headers, line breaks between paragraphs. Keep paragraphs short (3-5 lines max).

Return a JSON object with exactly 11 sections. Each section has:
- "title" (string), "content" (string), "verdict" (string), "verdict_type" (string: "critical"/"warning"/"positive"/"info")

JSON SCHEMA:
{{
  "category_landscape": {{"title": "Where You Stand Right Now", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "competitor_success_blueprint": {{"title": "Who Is Winning In Your Space & Why", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "brand_positioning": {{"title": "Your Brand vs The Market Reality", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "hook_format_intelligence": {{"title": "What Stops The Scroll (And What Doesnt)", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "audience_intelligence": {{"title": "Who Is Actually Watching & What They Want", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "organic_to_paid_bridge": {{"title": "Content Ready To Become Paid Ads", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "content_execution_plan": {{"title": "Your Exact 30-Day Content Playbook", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "what_to_stop": {{"title": "Stop These Immediately", "content": "...", "verdict": "...", "verdict_type": "critical"}},
  "priority_action_plan": {{"title": "5 Priority Actions Ranked By Impact", "content": "...", "verdict": "...", "verdict_type": "..."}},
  "emerging_signals": {{"title": "Trends & Opportunities Before They Peak", "content": "...", "verdict": "...", "verdict_type": "info"}},
  "platform_expansion": {{"title": "New Channels You Should Be On", "content": "...", "verdict": "...", "verdict_type": "info"}}
}}

CURRENCY: Always write "Rs." for Indian Rupees, never the rupee symbol (it breaks PDF rendering). Write "Rs.500" not "₹500".

Return ONLY valid JSON. No markdown fences. No preamble. Start with {{ end with }}."""

    user_prompt = f"""BRAND: {form_data['brand_name']}
CATEGORY: {form_data['brand_category']}
DESCRIPTION: {form_data['brand_description']}
TARGET MARKET: {form_data['target_market']}
REPORT TYPE: {form_data['report_type']}

=== REAL SCRAPED DATA (use ONLY this data, do not invent numbers) ===
{scraped_json}
=== END OF DATA ===

CRITICAL INSTRUCTIONS:
- Compare brand against EVERY competitor and category leader by @handle in every section
- If category_data has top_accounts, reference them as "accounts we discovered in your category" not "hashtag scrape results"
- If brand_youtube data exists, incorporate YouTube metrics into Section 11 (Platform Expansion) with specific numbers
- Reference at least 5 different @handles throughout the report
- Minimum 250 words per section
- Write like you're advising a friend who owns this business, not writing a technical report"""

    claude_response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    response_text = claude_response.content[0].text
    logger.info(f"[STRATEGIST] Claude analysis complete: {len(response_text):,} chars")

    response_text = _escape_literal_newlines(response_text)
    response_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', response_text)
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group()
    report_data = json.loads(response_text)

    return report_data
