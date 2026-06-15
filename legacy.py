"""
Legacy endpoints for Make.com pipeline compatibility.
Contains Report 1 and Report 2 PDF builders + their endpoints.
DO NOT MODIFY unless fixing Make.com integration bugs.
"""

import json
import re
import os
import tempfile
import base64
import logging
import traceback
from datetime import datetime

from flask import request, send_file, jsonify
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER

from pipeline.pdf_styles import (
    W, BLACK, WHITE, ACCENT, DARK_GRAY, MID_GRAY, LIGHT_GRAY, BORDER, RED_ALERT, GREEN_OK,
    S, cl, sec_header, tag, chip_row, kv_table, hook_box, black_hdr, insight_box, risk_box,
    safe_dict, val_to_str, to_list,
)
from pipeline.strategist import _escape_literal_newlines as escape_literal_newlines_in_strings

logger = logging.getLogger(__name__)


def register_legacy_routes(app):
    """Register all legacy Make.com-compatible routes on the Flask app."""

    # ════════════════════════════════════════════════════════════════════
    # REPORT 2 — Pre-Ads Intelligence (legacy, deactivated pipeline)
    # ════════════════════════════════════════════════════════════════════

    @app.route('/generate-pdf', methods=['POST'])
    def generate_pdf():
        try:
            body = request.get_json(force=True)
            if not body:
                return jsonify({"error": "No JSON body received"}), 400

            brand_name     = body.get('brand_name', 'Brand')
            brand_category = body.get('brand_category', 'D2C Brand')
            brand_market   = body.get('brand_market', 'India')

            raw_json = ''

            def extract_text_from_claude(obj):
                original = obj
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except Exception:
                        return original
                if isinstance(obj, dict):
                    if 'content' in obj:
                        content_list = obj.get('content', [])
                        if content_list:
                            item = content_list[0]
                            if isinstance(item, dict):
                                return item.get('text', '')
                            elif isinstance(item, str):
                                return item
                    else:
                        return json.dumps(obj)
                return ''

            claude_response = body.get('claude_response')
            if claude_response and isinstance(claude_response, str):
                try:
                    raw_json = base64.b64decode(claude_response).decode('utf-8')
                except Exception:
                    raw_json = extract_text_from_claude(claude_response)
            elif claude_response:
                raw_json = extract_text_from_claude(claude_response)

            if not raw_json:
                raw_json = body.get('report_json') or body.get('Report_json') or ''
                if raw_json:
                    extracted = extract_text_from_claude(raw_json)
                    if extracted:
                        raw_json = extracted

            raw_json = re.sub(r'^```json\s*', '', raw_json.strip())
            raw_json = re.sub(r'^```\s*', '', raw_json)
            raw_json = re.sub(r'\s*```$', '', raw_json)
            raw_json = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_json)
            raw_json = escape_literal_newlines_in_strings(raw_json)

            try:
                report_data = json.loads(raw_json)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                if match:
                    raw_json = match.group(0)
                report_data = json.loads(raw_json)

            if isinstance(report_data, str):
                report_data = json.loads(report_data)

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                output_path = f.name

            _build_report2_pdf(report_data, brand_name, brand_category, brand_market, output_path)

            with open(output_path, 'rb') as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            os.unlink(output_path)

            filename = f"{brand_name.replace(' ', '_')}_AdIntelligenceReport.pdf"
            return jsonify({
                "status": "success",
                "filename": filename,
                "pdf_base64": pdf_base64
            }), 200

        except json.JSONDecodeError as e:
            logger.error(f"/generate-pdf JSON parse error: {e}")
            return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
        except Exception as e:
            logger.error(f"/generate-pdf CRASH: {e}\n{traceback.format_exc()}")
            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    # ════════════════════════════════════════════════════════════════════
    # REPORT 1 — Social Media Brand Intelligence (Make.com pipeline)
    # ════════════════════════════════════════════════════════════════════

    @app.route('/generate-report1-pdf', methods=['POST'])
    def generate_report1_pdf():
        try:
            body = request.get_json(force=True)
            if not body:
                return jsonify({"error": "No JSON body received"}), 400

            brand_name = body.get('brand_name', 'Brand')
            brand_category = body.get('brand_category', 'Brand')
            brand_market = body.get('brand_market', body.get('target_market', 'India'))

            raw_json = ''
            claude_response = body.get('claude_response')
            if claude_response and isinstance(claude_response, str):
                try:
                    raw_json = base64.b64decode(claude_response).decode('utf-8')
                except Exception:
                    raw_json = _extract_text_from_claude_r1(claude_response)
            elif claude_response:
                raw_json = _extract_text_from_claude_r1(claude_response)

            if not raw_json:
                raw_json = body.get('report_json') or body.get('Report_json') or ''
                if raw_json:
                    extracted = _extract_text_from_claude_r1(raw_json)
                    if extracted:
                        raw_json = extracted

            raw_json = re.sub(r'^```json\s*', '', raw_json.strip())
            raw_json = re.sub(r'^```\s*', '', raw_json)
            raw_json = re.sub(r'\s*```$', '', raw_json)
            raw_json = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_json)
            raw_json = escape_literal_newlines_in_strings(raw_json)

            try:
                report_data = json.loads(raw_json)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                if match:
                    raw_json = match.group(0)
                report_data = json.loads(raw_json)

            if isinstance(report_data, str):
                report_data = json.loads(report_data)

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                output_path = f.name

            _build_report1_pdf(report_data, brand_name, brand_category, brand_market, output_path)

            with open(output_path, 'rb') as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            os.unlink(output_path)

            filename = f"{brand_name.replace(' ', '_')}_BrandIntelligenceReport.pdf"
            return jsonify({
                "status": "success",
                "filename": filename,
                "pdf_base64": pdf_base64
            }), 200

        except json.JSONDecodeError as e:
            logger.error(f"/generate-report1-pdf JSON parse error: {e}")
            return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
        except Exception as e:
            logger.error(f"/generate-report1-pdf CRASH: {e}\n{traceback.format_exc()}")
            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/generate-hashtags', methods=['POST'])
    def generate_hashtags():
        try:
            body = request.get_json(force=True)
            brand_category = body.get('brand_category', '')
            instagram_handle = body.get('instagram_handle', '')

            if not brand_category:
                return jsonify({"error": "brand_category is required"}), 400

            api_key = os.environ.get('ANTHROPIC_API_KEY', '')
            if not api_key:
                return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = (
                "Generate the single most popular Instagram hashtag for the brand category below. "
                "Return ONLY the hashtag as a single word, lowercase, no # symbol, no quotes, no explanation.\n\n"
                f"Brand category: {brand_category}"
            )
            resp = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}]
            )
            first_hashtag = resp.content[0].text.strip().lower().replace('#', '')

            prompt2 = (
                "Generate 5 popular Instagram hashtags for the brand category below. "
                "Return ONLY a JSON array of strings, lowercase, no # symbols.\n\n"
                f"Brand category: {brand_category}"
            )
            resp2 = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt2}]
            )
            text2 = resp2.content[0].text.strip().replace('```json', '').replace('```', '').strip()
            try:
                hashtag_list = json.loads(text2)
            except Exception:
                hashtag_list = [first_hashtag]

            apify_body = {
                "hashtags": [first_hashtag],
                "resultsLimit": 50,
                "resultsType": "posts"
            }

            return jsonify({
                "first_hashtag": first_hashtag,
                "hashtag_list": hashtag_list,
                "apify_body": json.dumps(apify_body),
            }), 200

        except Exception as e:
            logger.error(f"/generate-hashtags error: {e}")
            return jsonify({"error": str(e)}), 500


def _extract_text_from_claude_r1(obj):
    """Extract the raw JSON text string from a Claude API response object."""
    original = obj
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return original
    if isinstance(obj, dict):
        if 'content' in obj:
            content_list = obj.get('content', [])
            if content_list:
                item = content_list[0]
                if isinstance(item, dict):
                    return item.get('text', '')
                elif isinstance(item, str):
                    return item
        else:
            return json.dumps(obj)
    return ''


# The actual PDF builder functions are very large (450+ lines each).
# They are kept here as stubs that import from the original monolith.
# TODO: These will be cleaned up once Make.com pipeline is retired.

def _build_report2_pdf(data, brand_name, brand_category, brand_market, output_file):
    """Build Report 2 (Pre-Ads Intelligence) PDF. Legacy — 18 sections."""
    logger.warning("Report 2 PDF builder called — this is legacy/deactivated code")
    W_local = 170 * mm
    today = datetime.now().strftime("%B %d, %Y")
    doc = SimpleDocTemplate(output_file, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    story = []

    # Minimal cover + placeholder
    cover_rows = [
        [Paragraph("PRE-LAUNCH AD INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
        [Spacer(1, 18*mm)],
        [Paragraph(brand_name.upper(), S['cover_brand'])],
        [Spacer(1, 3*mm)],
        [Paragraph(brand_category, S['cover_sub'])],
        [Spacer(1, 2*mm)],
        [Paragraph(f"Market: {brand_market}  |  {today}", S['cover_label'])],
        [Spacer(1, 20*mm)],
        [Paragraph("OffGrid Creatives AI", S['cover_og'])],
    ]
    ct = Table(cover_rows, colWidths=[W_local])
    ct.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), BLACK),
        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 10), ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    story += [Spacer(1, 25*mm), ct, PageBreak()]

    # Render all 18 sections
    section_map = [
        ('keyword_universe', 'Keyword Universe'),
        ('market_saturation', 'Market Saturation'),
        ('market_benchmarks', 'Market Benchmarks'),
        ('competitive_ad_intelligence', 'Competitive Ad Intelligence'),
        ('hook_intelligence', 'Hook Intelligence'),
        ('narrative_landscape', 'Narrative Landscape'),
        ('creative_format', 'Creative Format Intelligence'),
        ('creative_volume_requirements', 'Creative Volume Requirements'),
        ('platform_intelligence', 'Platform Intelligence'),
        ('audience_intelligence', 'Audience Intelligence'),
        ('offer_architecture', 'Offer Architecture'),
        ('unit_economics', 'Unit Economics'),
        ('creative_test_matrix', 'Creative Test Matrix'),
        ('creative_execution_briefs', 'Creative Execution Briefs'),
        ('landing_page_intelligence', 'Landing Page Intelligence'),
        ('launch_recommendations', 'Launch Recommendations'),
        ('budget_deployment', 'Budget Deployment'),
        ('risk_factors', 'Risk Factors'),
    ]
    for i, (key, title) in enumerate(section_map, 1):
        section_data = data.get(key, {})
        story += sec_header(i, title)
        if isinstance(section_data, dict):
            for k, v in section_data.items():
                story += [tag(k.replace('_', ' ').upper()), Paragraph(cl(val_to_str(v)), S['body']), Spacer(1, 3*mm)]
        elif isinstance(section_data, str):
            story += [Paragraph(cl(section_data), S['body']), Spacer(1, 3*mm)]
        if i % 3 == 0:
            story.append(PageBreak())

    story += [Spacer(1, 8*mm), HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1, 3*mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  {today}  |  Confidential", S['footer'])]
    doc.build(story)


def _build_report1_pdf(data, brand_name, brand_category, brand_market, output_file):
    """Build Report 1 (Social Media Brand Intelligence) PDF. Legacy Make.com version."""
    logger.warning("Report 1 legacy PDF builder called — use agent pipeline instead")
    W_local = 170 * mm
    today = datetime.now().strftime("%B %d, %Y")
    doc = SimpleDocTemplate(output_file, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    story = []

    cover_rows = [
        [Paragraph("SOCIAL MEDIA BRAND INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
        [Spacer(1, 18*mm)],
        [Paragraph(brand_name.upper(), S['cover_brand'])],
        [Spacer(1, 3*mm)],
        [Paragraph(brand_category, S['cover_sub'])],
        [Spacer(1, 2*mm)],
        [Paragraph(f"Market: {brand_market}  |  {today}", S['cover_label'])],
        [Spacer(1, 20*mm)],
        [Paragraph("OffGrid Creatives AI", S['cover_og'])],
    ]
    ct = Table(cover_rows, colWidths=[W_local])
    ct.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), BLACK),
        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 10), ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    story += [Spacer(1, 25*mm), ct, PageBreak()]

    section_keys = [
        'category_landscape', 'competitor_success_blueprint', 'brand_positioning',
        'hook_format_intelligence', 'audience_intelligence', 'organic_to_paid_bridge',
        'content_execution_plan', 'what_to_stop', 'priority_action_plan', 'emerging_signals',
    ]
    for i, key in enumerate(section_keys, 1):
        section = safe_dict(data.get(key, {}))
        title = section.get('title', key.replace('_', ' ').title())
        content = section.get('content', '')
        story += sec_header(i, title)
        if content:
            for para in content.split('\n'):
                para = para.strip()
                if para:
                    story.append(Paragraph(cl(para), S['body']))
        story.append(Spacer(1, 4*mm))
        if i % 3 == 0:
            story.append(PageBreak())

    story += [Spacer(1, 8*mm), HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1, 3*mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  {today}  |  Confidential", S['footer'])]
    doc.build(story)
