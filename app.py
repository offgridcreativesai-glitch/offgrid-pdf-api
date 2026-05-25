import json
import re
import os
import tempfile
import base64
import threading
import logging
import traceback
import time
import uuid
import hashlib
import hmac
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv(override=True)
from flask import Flask, request, send_file, jsonify, Response
from flask_cors import CORS
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def escape_literal_newlines_in_strings(json_str):
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

BLACK      = colors.HexColor("#0A0A0A")
WHITE      = colors.white
ACCENT     = colors.HexColor("#C8A96E")
DARK_GRAY  = colors.HexColor("#333333")
MID_GRAY   = colors.HexColor("#888888")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
BORDER     = colors.HexColor("#E0E0E0")
RED_ALERT  = colors.HexColor("#C0392B")
GREEN_OK   = colors.HexColor("#27AE60")

S = {
    'cover_brand': ParagraphStyle('CB', fontName='Helvetica-Bold', fontSize=32, textColor=WHITE, alignment=TA_CENTER, leading=38),
    'cover_sub':   ParagraphStyle('CS', fontName='Helvetica',      fontSize=13, textColor=ACCENT, alignment=TA_CENTER),
    'cover_label': ParagraphStyle('CL', fontName='Helvetica',      fontSize=9,  textColor=colors.HexColor("#AAAAAA"), alignment=TA_CENTER),
    'cover_og':    ParagraphStyle('CO', fontName='Helvetica-Bold', fontSize=11, textColor=ACCENT, alignment=TA_CENTER),
    'sec_num':     ParagraphStyle('SN', fontName='Helvetica-Bold', fontSize=9,  textColor=ACCENT, spaceAfter=1),
    'sec_title':   ParagraphStyle('ST', fontName='Helvetica-Bold', fontSize=16, textColor=BLACK,  spaceAfter=4),
    'label':       ParagraphStyle('LB', fontName='Helvetica-Bold', fontSize=8,  textColor=MID_GRAY, spaceAfter=2, spaceBefore=4),
    'body':        ParagraphStyle('BD', fontName='Helvetica',      fontSize=9,  textColor=DARK_GRAY, leading=15, spaceAfter=3),
    'bullet':      ParagraphStyle('BL', fontName='Helvetica',      fontSize=9,  textColor=DARK_GRAY, leading=15, spaceAfter=2, leftIndent=8),
    'hook':        ParagraphStyle('HK', fontName='Helvetica-Bold', fontSize=10, textColor=BLACK, leading=15),
    'metric':      ParagraphStyle('MT', fontName='Helvetica-Bold', fontSize=12, textColor=ACCENT),
    'footer':      ParagraphStyle('FT', fontName='Helvetica',      fontSize=7,  textColor=MID_GRAY, alignment=TA_CENTER),
    'brief_hdr':   ParagraphStyle('BH', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE),
    'body_bold':   ParagraphStyle('BB', fontName='Helvetica-Bold', fontSize=9,  textColor=DARK_GRAY, leading=15),
    'scene':       ParagraphStyle('SC', fontName='Helvetica',      fontSize=8.5,textColor=DARK_GRAY, leading=14, leftIndent=5),
    'alert':       ParagraphStyle('AL', fontName='Helvetica-Bold', fontSize=9,  textColor=RED_ALERT, leading=14),
}

def cl(t):
    if not isinstance(t, str): t = str(t)
    return t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def sec_header(num, title):
    return [Spacer(1,6*mm), Paragraph(f"SECTION {num:02d}", S['sec_num']),
            Paragraph(cl(title), S['sec_title']),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT), Spacer(1,4*mm)]

def tag(label):
    return Paragraph(cl(label), S['label'])

def chip_row(items, cols=3):
    W = 170*mm
    if not items: return Spacer(1,2)
    rows, row = [], []
    for i, item in enumerate(items):
        row.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
        if len(row)==cols or i==len(items)-1:
            while len(row)<cols: row.append(Spacer(1,1))
            rows.append(row); row=[]
    t = Table(rows, colWidths=[W/cols]*cols)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
        ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
    return t

def kv_table(rows_data, c1=50*mm):
    W = 170*mm
    rows = [[Paragraph(cl(str(k)), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in rows_data]
    t = Table(rows, colWidths=[c1, W-c1])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.5,BORDER),
        ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8)]))
    return t

def hook_box(text):
    W = 170*mm
    t = Table([[Paragraph(f'"{cl(text)}"', S['hook'])]], colWidths=[W])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
        ('LINEBEFORE',(0,0),(0,-1),4,ACCENT),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),12)]))
    return t

def black_hdr(text, left_color=ACCENT):
    W = 170*mm
    h = Table([[Paragraph(cl(text), S['brief_hdr'])]], colWidths=[W])
    h.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLACK),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),12),
        ('LINEBEFORE',(0,0),(0,-1),4,left_color)]))
    return h

def insight_box(text):
    if not text or not isinstance(text, str) or text.strip().lower() in ('', 'none', 'null', 'n/a'):
        return Spacer(1, 1)
    W = 170*mm
    INSIGHT_BG = colors.HexColor("#FFF8EC")
    INSIGHT_LBL = ParagraphStyle('ILB', fontName='Helvetica-Bold', fontSize=7, textColor=ACCENT, spaceAfter=3)
    INSIGHT_TXT = ParagraphStyle('ITX', fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=14)
    rows = [[Paragraph("WHAT THIS MEANS FOR YOU", INSIGHT_LBL)],
            [Paragraph(cl(text.strip()), INSIGHT_TXT)]]
    t = Table(rows, colWidths=[W])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),INSIGHT_BG),('BOX',(0,0),(-1,-1),0.5,ACCENT),
        ('LINEBEFORE',(0,0),(0,-1),3,ACCENT),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),12),
        ('RIGHTPADDING',(0,0),(-1,-1),10)]))
    return t

def risk_box(title, content, color=RED_ALERT):
    W = 170*mm
    rs = ParagraphStyle('RS', fontName='Helvetica-Bold', fontSize=9, textColor=color)
    t = Table([[Paragraph(cl(title), rs), Paragraph(cl(str(content)), S['body'])]], colWidths=[45*mm,125*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.5,BORDER),
        ('LINEBEFORE',(0,0),(0,-1),3,color),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8)]))
    return t

def safe_dict(val):
    if isinstance(val, dict):
        return val
    return {}

def val_to_str(v):
    if isinstance(v, list):
        return ', '.join(str(i) for i in v)
    return str(v) if v is not None else ''

def to_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        return [v]
    return []

def build_pdf(data, brand_name, brand_category, brand_market, output_file):
    W = 170*mm
    today = datetime.now().strftime("%B %d, %Y")
    doc = SimpleDocTemplate(output_file, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    story = []
    current_section = "COVER"

    try:
        # COVER
        cover_rows = [
            [Paragraph("PRE-LAUNCH AD INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
            [Spacer(1,18*mm)], [Paragraph(brand_name.upper(), S['cover_brand'])], [Spacer(1,3*mm)],
            [Paragraph(brand_category, S['cover_sub'])], [Spacer(1,2*mm)],
            [Paragraph(f"Market: {brand_market}  |  {today}  |  Version 3.0", S['cover_label'])],
            [Spacer(1,10*mm)], [HRFlowable(width=60*mm, thickness=0.5, color=ACCENT)], [Spacer(1,6*mm)],
            [Paragraph("17-Section Performance Intelligence + 5 Ready-to-Shoot Creative Briefs",
                ParagraphStyle('CV', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#CCCCCC"), alignment=TA_CENTER))],
            [Spacer(1,18*mm)], [Paragraph("OffGrid Creatives AI", S['cover_og'])],
            [Paragraph("offgridcreativesai@gmail.com", S['cover_label'])],
        ]
        ct = Table(cover_rows, colWidths=[W])
        ct.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLACK),('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),('LEFTPADDING',(0,0),(-1,-1),10),
            ('RIGHTPADDING',(0,0),(-1,-1),10),('ALIGN',(0,0),(-1,-1),'CENTER')]))
        story += [Spacer(1,25*mm), ct, PageBreak()]
        logger.info("build_pdf: COVER complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S1 KEYWORD UNIVERSE"
        kw = safe_dict(data.get('keyword_universe'))
        story += sec_header(1, "Keyword Universe")
        for key, label in [('search_intent_keywords','SEARCH INTENT'),('emotional_trigger_keywords','EMOTIONAL TRIGGERS'),
            ('culture_keywords','CULTURE'),('style_keywords','STYLE'),('seasonal_keywords','SEASONAL')]:
            items = to_list(kw.get(key, []))
            if items: story += [tag(label), chip_row(items, 3), Spacer(1,3*mm)]
        logger.info("build_pdf: S1 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S2 MARKET SATURATION"
        ms = safe_dict(data.get('market_saturation'))
        story += sec_header(2, "Market Saturation")
        for key, label in [('category_maturity','CATEGORY MATURITY'),('content_fatigue','CONTENT FATIGUE'),
            ('pricing_pressure','PRICING PRESSURE'),('differentiation_gaps','DIFFERENTIATION GAPS'),
            ('audience_fragmentation','AUDIENCE FRAGMENTATION')]:
            v = ms.get(key, '')
            if v: story += [tag(label), Paragraph(cl(val_to_str(v)), S['body']), Spacer(1,3*mm)]
        logger.info("build_pdf: S2 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S3 MARKET BENCHMARKS"
        mb = safe_dict(data.get('market_benchmarks'))
        story += sec_header(3, "Market Benchmarks")
        bench_rows = [("CPM RANGE", mb.get('typical_cpm_range','')),("CTR RANGE", mb.get('typical_ctr_range','')),
            ("CVR RANGE", mb.get('typical_cvr_range','')),("CAC RANGE", mb.get('typical_cac_range','')),
            ("AOV RANGE", mb.get('typical_aov_range','')),("ROAS MONTH 1-2", mb.get('average_roas_month1_2','')),
            ("ROAS MONTH 3-4", mb.get('average_roas_month3_4','')),("ROAS MONTH 5-6", mb.get('average_roas_month5_6',''))]
        story += [kv_table(bench_rows), Spacer(1,4*mm)]
        logger.info("build_pdf: S3 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S4 COMPETITIVE AD INTELLIGENCE"
        ci = safe_dict(data.get('competitive_ad_intelligence'))
        story += sec_header(4, "Competitive Ad Intelligence")
        for comp_name, comp_data in ci.items():
            if not isinstance(comp_data, dict): continue
            story.append(black_hdr(comp_name.upper()))
            rows = [("AD FORMATS", val_to_str(comp_data.get('ad_formats_running',''))),
                ("PRIMARY HOOK STYLE", val_to_str(comp_data.get('primary_hook_style',''))),
                ("OFFER STRATEGY", val_to_str(comp_data.get('offer_strategy',''))),
                ("AUDIENCE TARGETING", val_to_str(comp_data.get('audience_targeting_style',''))),
                ("FATIGUE SCORE", f"{comp_data.get('creative_fatigue_score','?')}/10"),
                ("SCALING SIGNALS", val_to_str(comp_data.get('scaling_signals',''))),
                ("STRATEGIC GAP", val_to_str(comp_data.get('strategic_gap','')))]
            story += [kv_table(rows, 42*mm), Spacer(1,4*mm)]
        logger.info("build_pdf: S4 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S5 HOOK INTELLIGENCE"
        hi = safe_dict(data.get('hook_intelligence'))
        story += sec_header(5, "Hook Intelligence")
        for key, label in [('scarcity_hooks','SCARCITY HOOKS'),('social_proof_hooks','SOCIAL PROOF HOOKS'),
            ('problem_agitation_hooks','PROBLEM AGITATION HOOKS'),('curiosity_gap_hooks','CURIOSITY GAP HOOKS'),
            ('direct_response_hooks','DIRECT RESPONSE HOOKS')]:
            hooks = to_list(hi.get(key, []))
            if hooks:
                story.append(tag(label))
                for h in hooks: story += [hook_box(str(h)), Spacer(1,2*mm)]
                story.append(Spacer(1,2*mm))
        pnv = hi.get('platform_native_variants')
        if isinstance(pnv, dict) and pnv:
            story.append(tag("TOP 3 HOOKS BY PREDICTED CTR"))
            for rk, rd in pnv.items():
                if not isinstance(rd, dict): continue
                story.append(black_hdr(f"RANK {rd.get('predicted_ctr_rank','?')} — {cl(str(rd.get('hook','')))}"))
                rt = Table([[Paragraph(cl(str(k)), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
                    [("WHY IT WINS", rd.get('reason','')),("REELS OVERLAY", rd.get('reels_overlay','')),
                     ("FEED STATIC", rd.get('feed_static','')),("CAPTION OPENING", rd.get('caption_opening',''))]],
                    colWidths=[38*mm,132*mm])
                rt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                    ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                    ('LEFTPADDING',(0,0),(-1,-1),8)]))
                story += [rt, Spacer(1,3*mm)]
        elif isinstance(pnv, list) and pnv:
            story.append(tag("TOP 3 HOOKS BY PREDICTED CTR"))
            for rd in pnv:
                if not isinstance(rd, dict): continue
                story.append(black_hdr(f"RANK {rd.get('predicted_ctr_rank','?')} — {cl(str(rd.get('hook','')))}"))
                rt = Table([[Paragraph(cl(str(k)), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
                    [("WHY IT WINS", rd.get('reason','')),("REELS OVERLAY", rd.get('reels_overlay','')),
                     ("FEED STATIC", rd.get('feed_static','')),("CAPTION OPENING", rd.get('caption_opening',''))]],
                    colWidths=[38*mm,132*mm])
                rt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                    ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                    ('LEFTPADDING',(0,0),(-1,-1),8)]))
                story += [rt, Spacer(1,3*mm)]
        logger.info("build_pdf: S5 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S6 NARRATIVE LANDSCAPE"
        nl = safe_dict(data.get('narrative_landscape'))
        story += sec_header(6, "Narrative Landscape")
        story.append(tag("COMPETITOR NARRATIVES"))
        comp_narr = nl.get('competitor_narratives', {})
        if isinstance(comp_narr, dict):
            for comp, narr in comp_narr.items():
                story.append(Paragraph(f"<b>{cl(comp.upper())}:</b> {cl(str(narr))}", S['body']))
        elif isinstance(comp_narr, list):
            for narr in comp_narr:
                story.append(Paragraph(f"• {cl(str(narr))}", S['bullet']))
        story.append(Spacer(1,3*mm))
        if nl.get('market_whitespace'): story += [tag("MARKET WHITESPACE"), Paragraph(cl(val_to_str(nl.get('market_whitespace',''))), S['body']), Spacer(1,3*mm)]
        if nl.get('brand_positioning_opportunity'): story += [tag("BRAND POSITIONING OPPORTUNITY"), Paragraph(cl(val_to_str(nl.get('brand_positioning_opportunity',''))), S['body']), Spacer(1,3*mm)]
        angles = to_list(nl.get('storytelling_angles', []))
        if angles:
            story.append(tag("PLUG-AND-PLAY NARRATIVE SCRIPTS"))
            for i, angle in enumerate(angles, 1): story += [hook_box(f"{i}. {angle}"), Spacer(1,2*mm)]
        logger.info("build_pdf: S6 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S7 CREATIVE FORMAT"
        cf = safe_dict(data.get('creative_format'))
        story += sec_header(7, "Creative Format Intelligence")
        for key, label in [('top_performing_formats','TOP PERFORMING FORMATS'),('emerging_opportunities','EMERGING OPPORTUNITIES')]:
            items = to_list(cf.get(key, []))
            if items:
                story.append(tag(label))
                for item in items: story.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
                story.append(Spacer(1,3*mm))
        if cf.get('format_recommendations'): story += [tag("FORMAT RECOMMENDATION"), Paragraph(cl(val_to_str(cf.get('format_recommendations',''))), S['body'])]
        logger.info("build_pdf: S7 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S8 CREATIVE VOLUME REQUIREMENTS"
        cv = safe_dict(data.get('creative_volume_requirements'))
        story += sec_header(8, "Creative Volume Requirements")
        wv = safe_dict(cv.get('weekly_creative_volume'))
        fm = safe_dict(cv.get('format_mix'))
        story += [kv_table([("CREATIVES PER MONTH", val_to_str(cv.get('creatives_per_month',''))),
            ("STATIC IMAGES PER WEEK", val_to_str(wv.get('static_images',''))),
            ("VIDEO CONCEPTS PER WEEK", val_to_str(wv.get('video_concepts',''))),
            ("FORMAT MIX", f"Reels {fm.get('reels_percentage','')}% / Carousel {fm.get('carousel_percentage','')}% / Static {fm.get('static_percentage','')}%"),
            ("REFRESH FREQUENCY", val_to_str(cv.get('refresh_frequency',''))),
            ("MIN VIABLE SET FOR ASC", val_to_str(cv.get('minimum_viable_creative_set',''))),
            ("PRODUCTION BUDGET", val_to_str(cv.get('creative_production_budget_estimate','')))]), Spacer(1,4*mm)]
        logger.info("build_pdf: S8 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S9 PLATFORM INTELLIGENCE"
        pi = safe_dict(data.get('platform_intelligence'))
        story += sec_header(9, "Platform Intelligence")
        for key, label in [('facebook_strategy','FACEBOOK STRATEGY'),('instagram_strategy','INSTAGRAM STRATEGY'),
            ('reels_strategy','REELS STRATEGY'),('asc_campaign_structure','ASC CAMPAIGN STRUCTURE'),
            ('budget_allocation','BUDGET ALLOCATION'),('content_calendar','CONTENT CALENDAR')]:
            v = pi.get(key, '')
            if v: story += [tag(label), Paragraph(cl(val_to_str(v)), S['body']), Spacer(1,3*mm)]
        logger.info("build_pdf: S9 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S10 AUDIENCE INTELLIGENCE"
        ai_d = safe_dict(data.get('audience_intelligence'))
        story += sec_header(10, "Audience Intelligence")
        for seg_key, seg_label in [('primary_segment','PRIMARY SEGMENT'),('secondary_segment','SECONDARY SEGMENT')]:
            seg = safe_dict(ai_d.get(seg_key))
            if seg:
                story.append(tag(seg_label))
                seg_rows = [(k.replace('_',' ').upper(), val_to_str(v)) for k,v in seg.items()]
                story += [kv_table(seg_rows), Spacer(1,4*mm)]
        geo = safe_dict(ai_d.get('geographic_nuance'))
        if geo and isinstance(geo, dict): story += [tag("GEOGRAPHIC NUANCE"), kv_table([(k.replace('_',' ').upper(), val_to_str(v)) for k,v in geo.items()]), Spacer(1,4*mm)]
        logger.info("build_pdf: S10 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S11 OFFER ARCHITECTURE"
        oa = safe_dict(data.get('offer_architecture'))
        story += sec_header(11, "Offer Architecture")
        if oa.get('recommended_price_point'): story += [tag("RECOMMENDED PRICE POINT"), Paragraph(cl(val_to_str(oa.get('recommended_price_point',''))), S['body']), Spacer(1,3*mm)]
        if oa.get('first_order_hook'): story += [tag("FIRST ORDER HOOK"), hook_box(val_to_str(oa.get('first_order_hook',''))), Spacer(1,3*mm)]
        bundles = oa.get('bundle_strategy', {})
        if bundles:
            story.append(tag("BUNDLE STRATEGY"))
            if isinstance(bundles, dict):
                for k, v in bundles.items(): story.append(Paragraph(f"• <b>{cl(k.upper())}:</b> {cl(str(v))}", S['bullet']))
            elif isinstance(bundles, list):
                for item in bundles: story.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        if oa.get('price_justification'): story += [tag("PRICE JUSTIFICATION"), Paragraph(cl(val_to_str(oa.get('price_justification',''))), S['body']), Spacer(1,3*mm)]
        if oa.get('discount_guardrails'): story += [tag("DISCOUNT GUARDRAILS"), Paragraph(cl(val_to_str(oa.get('discount_guardrails',''))), S['alert']), Spacer(1,3*mm)]
        logger.info("build_pdf: S11 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S12 UNIT ECONOMICS"
        ue = safe_dict(data.get('unit_economics'))
        story += sec_header(12, "Unit Economics")
        mt = Table([[[Paragraph("TARGET CAC", S['label']), Paragraph(cl(str(ue.get('target_cac',''))), S['metric'])],
            [Paragraph("BREAK-EVEN ROAS", S['label']), Paragraph(cl(str(ue.get('break_even_roas',''))), S['metric'])],
            [Paragraph("RECOMMENDED AOV", S['label']), Paragraph(cl(str(ue.get('recommended_aov',''))), S['metric'])]]], colWidths=[W/3]*3)
        mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLACK),('BOX',(0,0),(-1,-1),1,ACCENT),
            ('INNERGRID',(0,0),(-1,-1),0.5,ACCENT),('TOPPADDING',(0,0),(-1,-1),10),
            ('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),10)]))
        story += [mt, Spacer(1,4*mm)]
        roas = safe_dict(ue.get('realistic_roas_timeline'))
        if roas:
            story.append(tag("REALISTIC ROAS TIMELINE"))
            for k, label in [('month_1_2_expectation','MONTH 1-2'),('month_3_4_expectation','MONTH 3-4'),('month_5_6_expectation','MONTH 5-6')]:
                v = roas.get(k, '')
                if v: story.append(Paragraph(f"<b>{label}:</b> {cl(val_to_str(v))}", S['body']))
            story.append(Spacer(1,3*mm))
        india = safe_dict(ue.get('india_specific_factors'))
        if india and isinstance(india, dict): story += [tag("INDIA-SPECIFIC FACTORS"), kv_table([(k.replace('_',' ').upper(), val_to_str(v)) for k,v in india.items()]), Spacer(1,4*mm)]
        logger.info("build_pdf: S12 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S13 CREATIVE TEST MATRIX"
        ctm = safe_dict(data.get('creative_test_matrix'))
        story += sec_header(13, "Creative Test Matrix")
        story += [kv_table([("TESTING BUDGET", val_to_str(ctm.get('testing_budget_percentage',''))),
            ("VALIDATION TIMELINE", val_to_str(ctm.get('validation_timeline',''))),
            ("WEEKLY VOLUME DURING TEST", val_to_str(ctm.get('weekly_creative_volume_during_test','')))]), Spacer(1,4*mm)]
        for hyp_key in ['test_hypothesis_1','test_hypothesis_2','test_hypothesis_3']:
            hyp = safe_dict(ctm.get(hyp_key))
            if not isinstance(hyp, dict): continue
            story.append(black_hdr(f"HYPOTHESIS {hyp_key.split('_')[-1]} — {cl(val_to_str(hyp.get('hook_angle','')))}"))
            ht = Table([[Paragraph(cl(str(k)), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
                [("FORMAT", hyp.get('ad_format','')),("AUDIENCE", hyp.get('target_audience','')),
                 ("BUDGET", hyp.get('budget_allocation_percentage','')),
                 ("SUCCESS METRIC", hyp.get('success_metric','')),("KILL CRITERIA", hyp.get('kill_criteria',''))]],
                colWidths=[40*mm, 130*mm])
            ht.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LEFTPADDING',(0,0),(-1,-1),8)]))
            story += [ht, Spacer(1,3*mm)]
        logger.info("build_pdf: S13 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S14 CREATIVE EXECUTION BRIEFS"
        ceb = data.get('creative_execution_briefs', {})
        story += sec_header(14, "Creative Execution Briefs")
        story += [Paragraph("5 complete ready-to-shoot briefs. Execute on day one. No questions needed.", S['body']), Spacer(1,4*mm)]
        # Handle both dict and list formats from Claude
        briefs_list = []
        if isinstance(ceb, dict):
            briefs_list = [v for v in ceb.values() if isinstance(v, dict)]
        elif isinstance(ceb, list):
            briefs_list = [v for v in ceb if isinstance(v, dict)]
        for brief in briefs_list:
            story.append(black_hdr(f"BRIEF {brief.get('brief_number','?')} — {cl(val_to_str(brief.get('brief_name','')))}"))
            top_t = Table([[Paragraph(cl(str(k)), S['label']), Paragraph(cl(val_to_str(v)), S['body'])] for k,v in
                [("OBJECTIVE", brief.get('objective','')),("FORMAT", brief.get('format','')),
                 ("AUDIO DIRECTION", brief.get('audio_direction','')),("THUMBNAIL", brief.get('thumbnail_description','')),
                 ("CTA & OFFER", brief.get('cta_and_offer','')),("PRODUCTION REQUIREMENTS", brief.get('production_requirements','')),
                 ("PRODUCTION COST", brief.get('production_cost_estimate',''))]],
                colWidths=[42*mm, 128*mm])
            top_t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LEFTPADDING',(0,0),(-1,-1),8)]))
            story.append(top_t)
            scene = brief.get('scene_breakdown', '')
            if scene:
                scene = val_to_str(scene)
                sh = Table([[Paragraph("SCENE BREAKDOWN", S['label'])]], colWidths=[W])
                sh.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#1A1A1A")),
                    ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),8)]))
                st = Table([[Paragraph(cl(scene), S['scene'])]], colWidths=[W])
                st.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#F0F0F0")),
                    ('BOX',(0,0),(-1,-1),0.3,BORDER),('TOPPADDING',(0,0),(-1,-1),8),
                    ('BOTTOMPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),10)]))
                story += [sh, st]
            ost = brief.get('on_screen_text', '')
            if ost:
                ost = val_to_str(ost)
                oh = Table([[Paragraph("ON-SCREEN TEXT — IN ORDER", S['label'])]], colWidths=[W])
                oh.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#1A1A1A")),
                    ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),8)]))
                ot = Table([[Paragraph(cl(ost), S['body_bold'])]], colWidths=[W])
                ot.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.5,ACCENT),
                    ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),10)]))
                story += [oh, ot]
            story.append(Spacer(1,6*mm))
        logger.info("build_pdf: S14 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S15 LANDING PAGE INTELLIGENCE"
        lp = safe_dict(data.get('landing_page_intelligence'))
        story += sec_header(15, "Landing Page Intelligence")
        for key, label in [('hero_section_strategy','HERO SECTION STRATEGY'),('offer_placement','OFFER PLACEMENT'),
            ('mobile_optimization_factors','MOBILE OPTIMIZATION — INDIA')]:
            v = lp.get(key, '')
            if v: story += [tag(label), Paragraph(cl(val_to_str(v)), S['body']), Spacer(1,3*mm)]
        trust = to_list(lp.get('trust_signals_required', []))
        if trust:
            story.append(tag("REQUIRED TRUST SIGNALS"))
            for t_item in trust: story.append(Paragraph(f"• {cl(str(t_item))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        killers = to_list(lp.get('conversion_killers', []))
        if killers:
            story.append(tag("CONVERSION KILLERS"))
            for killer in killers: story += [risk_box("KILL", str(killer)), Spacer(1,2*mm)]
        if lp.get('recommended_page_structure'): story += [tag("RECOMMENDED PAGE STRUCTURE"), Paragraph(cl(val_to_str(lp.get('recommended_page_structure',''))), S['body'])]
        logger.info("build_pdf: S15 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S16 LAUNCH RECOMMENDATIONS"
        lr = safe_dict(data.get('launch_recommendations'))
        story += sec_header(16, "Launch Recommendations")
        for phase_key, phase_label, phase_color in [
            ('phase_1','PHASE 1 — DAYS 1-30', GREEN_OK),
            ('phase_2','PHASE 2 — DAYS 31-60', ACCENT),
            ('phase_3','PHASE 3 — DAYS 61-90+', colors.HexColor("#2980B9"))]:
            phase = safe_dict(lr.get(phase_key))
            if not isinstance(phase, dict): continue
            story.append(black_hdr(phase_label, phase_color))
            pt = Table([[Paragraph(cl(str(k)), S['label']), Paragraph(cl(val_to_str(v)), S['body'])] for k,v in
                [("BUDGET", phase.get('budget','')),("SUCCESS METRICS", phase.get('success_metrics',''))]],
                colWidths=[35*mm, 135*mm])
            pt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LEFTPADDING',(0,0),(-1,-1),8)]))
            story.append(pt)
            for action in to_list(phase.get('actions', [])): story.append(Paragraph(f"• {cl(str(action))}", S['bullet']))
            story.append(Spacer(1,4*mm))
        logger.info("build_pdf: S16 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S17 BUDGET DEPLOYMENT"
        bd = safe_dict(data.get('budget_deployment'))
        story += sec_header(17, "Budget Deployment")
        if bd.get('total_monthly_budget'): story += [tag("TOTAL MONTHLY BUDGET"), Paragraph(cl(val_to_str(bd.get('total_monthly_budget',''))), S['metric']), Spacer(1,3*mm)]
        for key, label in [('asc_campaign_structure','ASC CAMPAIGN STRUCTURE'),('creative_refresh_cadence','CREATIVE REFRESH CADENCE'),
            ('scaling_triggers','SCALING TRIGGERS'),('scalability_ceiling','SCALABILITY CEILING')]:
            v = bd.get(key, '')
            if v: story += [tag(label), Paragraph(cl(val_to_str(v)), S['body']), Spacer(1,3*mm)]
        expected = safe_dict(bd.get('expected_metrics'))
        if isinstance(expected, dict) and expected:
            story += [tag("EXPECTED METRICS BY MONTH"), kv_table([(k.replace('_',' ').upper(), val_to_str(v)) for k,v in expected.items()]), Spacer(1,4*mm)]
        logger.info("build_pdf: S17 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "S18 RISK FACTORS"
        rf = safe_dict(data.get('risk_factors'))
        story += sec_header(18, "Risk Factors")
        for key, label, color in [
            ('competitive_response_risk','COMPETITIVE RESPONSE RISK', MID_GRAY),
            ('creative_fatigue_timeline','CREATIVE FATIGUE TIMELINE', ACCENT),
            ('pricing_war_risk','PRICING WAR RISK', MID_GRAY),
            ('cod_rto_risk','COD / RTO RISK', RED_ALERT),
            ('platform_policy_risk','PLATFORM POLICY RISK', ACCENT),
            ('design_piracy_risk','DESIGN PIRACY RISK', RED_ALERT)]:
            v = rf.get(key, '')
            if v: story += [risk_box(label, val_to_str(v), color), Spacer(1,2*mm)]
        logger.info("build_pdf: S18 complete")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # FOOTER
    try:
        current_section = "FOOTER"
        story += [Spacer(1,8*mm), HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1,3*mm),
            Paragraph(f"Prepared by OffGrid Creatives AI  |  offgridcreativesai@gmail.com  |  {today}  |  Confidential  |  Version 3.0", S['footer'])]
        logger.info("build_pdf: FOOTER complete, building doc...")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    try:
        current_section = "DOC BUILD"
        doc.build(story)
        logger.info("build_pdf: doc.build() SUCCESS")
    except Exception as e:
        logger.error(f"build_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise


GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "offgridcreativesai@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


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
            """Safely extract report text from Claude API response in any form."""
            original = obj
            if isinstance(obj, str):
                try:
                    obj = json.loads(obj)
                except Exception:
                    return original  # Already plain text/JSON string
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
                    # Dict without content key = already the report JSON
                    return json.dumps(obj)
            return ''

        # Try claude_response key first (Make.com sends base64-encoded text)
        claude_response = body.get('claude_response')
        if claude_response and isinstance(claude_response, str):
            try:
                raw_json = base64.b64decode(claude_response).decode('utf-8')
            except Exception:
                raw_json = extract_text_from_claude(claude_response)
        elif claude_response:
            raw_json = extract_text_from_claude(claude_response)

        # Fall back to Report_json / report_json
        if not raw_json:
            raw_json = body.get('report_json') or body.get('Report_json') or ''
            if raw_json:
                extracted = extract_text_from_claude(raw_json)
                if extracted:
                    raw_json = extracted

        raw_json = re.sub(r'^```json\s*', '', raw_json.strip())
        raw_json = re.sub(r'^```\s*', '', raw_json)
        raw_json = re.sub(r'\s*```$', '', raw_json)

        # Sanitize control characters that break JSON parsing
        raw_json = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_json)
        raw_json = escape_literal_newlines_in_strings(raw_json)

        # Attempt JSON repair for common LLM output issues
        try:
            report_data = json.loads(raw_json)
        except json.JSONDecodeError:
            import re as _re2
            match = _re2.search(r'\{.*\}', raw_json, _re2.DOTALL)
            if match:
                raw_json = match.group(0)
            report_data = json.loads(raw_json)

        # Handle double-encoded JSON (json.loads returns string instead of dict)
        if isinstance(report_data, str):
            report_data = json.loads(report_data)

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            output_path = f.name

        build_pdf(report_data, brand_name, brand_category, brand_market, output_path)

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


def build_report1_pdf(data, brand_name, brand_category, brand_market, output_file):
    logger.info("build_report1_pdf() STARTED")
    current_section = "INIT"
    W = 170*mm
    today = datetime.now().strftime("%B %d, %Y")
    doc = SimpleDocTemplate(output_file, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    story = []

    AI_EST = ParagraphStyle('AIE', fontName='Helvetica-Bold', fontSize=7,
        textColor=colors.HexColor("#E67E22"), spaceAfter=2, spaceBefore=2)
    CONF_STYLE = ParagraphStyle('CONF', fontName='Helvetica', fontSize=7,
        textColor=GREEN_OK, spaceAfter=2, spaceBefore=2)

    def ai_estimate_note(text="AI ESTIMATE — based on public data analysis, not verified metrics"):
        return Paragraph(text, AI_EST)

    def conf_note(n):
        if n:
            return Paragraph(f"Confidence: Based on {n} posts analysed from live Instagram data", CONF_STYLE)
        return Spacer(1, 1)

    LEGAL = ("Legal notice: This report is based exclusively on publicly available Instagram data. "
             "Save rates, reach, impressions, and conversion rates marked * are AI estimates — "
             "Instagram does not expose these metrics publicly. No personally identifiable information "
             "has been collected or stored. For internal strategic use only.")

    # Pull posts count once for confidence notes
    landscape    = safe_dict(data.get('category_landscape'))
    posts_analysed   = landscape.get('total_posts_analysed', '')
    accounts_analysed = landscape.get('total_accounts_analysed', '')

    # Plain-English summaries from Claude (may be absent in older responses)
    summaries = safe_dict(data.get('summaries'))

    # ── COVER ──────────────────────────────────────────────────────────────────
    current_section = "COVER"
    try:
        conf_text = f"Based on {posts_analysed} posts from {accounts_analysed} accounts" if posts_analysed else "Live Instagram data"
        cover_rows = [
            [Paragraph("SOCIAL MEDIA BRAND INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
            [Spacer(1,14*mm)],
            [Paragraph(cl(brand_name.upper()), S['cover_brand'])],
            [Spacer(1,3*mm)],
            [Paragraph(cl(brand_category), S['cover_sub'])],
            [Spacer(1,2*mm)],
            [Paragraph(f"Market: {brand_market}  |  {today}  |  Version 2.0", S['cover_label'])],
            [Spacer(1,5*mm)],
            [Paragraph(cl(conf_text), ParagraphStyle('CONF2', fontName='Helvetica', fontSize=8, textColor=GREEN_OK, alignment=TA_CENTER))],
            [Spacer(1,4*mm)],
            [HRFlowable(width=60*mm, thickness=0.5, color=ACCENT)],
            [Spacer(1,5*mm)],
            [Paragraph("10-Section Data-Driven Social Media Intelligence Report",
                ParagraphStyle('CV', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#CCCCCC"), alignment=TA_CENTER))],
            [Spacer(1,10*mm)],
            [Paragraph("OffGrid Creatives AI", S['cover_og'])],
            [Paragraph("offgridcreativesai@gmail.com", S['cover_label'])],
            [Spacer(1,6*mm)],
            [Paragraph(LEGAL, ParagraphStyle('DL', fontName='Helvetica', fontSize=6.5,
                textColor=colors.HexColor("#888888"), alignment=TA_CENTER, leading=9))],
        ]
        ct = Table(cover_rows, colWidths=[W])
        ct.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLACK),('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),('LEFTPADDING',(0,0),(-1,-1),10),
            ('RIGHTPADDING',(0,0),(-1,-1),10),('ALIGN',(0,0),(-1,-1),'CENTER')]))
        story += [Spacer(1,25*mm), ct, PageBreak()]
        logger.info("build_report1_pdf: COVER OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S1 CATEGORY LANDSCAPE ──────────────────────────────────────────────────
    try:
        current_section = "S1 Category Landscape"
        story += sec_header(1, "Category Landscape")
        story += [insight_box(summaries.get('category_landscape','')), Spacer(1,3*mm)]
        story += [conf_note(posts_analysed), Spacer(1,2*mm)]
        kv_rows = []
        if posts_analysed:   kv_rows.append(("POSTS ANALYSED",               str(posts_analysed)))
        if accounts_analysed: kv_rows.append(("ACCOUNTS ANALYSED",            str(accounts_analysed)))
        for key, label in [
            ('avg_engagement_rate_category','AVG ENGAGEMENT RATE'),
            ('top_engagement_rate_seen',    'HIGHEST ENGAGEMENT SEEN'),
            ('lowest_engagement_rate_seen', 'LOWEST ENGAGEMENT (after bot filter)'),
            ('dominant_content_format',     'DOMINANT FORMAT'),
            ('avg_posting_frequency',       'AVG POSTING FREQUENCY'),
        ]:
            v = landscape.get(key,'')
            if v: kv_rows.append((label, val_to_str(v)))
        if kv_rows: story += [kv_table(kv_rows), Spacer(1,4*mm)]
        days  = to_list(landscape.get('most_active_posting_days',[]))
        hours = to_list(landscape.get('most_active_posting_hours',[]))
        tags5 = to_list(landscape.get('top_5_hashtags_by_frequency',[]))
        if days:  story += [tag("MOST ACTIVE POSTING DAYS"),  chip_row(days, 4),  Spacer(1,3*mm)]
        if hours: story += [tag("MOST ACTIVE POSTING HOURS"), chip_row(hours, 3), Spacer(1,3*mm)]
        if tags5: story += [tag("TOP 5 HASHTAGS BY FREQUENCY"), chip_row(tags5, 3), Spacer(1,3*mm)]
        dq = landscape.get('data_quality_note','')
        if dq: story += [tag("DATA QUALITY NOTE"), Paragraph(cl(val_to_str(dq)), S['body']), Spacer(1,3*mm)]
        logger.info("build_report1_pdf: S1 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S2 COMPETITOR SUCCESS BLUEPRINT ────────────────────────────────────────
    try:
        current_section = "S2 Competitor Success Blueprint"
        csb = safe_dict(data.get('competitor_success_blueprint'))
        story += sec_header(2, "Competitor Success Blueprint")
        story += [insight_box(summaries.get('competitor_success_blueprint','')), Spacer(1,3*mm)]
        story += [conf_note(posts_analysed), Spacer(1,2*mm)]
        for perf in to_list(csb.get('top_performers',[])):
            if not isinstance(perf, dict): continue
            handle = val_to_str(perf.get('handle',''))
            story.append(black_hdr(f"@{handle}" if handle else "TOP PERFORMER"))
            p_rows = []
            for key, label in [
                ('follower_count',      'FOLLOWERS'),
                ('avg_engagement_rate', 'AVG ENGAGEMENT RATE'),
                ('posts_analysed',      'POSTS ANALYSED'),
                ('dominant_format',     'DOMINANT FORMAT'),
                ('avg_posts_per_week',  'AVG POSTS PER WEEK'),
                ('hashtag_strategy',    'HASHTAG STRATEGY'),
            ]:
                v = perf.get(key,'')
                if v: p_rows.append((label, val_to_str(v)))
            if p_rows: story += [kv_table(p_rows, 45*mm), Spacer(1,2*mm)]
            if perf.get('hook_pattern'):
                story += [tag("HOOK PATTERN"), Paragraph(cl(val_to_str(perf.get('hook_pattern',''))), S['body']), Spacer(1,2*mm)]
            if perf.get('top_performing_caption_example'):
                story += [tag("TOP CAPTION EXAMPLE"), hook_box(val_to_str(perf.get('top_performing_caption_example',''))), Spacer(1,2*mm)]
            if perf.get('what_makes_them_win'):
                story += [tag("WHY THEY WIN"), Paragraph(cl(val_to_str(perf.get('what_makes_them_win',''))), S['body']), Spacer(1,3*mm)]
        patterns = to_list(csb.get('common_patterns_across_top_performers',[]))
        if patterns:
            story.append(tag("COMMON PATTERNS ACROSS TOP PERFORMERS"))
            for p in patterns: story.append(Paragraph(f"• {cl(str(p))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        low_patterns = to_list(csb.get('what_low_performers_have_in_common',[]))
        if low_patterns:
            story.append(tag("WHAT LOW PERFORMERS HAVE IN COMMON"))
            for p in low_patterns: story.append(Paragraph(f"• {cl(str(p))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        logger.info("build_report1_pdf: S2 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S3 BRAND POSITIONING ───────────────────────────────────────────────────
    try:
        current_section = "S3 Brand Positioning"
        bp = safe_dict(data.get('brand_positioning'))
        story += sec_header(3, "Brand Positioning")

        # Detect zero / very few brand posts: own engagement rate missing, zero, or N/A
        own_rate = val_to_str(bp.get('own_avg_engagement_rate', ''))
        no_brand_posts = not own_rate or own_rate.strip().lower() in ('', '0', '0%', 'n/a', 'na', 'none', 'null', '-', '\u2013', '\u2014')

        if no_brand_posts:
            story += [
                Paragraph(
                    "No recent posts found on your profile. Post regularly for 2\u20133 weeks "
                    "then rerun this report for your brand positioning analysis. "
                    "Category benchmarks for reference:",
                    S['body']
                ),
                Spacer(1, 4*mm)
            ]
            cat_rows = []
            for key, label in [
                ('category_avg_engagement_rate', 'CATEGORY AVG ENGAGEMENT'),
                ('category_dominant_format',     'CATEGORY DOMINANT FORMAT'),
                ('category_posting_frequency',   'CATEGORY POSTING FREQUENCY'),
            ]:
                v = bp.get(key, '')
                if v: cat_rows.append((label, val_to_str(v)))
            if cat_rows:
                story += [kv_table(cat_rows), Spacer(1, 4*mm)]
        else:
            pos_rows = []
            for key, label in [
                ('own_avg_engagement_rate',      'OWN ENGAGEMENT RATE'),
                ('category_avg_engagement_rate', 'CATEGORY AVG ENGAGEMENT'),
                ('engagement_gap',               'ENGAGEMENT GAP'),
                ('own_dominant_format',          'OWN DOMINANT FORMAT'),
                ('category_dominant_format',     'CATEGORY DOMINANT FORMAT'),
                ('format_alignment',             'FORMAT ALIGNMENT'),
                ('own_posting_frequency',        'OWN POSTING FREQUENCY'),
                ('category_posting_frequency',   'CATEGORY POSTING FREQUENCY'),
                ('frequency_gap',                'FREQUENCY GAP'),
            ]:
                v = bp.get(key, '')
                if v: pos_rows.append((label, val_to_str(v)))
            if pos_rows: story += [kv_table(pos_rows), Spacer(1, 4*mm)]
            if bp.get('content_overlap_with_category'):
                story += [tag("CONTENT OVERLAP WITH CATEGORY"), Paragraph(cl(val_to_str(bp.get('content_overlap_with_category', ''))), S['body']), Spacer(1, 3*mm)]
            if bp.get('whitespace_opportunity'):
                story += [tag("WHITESPACE OPPORTUNITY"), Paragraph(cl(val_to_str(bp.get('whitespace_opportunity', ''))), S['body']), Spacer(1, 3*mm)]
            if bp.get('one_line_brand_verdict'):
                story += [tag("VERDICT"), hook_box(val_to_str(bp.get('one_line_brand_verdict', ''))), Spacer(1, 3*mm)]

        logger.info("build_report1_pdf: S3 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S4 HOOK & FORMAT INTELLIGENCE ─────────────────────────────────────────
    try:
        current_section = "S4 Hook & Format Intelligence"
        hfi = safe_dict(data.get('hook_format_intelligence'))
        story += sec_header(4, "Hook & Format Intelligence")
        story += [insight_box(summaries.get('hook_format_intelligence','')), Spacer(1,3*mm)]
        story += [conf_note(posts_analysed), Spacer(1,2*mm)]
        for h in to_list(hfi.get('top_3_hooks_by_engagement',[])):
            if not isinstance(h, dict): continue
            story += [tag("HOOK"), hook_box(val_to_str(h.get('hook_text','')))]
            h_rows = []
            if h.get('hook_type'):                                    h_rows.append(("TYPE",              val_to_str(h.get('hook_type',''))))
            if h.get('avg_engagement_on_posts_using_this_pattern'):   h_rows.append(("AVG ENGAGEMENT",    val_to_str(h.get('avg_engagement_on_posts_using_this_pattern',''))))
            if h.get('post_count_with_this_pattern'):                 h_rows.append(("POSTS WITH PATTERN",str(h.get('post_count_with_this_pattern',''))))
            if h_rows: story.append(kv_table(h_rows, 55*mm))
            story.append(Spacer(1,3*mm))
        fmt_rows = []
        for key, label in [
            ('best_performing_format',  'BEST FORMAT'),
            ('worst_performing_format', 'WORST FORMAT'),
            ('optimal_caption_length',  'OPTIMAL CAPTION LENGTH'),
            ('emoji_usage_pattern',     'EMOJI USAGE PATTERN'),
        ]:
            v = hfi.get(key,'')
            if v: fmt_rows.append((label, val_to_str(v)))
        if fmt_rows: story += [kv_table(fmt_rows), Spacer(1,3*mm)]
        ctas = to_list(hfi.get('cta_patterns_in_top_posts',[]))
        if ctas:
            story.append(tag("CTA PATTERNS IN TOP POSTS"))
            for cta in ctas: story.append(Paragraph(f"• {cl(str(cta))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        if hfi.get('own_profile_hook_assessment'):
            story += [tag("YOUR HOOK ASSESSMENT"), Paragraph(cl(val_to_str(hfi.get('own_profile_hook_assessment',''))), S['body']), Spacer(1,3*mm)]
        logger.info("build_report1_pdf: S4 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S5 AUDIENCE INTELLIGENCE ───────────────────────────────────────────────
    try:
        current_section = "S5 Audience Intelligence"
        ai_d = safe_dict(data.get('audience_intelligence'))
        story += sec_header(5, "Audience Intelligence")
        story += [insight_box(summaries.get('audience_intelligence','')), Spacer(1,3*mm)]
        story += [conf_note(posts_analysed), Spacer(1,2*mm)]
        if ai_d.get('comment_sentiment_summary'):
            story += [tag("COMMENT SENTIMENT SUMMARY"), Paragraph(cl(val_to_str(ai_d.get('comment_sentiment_summary',''))), S['body']), Spacer(1,3*mm)]
        for key, label in [
            ('top_positive_triggers',              'POSITIVE TRIGGERS'),
            ('top_negative_triggers',              'NEGATIVE TRIGGERS'),
            ('questions_audience_asks_repeatedly', 'QUESTIONS AUDIENCE ASKS'),
            ('purchase_intent_signals',            'PURCHASE INTENT SIGNALS'),
            ('content_topics_that_drive_comments', 'TOPICS THAT DRIVE COMMENTS'),
        ]:
            items = to_list(ai_d.get(key,[]))
            if items:
                story.append(tag(label))
                for item in items: story.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
                story.append(Spacer(1,3*mm))
        if ai_d.get('content_topics_that_drive_saves_estimate'):
            story.append(ai_estimate_note("* Save data is an AI estimate — Instagram does not expose save counts publicly"))
            story += [tag("TOPICS THAT DRIVE SAVES *"), Paragraph(cl(val_to_str(ai_d.get('content_topics_that_drive_saves_estimate',''))), S['body']), Spacer(1,3*mm)]
        if ai_d.get('best_time_to_post_for_comments'):
            story += [tag("BEST TIME TO POST"), Paragraph(cl(val_to_str(ai_d.get('best_time_to_post_for_comments',''))), S['body']), Spacer(1,3*mm)]
        logger.info("build_report1_pdf: S5 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S6 ORGANIC TO PAID BRIDGE ─────────────────────────────────────────────
    try:
        current_section = "S6 Organic to Paid Bridge"
        otpb = safe_dict(data.get('organic_to_paid_bridge'))
        story += sec_header(6, "Organic to Paid Bridge")
        story += [insight_box(summaries.get('organic_to_paid_bridge','')), Spacer(1,3*mm)]
        story += [Paragraph("Content structures with paid ad potential — based on format and engagement patterns from organic data only.", S['body']), Spacer(1,3*mm)]
        for fmt in to_list(otpb.get('organic_formats_with_paid_potential',[])):
            if not isinstance(fmt, dict): continue
            fmt_name = val_to_str(fmt.get('format',''))
            story.append(black_hdr(fmt_name.upper() if fmt_name else "FORMAT"))
            f_rows = []
            if fmt.get('reason'):               f_rows.append(("WHY IT WORKS",    val_to_str(fmt.get('reason',''))))
            if fmt.get('example_hook_structure'):f_rows.append(("HOOK STRUCTURE", val_to_str(fmt.get('example_hook_structure',''))))
            if f_rows: story += [kv_table(f_rows, 42*mm), Spacer(1,3*mm)]
        scroll = to_list(otpb.get('hook_styles_that_stop_scroll',[]))
        if scroll:
            story.append(tag("HOOK STYLES THAT STOP SCROLL"))
            for hs in scroll: story.append(Paragraph(f"• {cl(str(hs))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        if otpb.get('caption_structures_with_high_comment_rate'):
            story += [tag("CAPTION STRUCTURES WITH HIGH COMMENT RATE"), Paragraph(cl(val_to_str(otpb.get('caption_structures_with_high_comment_rate',''))), S['body']), Spacer(1,3*mm)]
        gaps = to_list(otpb.get('content_angle_gaps_competitors_are_missing',[]))
        if gaps:
            story.append(tag("CONTENT GAPS COMPETITORS ARE MISSING"))
            for g in gaps: story.append(Paragraph(f"• {cl(str(g))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        logger.info("build_report1_pdf: S6 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S7 CONTENT EXECUTION PLAN ─────────────────────────────────────────────
    try:
        current_section = "S7 Content Execution Plan"
        cep = safe_dict(data.get('content_execution_plan'))
        story += sec_header(7, "Content Execution Plan")
        story += [insight_box(summaries.get('content_execution_plan','')), Spacer(1,3*mm)]
        if cep.get('recommended_posting_frequency'):
            story += [tag("RECOMMENDED POSTING FREQUENCY"), Paragraph(cl(val_to_str(cep.get('recommended_posting_frequency',''))), S['body']), Spacer(1,3*mm)]
        if cep.get('recommended_format_split'):
            story += [tag("RECOMMENDED FORMAT SPLIT"), Paragraph(cl(val_to_str(cep.get('recommended_format_split',''))), S['body']), Spacer(1,3*mm)]
        for week_key, week_label, week_color in [
            ('week_1_focus', 'WEEK 1', GREEN_OK),
            ('week_2_focus', 'WEEK 2', ACCENT),
            ('week_3_focus', 'WEEK 3', colors.HexColor("#2980B9")),
            ('week_4_focus', 'WEEK 4', MID_GRAY),
        ]:
            week = safe_dict(cep.get(week_key))
            if not week: continue
            story.append(black_hdr(week_label, week_color))
            w_rows = []
            for wk, wl in [('content_theme','CONTENT THEME'),('hook_to_use','HOOK TO USE'),('format','FORMAT')]:
                v = week.get(wk,'')
                if v: w_rows.append((wl, val_to_str(v)))
            pdays = to_list(week.get('posting_days',[]))
            if pdays: w_rows.append(("POSTING DAYS", ', '.join(str(d) for d in pdays)))
            if w_rows: story += [kv_table(w_rows, 42*mm), Spacer(1,2*mm)]
            htags = to_list(week.get('hashtag_set',[]))
            if htags: story += [tag("HASHTAG SET"), chip_row(htags, 3), Spacer(1,2*mm)]
            story.append(Spacer(1,2*mm))
        logger.info("build_report1_pdf: S7 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S8 WHAT TO STOP ───────────────────────────────────────────────────────
    try:
        current_section = "S8 What To Stop"
        s8 = data.get('what_to_stop', [])
        story += sec_header(8, "What To Stop")
        story += [insight_box(summaries.get('what_to_stop','')), Spacer(1,3*mm)]
        story += [Paragraph("Patterns that underperform in this category. Stop these to immediately improve content effectiveness.", S['alert']), Spacer(1,3*mm)]
        for item in to_list(s8):
            if isinstance(item, dict):
                pattern    = val_to_str(item.get('pattern', ''))
                reason     = val_to_str(item.get('reason', ''))
                data_basis = val_to_str(item.get('data_basis', ''))
                content = pattern if pattern else str(item)
                if reason:
                    content += f" — {reason}"
                story += [risk_box("STOP", content, RED_ALERT), Spacer(1,1*mm)]
                if data_basis and data_basis.lower() not in ('', 'none', 'null', 'n/a'):
                    story += [Paragraph(f"<b>Data basis:</b> {cl(data_basis)}", S['body']), Spacer(1,3*mm)]
                else:
                    story.append(Spacer(1,2*mm))
            else:
                story += [risk_box("STOP", str(item), RED_ALERT), Spacer(1,2*mm)]
        logger.info("build_report1_pdf: S8 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S9 PRIORITY ACTION PLAN ───────────────────────────────────────────────
    try:
        current_section = "S9 Priority Action Plan"
        s9 = data.get('priority_action_plan', [])
        story += sec_header(9, "Priority Action Plan")
        story += [insight_box(summaries.get('priority_action_plan','')), Spacer(1,3*mm)]
        story += [Paragraph("Ranked by impact. Every action traces back to a specific data observation.", S['body']), Spacer(1,3*mm)]
        for action in to_list(s9):
            if not isinstance(action, dict): continue
            rank = action.get('rank', '')
            try: rank_int = int(rank)
            except (TypeError, ValueError): rank_int = 0
            color = GREEN_OK if rank_int == 1 else ACCENT if rank_int in (2, 3) else DARK_GRAY
            action_text = val_to_str(action.get('action',''))
            story.append(black_hdr(f"ACTION {rank}: {cl(action_text)}", color))
            a_rows = []
            for key, label in [
                ('data_basis',       'DATA BASIS'),
                ('expected_outcome', 'EXPECTED OUTCOME'),
                ('effort',           'EFFORT'),
                ('time_to_impact',   'TIME TO IMPACT'),
            ]:
                v = action.get(key,'')
                if v: a_rows.append((label, val_to_str(v)))
            if a_rows: story += [kv_table(a_rows, 42*mm), Spacer(1,3*mm)]
        logger.info("build_report1_pdf: S9 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── S10 EMERGING SIGNALS ──────────────────────────────────────────────────
    try:
        current_section = "S10 Emerging Signals"
        es = safe_dict(data.get('emerging_signals'))
        story += sec_header(10, "Emerging Signals")
        story += [insight_box(summaries.get('emerging_signals','')), Spacer(1,3*mm)]
        story += [Paragraph("Patterns from the most recent 30% of posts in category data — rising trends before they peak.", S['body']), Spacer(1,3*mm)]
        rf = to_list(es.get('rising_content_formats',[]))
        rt = to_list(es.get('rising_topics',[]))
        rh = to_list(es.get('rising_hashtags',[]))
        if rf:
            story.append(tag("RISING CONTENT FORMATS"))
            for f in rf: story.append(Paragraph(f"• {cl(str(f))}", S['bullet']))
            story.append(Spacer(1,3*mm))
        if rt: story += [tag("RISING TOPICS"),   chip_row(rt, 3), Spacer(1,3*mm)]
        if rh: story += [tag("RISING HASHTAGS"), chip_row(rh, 3), Spacer(1,3*mm)]
        if es.get('early_signal_note'):
            story += [tag("SIGNAL NOTE"), Paragraph(cl(val_to_str(es.get('early_signal_note',''))), S['body']), Spacer(1,3*mm)]
        logger.info("build_report1_pdf: S10 OK")
    except Exception as e:
        logger.error(f"build_report1_pdf CRASHED at {current_section}: {e}\n{traceback.format_exc()}")
        raise

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    story += [
        Spacer(1,8*mm),
        HRFlowable(width="100%", thickness=1, color=ACCENT),
        Spacer(1,3*mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  offgridcreativesai@gmail.com  |  {today}  |  Confidential  |  Version 2.0", S['footer']),
        Spacer(1,2*mm),
        Paragraph(LEGAL, ParagraphStyle('FOOTDISC', fontName='Helvetica', fontSize=6,
            textColor=MID_GRAY, alignment=TA_CENTER, leading=8)),
    ]

    doc.build(story)
    logger.info("build_report1_pdf() COMPLETED SUCCESSFULLY")


def _extract_text_from_claude_r1(obj):
    """Extract the raw JSON text string from a Claude API response object."""
    original = obj
    if isinstance(obj, str):
        try: obj = json.loads(obj)
        except: return original
    if isinstance(obj, dict):
        if 'content' in obj:
            content_list = obj.get('content', [])
            if content_list:
                item = content_list[0]
                if isinstance(item, dict): return item.get('text', '')
                elif isinstance(item, str): return item
        else:
            return json.dumps(obj)
    return ''


def _parse_report1_body(body):
    """
    Parse the incoming request body and return (raw_json, brand_name, brand_category, brand_market, email).
    Handles base64-encoded claude_response, raw Claude API objects, and report_json fallback.
    """
    brand_name     = (body.get('brand_name') or '').strip() or 'Brand'
    brand_category = (body.get('brand_category') or '').strip() or 'D2C Brand'
    brand_market   = (body.get('brand_market') or '').strip() or 'India'
    email          = (body.get('email') or '').strip()

    raw_json = ''

    claude_response = body.get('claude_response')
    if claude_response:
        if isinstance(claude_response, str):
            # Try base64 decode first (Make.com sends base64(content[1].text))
            try:
                decoded = base64.b64decode(claude_response).decode('utf-8')
                raw_json = decoded
            except Exception:
                raw_json = _extract_text_from_claude_r1(claude_response)
        else:
            raw_json = _extract_text_from_claude_r1(claude_response)

    if not raw_json:
        raw_json = body.get('report_json') or body.get('Report_json') or ''
        if raw_json:
            extracted = _extract_text_from_claude_r1(raw_json)
            if extracted:
                raw_json = extracted

    # Strip markdown fences and control characters
    raw_json = re.sub(r'^```json\s*', '', raw_json.strip())
    raw_json = re.sub(r'^```\s*', '', raw_json)
    raw_json = re.sub(r'\s*```$', '', raw_json)
    raw_json = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_json)
    raw_json = escape_literal_newlines_in_strings(raw_json)

    return raw_json, brand_name, brand_category, brand_market, email


def _build_report1_pdf_bytes(body):
    """Parse body, build PDF, return (pdf_base64, filename). Raises on any error."""
    raw_json, brand_name, brand_category, brand_market, _ = _parse_report1_body(body)
    logger.info("Report1 request: brand_name=%r, brand_category=%r, brand_market=%r",
                brand_name, brand_category, brand_market)

    try:
        report_data = json.loads(raw_json)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw_json, re.DOTALL)
        if match:
            raw_json = match.group(0)
        report_data = json.loads(raw_json)

    if isinstance(report_data, str):
        report_data = json.loads(report_data)

    # Quality gate: warn but allow low-data reports (hashtag scraper may return few posts)
    landscape = report_data.get('category_landscape', {}) if isinstance(report_data, dict) else {}
    posts_count = landscape.get('total_posts_analysed', 0)
    try:
        posts_count = int(posts_count)
    except (TypeError, ValueError):
        posts_count = 0
    if posts_count == 0:
        logger.warning("Quality warning: 0 posts analysed in Claude response. Generating report anyway with available data.")
    else:
        logger.info(f"Quality gate passed: {posts_count} posts analysed")

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        output_path = f.name

    build_report1_pdf(report_data, brand_name, brand_category, brand_market, output_path)

    with open(output_path, 'rb') as f:
        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
    os.unlink(output_path)

    filename = f"{brand_name.replace(' ', '_')}_SocialMediaReport.pdf"
    return pdf_base64, filename, brand_name


def _deliver_report1_background(body):
    """
    Background thread: build the PDF then POST pdf_base64 to the Make.com
    delivery webhook (MAKE_WEBHOOK_URL). If that env var is not set, logs a
    warning — the PDF was generated but not delivered.
    """
    import urllib.request as _urlreq
    import urllib.error as _urlerr

    try:
        _, _, _, _, email = _parse_report1_body(body)
        pdf_base64, filename, brand_name = _build_report1_pdf_bytes(body)

        webhook_url = os.environ.get('MAKE_WEBHOOK_URL', '').strip()
        if not webhook_url:
            logger.warning("MAKE_WEBHOOK_URL not set — PDF built but not delivered for %s", brand_name)
            return

        payload = json.dumps({
            "pdf_base64": pdf_base64,
            "filename": "Report.pdf",          # hardcoded — dynamic names cause BundleValidationError
            "email": email,
            "brand_name": brand_name
        }).encode('utf-8')

        req = _urlreq.Request(
            webhook_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with _urlreq.urlopen(req, timeout=30) as resp:
                logger.info("Webhook delivered for %s — HTTP %s", brand_name, resp.status)
        except _urlerr.HTTPError as e:
            logger.error("Webhook HTTP error for %s: %s %s", brand_name, e.code, e.reason)
        except Exception as e:
            logger.error("Webhook delivery failed for %s: %s", brand_name, e)

    except Exception as e:
        logger.error("Background report1 processing failed: %s\n%s", e, traceback.format_exc())


@app.route('/generate-report1-full', methods=['POST'])
def generate_report1_full():
    """
    Combined endpoint: receives brand info + base64-encoded Apify data,
    calls Claude API, generates PDF, returns base64 PDF.
    This consolidates the Make.com Claude API call + PDF generation into one Railway call,
    avoiding JSON escaping issues in Make.com's jsonStringBodyContent.
    """
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    import time as _time

    try:
        body = request.get_json(force=True)
        if not body:
            return jsonify({"error": "No body received"}), 400

        brand_name     = (body.get('brand_name') or '').strip() or 'Brand'
        brand_category = (body.get('brand_category') or '').strip() or 'D2C Brand'
        brand_market   = (body.get('brand_market') or '').strip() or 'India'
        email          = (body.get('email') or '').strip()
        competitor_handles = (body.get('competitor_handles') or '').strip() or 'none provided'

        # Decode base64-encoded Apify data
        apify_data_b64 = body.get('apify_data', '')
        if apify_data_b64:
            try:
                apify_data_raw = base64.b64decode(apify_data_b64).decode('utf-8')
            except Exception:
                apify_data_raw = apify_data_b64  # fallback: maybe it's already raw
        else:
            apify_data_raw = '[]'

        logger.info("/generate-report1-full: brand=%r, category=%r, market=%r, raw_apify_len=%d",
                     brand_name, brand_category, brand_market, len(apify_data_raw))

        # Trim Apify data to only fields Claude needs (raw data can be 3MB+ with image URLs etc.)
        KEEP_FIELDS = {'ownerUsername', 'likesCount', 'commentsCount', 'type', 'caption',
                       'hashtags', 'timestamp', 'followersCount', 'ownerFullName',
                       'shortCode', 'videoViewCount', 'videoDuration'}
        try:
            apify_posts = json.loads(apify_data_raw)
            if isinstance(apify_posts, list):
                trimmed = []
                for post in apify_posts:
                    if isinstance(post, dict):
                        trimmed.append({k: post[k] for k in KEEP_FIELDS if k in post})
                apify_data_raw = json.dumps(trimmed, ensure_ascii=False)
                logger.info("/generate-report1-full: trimmed %d posts, data_len=%d",
                             len(trimmed), len(apify_data_raw))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("/generate-report1-full: could not parse Apify data for trimming: %s", e)

        # --- Call Claude API ---
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

        system_prompt = (
            "You are a social media intelligence analyst. Analyse the Instagram data provided and return ONLY valid JSON "
            "following the EXACT schema below. Use ONLY numbers and facts present in the data. DO NOT invent, estimate, or "
            "assume any metric not present in the data. If a field cannot be computed, use null. No preamble, no markdown, "
            "no explanation. Start with { end with }.\n"
            "DATA FORMAT: The CATEGORY_DATA is a raw JSON array of Instagram posts. Each post object has these key fields: "
            "ownerUsername, likesCount, commentsCount, type (Image/Video/Sidecar), caption, hashtags (array), timestamp. "
            "The followersCount field is NOT available from the hashtag scraper - when missing or 0, it means unavailable, "
            "NOT zero followers. Do NOT exclude any posts. Include ALL posts in your analysis. Set total_posts_analysed to "
            "the actual count of post objects in the array.\n"
            "ENGAGEMENT RATE: When followersCount is 0 or unavailable, engagement rate cannot be calculated - set it to null. "
            "Only calculate ER when followersCount > 0.\n"
            "COMPETITOR INTELLIGENCE RULE: The client has provided competitor Instagram handles. Search through CATEGORY_DATA "
            "for posts from these exact handles. If you find posts from a competitor handle, extract their hooks (first line of "
            "caption), CTAs, hashtag strategy, content format, and posting patterns. If a competitor handle does NOT appear in "
            "CATEGORY_DATA, set their fields to null and note: Competitor not found in category data.\n"
            "BRAND DATA NOTE: Brand data is not available in this version. brand_positioning sections should be set to null with "
            "note: Brand data will be available after Instagram account connection is set up.\n"
            "SUMMARIES RULE: For the summaries object, write 2-3 plain-English sentences per key. Address the brand owner directly. "
            "Use specific numbers, handles, and format names from the data. Each summary answers: what does this section mean for "
            "their brand right now.\n"
            "Do not use double quotes inside string values - use single quotes instead.\n"
            'EXACT SCHEMA (use these exact key names only):\n'
            '{"category_landscape":{"total_posts_analysed":"","total_accounts_analysed":"","avg_engagement_rate_category":"",'
            '"top_engagement_rate_seen":"","lowest_engagement_rate_seen":"","dominant_content_format":"","avg_posting_frequency":"",'
            '"most_active_posting_days":[],"most_active_posting_hours":[],"top_5_hashtags_by_frequency":[],"data_quality_note":""},'
            '"competitor_success_blueprint":{"top_performers":[{"handle":"","follower_count":null,"avg_engagement_rate":null,'
            '"posts_analysed":null,"dominant_format":"","hook_pattern":"","cta_pattern":"","hashtag_strategy":"",'
            '"top_performing_caption_example":"","what_makes_them_win":""}],"common_patterns_across_top_performers":[],'
            '"content_gaps_competitors_are_missing":[]},"brand_positioning":{"data_status":"Brand Instagram not yet connected - '
            'coming in next version","own_avg_engagement_rate":null,"category_avg_engagement_rate":"","own_dominant_format":null,'
            '"category_dominant_format":"","whitespace_opportunity":"","one_line_brand_verdict":null},"hook_format_intelligence":'
            '{"top_3_hooks_by_engagement":[{"hook_text":"","hook_type":"","avg_engagement_on_posts_using_this_pattern":"",'
            '"post_count_with_this_pattern":""}],"best_performing_format":"","worst_performing_format":"","optimal_caption_length":"",'
            '"emoji_usage_pattern":"","cta_patterns_in_top_posts":[]},"audience_intelligence":{"comment_sentiment_summary":"",'
            '"top_positive_triggers":[],"top_negative_triggers":[],"questions_audience_asks_repeatedly":[],'
            '"purchase_intent_signals":[],"content_topics_that_drive_comments":[]},"organic_to_paid_bridge":'
            '{"organic_formats_with_paid_potential":[{"format":"","reason":"","example_hook_structure":""}],'
            '"hook_styles_that_stop_scroll":[],"content_angle_gaps_competitors_are_missing":[]},"content_execution_plan":'
            '{"recommended_posting_frequency":"","recommended_format_split":"","week_1_focus":{"content_theme":"","hook_to_use":"",'
            '"format":"","posting_days":[],"hashtag_set":[]},"week_2_focus":{"content_theme":"","hook_to_use":"","format":"",'
            '"posting_days":[],"hashtag_set":[]},"week_3_focus":{"content_theme":"","hook_to_use":"","format":"","posting_days":[],'
            '"hashtag_set":[]},"week_4_focus":{"content_theme":"","hook_to_use":"","format":"","posting_days":[],"hashtag_set":[]}},'
            '"what_to_stop":[{"pattern":"","reason":"","data_basis":""}],"priority_action_plan":[{"rank":1,"action":"",'
            '"data_basis":"","expected_outcome":"","effort":"","time_to_impact":""}],"emerging_signals":{"rising_content_formats":[],'
            '"rising_topics":[],"rising_hashtags":[],"early_signal_note":""},"summaries":{"category_landscape":"",'
            '"competitor_success_blueprint":"","hook_format_intelligence":"","audience_intelligence":"","organic_to_paid_bridge":"",'
            '"content_execution_plan":"","what_to_stop":"","priority_action_plan":"","emerging_signals":""}}'
        )

        user_message = (
            f"Brand: {brand_name}\n"
            f"Category: {brand_category}\n"
            f"Market: {brand_market}\n"
            f"Competitor handles to find in data: {competitor_handles}\n\n"
            f"INSTRUCTION: Analyse ALL posts in the CATEGORY_DATA JSON array below. "
            f"Count them, extract patterns, find competitor handles if present. Do NOT skip any posts.\n\n"
            f"CATEGORY_DATA (JSON array of Instagram posts):\n{apify_data_raw}"
        )

        claude_payload = json.dumps({
            "model": "claude-opus-4-6",
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}]
        }).encode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }

        # Call Claude with retry logic
        claude_result = None
        last_err = None
        for attempt in range(4):
            req = _urlreq.Request(
                "https://api.anthropic.com/v1/messages",
                data=claude_payload,
                headers=headers,
                method="POST"
            )
            try:
                with _urlreq.urlopen(req, timeout=120) as resp:
                    claude_result = json.loads(resp.read().decode('utf-8'))
                break
            except _urlerr.HTTPError as he:
                last_err = he
                if he.code in (429, 529) and attempt < 3:
                    wait = (attempt + 1) * 5
                    logger.warning("/generate-report1-full: Claude API %d, retrying in %ds (attempt %d/4)",
                                   he.code, wait, attempt + 1)
                    _time.sleep(wait)
                    continue
                err_body = he.read().decode('utf-8', errors='replace') if hasattr(he, 'read') else str(he)
                logger.error("/generate-report1-full: Claude API error %d: %s", he.code, err_body[:500])
                raise

        if claude_result is None:
            raise last_err or RuntimeError("Claude API call failed after retries")

        # Extract the text response from Claude
        claude_text = claude_result.get('content', [{}])[0].get('text', '').strip()
        logger.info("/generate-report1-full: Claude response length=%d", len(claude_text))

        # Build PDF using existing infrastructure
        pdf_body = {
            'claude_response': base64.b64encode(claude_text.encode('utf-8')).decode('utf-8'),
            'brand_name': brand_name,
            'brand_category': brand_category,
            'brand_market': brand_market,
            'email': email
        }

        try:
            pdf_base64, filename, _ = _build_report1_pdf_bytes(pdf_body)
        except json.JSONDecodeError as e:
            logger.error("/generate-report1-full: PDF build JSON error: %s\nClaude text: %s", e, claude_text[:1000])
            return jsonify({"error": f"Claude response was not valid JSON: {str(e)}", "claude_text_preview": claude_text[:500]}), 500

        return jsonify({
            "status": "success",
            "filename": filename,
            "pdf_base64": pdf_base64
        }), 200

    except Exception as e:
        logger.error("/generate-report1-full error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/generate-report1-pdf', methods=['POST'])
def generate_report1_pdf():
    """
    If MAKE_WEBHOOK_URL is set: immediately return {"status": "processing"} and
    generate + deliver the PDF in a background thread via Make.com webhook.

    If MAKE_WEBHOOK_URL is NOT set: synchronous mode — build PDF and return
    pdf_base64 directly (legacy Make.com Module 7 flow still works).
    """
    try:
        # Support both multipart/form-data and JSON body
        content_type = request.content_type or ''
        if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            body = request.form.to_dict()
        else:
            body = request.get_json(force=True)
        if not body:
            return jsonify({"error": "No body received"}), 400

        webhook_url = os.environ.get('MAKE_WEBHOOK_URL', '').strip()

        if webhook_url:
            # --- ASYNC MODE: respond immediately, deliver via webhook ---
            t = threading.Thread(target=_deliver_report1_background, args=(body,), daemon=True)
            t.start()
            return jsonify({"status": "processing"}), 200

        else:
            # --- SYNC MODE: build PDF and return base64 (legacy flow) ---
            try:
                pdf_base64, filename, _ = _build_report1_pdf_bytes(body)
            except json.JSONDecodeError as e:
                return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

            return jsonify({
                "status": "success",
                "filename": filename,
                "pdf_base64": pdf_base64
            }), 200

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/generate-hashtags', methods=['POST'])
def generate_hashtags():
    import urllib.request as _urlreq
    try:
        raw_data = request.get_data(as_text=True)
        logger.info(f"/generate-hashtags raw body: {raw_data[:500]!r}")
        logger.info(f"/generate-hashtags Content-Type: {request.content_type}")
        body = request.get_json(force=True) or {}
        logger.info(f"/generate-hashtags parsed body keys: {list(body.keys())}")
        category = body.get('category', '').strip()
        if not category:
            logger.warning(f"/generate-hashtags: empty category, full body: {body}")
            return jsonify({"error": "category is required", "received_body": body}), 400

        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

        prompt = (
            "Generate 6-8 relevant Instagram hashtags for the brand category below. "
            "Rules: lowercase, alphanumeric only, no spaces, no hyphens, no special characters, no hash symbol. "
            "Return ONLY a raw JSON array. No markdown, no code fences, no explanation.\n\n"
            f"Brand category: {category}"
        )
        payload = json.dumps({
            "model": "claude-opus-4-6",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')

        import time as _time
        import urllib.error as _urlerr

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        result = None
        last_err = None
        for attempt in range(4):
            req = _urlreq.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers=headers,
                method="POST"
            )
            try:
                with _urlreq.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                break
            except _urlerr.HTTPError as he:
                last_err = he
                if he.code in (429, 529) and attempt < 3:
                    wait = (attempt + 1) * 3  # 3, 6, 9 seconds
                    logger.warning(f"/generate-hashtags: API returned {he.code}, retrying in {wait}s (attempt {attempt+1}/4)")
                    _time.sleep(wait)
                    continue
                raise
        if result is None:
            raise last_err or RuntimeError("API call failed after retries")

        text = result['content'][0]['text'].strip()
        text = text.replace('```json', '').replace('```', '').strip()
        hashtags = json.loads(text)

        if not isinstance(hashtags, list):
            raise ValueError("Response was not a JSON array")

        # Final sanitisation: lowercase, alphanumeric only, drop empties
        clean = [re.sub(r'[^a-z0-9]', '', h.lower()) for h in hashtags if isinstance(h, str)]
        clean = [h for h in clean if h]

        apify_body = json.dumps({"hashtags": clean, "resultsLimit": 50, "resultsType": "posts"})
        hashtag_list = ",".join(clean)
        first_hashtag = clean[0] if clean else ""
        logger.info(f"/generate-hashtags: category={category!r} → {clean}")
        return jsonify({"hashtags": clean, "apify_body": apify_body, "hashtag_list": hashtag_list, "first_hashtag": first_hashtag})

    except Exception as e:
        logger.error(f"/generate-hashtags error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    env_names = [k for k in os.environ if 'ANTH' in k.upper() or 'API' in k.upper() or 'KEY' in k.upper()]
    return jsonify({"status": "ok", "api_key_set": bool(key), "api_key_length": len(key), "related_env_vars": env_names}), 200



# ════════════════════════════════════════════════════════════════════
# MULTI-PLATFORM SCRAPING ENGINE
# ════════════════════════════════════════════════════════════════════

APIFY_ACTORS = {
    'instagram': 'apify/instagram-profile-scraper',
    'instagram_posts': 'apify/instagram-post-scraper',
    'youtube': 'streamers/youtube-channel-scraper',
    'linkedin': 'dev_fusion/Linkedin-Profile-Scraper',
    'tiktok': 'clockworks/tiktok-profile-scraper',
    'website': 'apify/website-content-crawler',
}


def apify_run_actor(actor_name, input_data, timeout_secs=120):
    """Run an Apify actor and return the dataset items."""
    token = os.environ.get('APIFY_TOKEN', '')
    if not token:
        return {'error': 'APIFY_TOKEN not set', 'platform': actor_name}

    actor_id = actor_name.replace('/', '~')
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={token}"

    try:
        resp = http_requests.post(run_url, json=input_data, timeout=30)
        resp.raise_for_status()
        run_data = resp.json()['data']
        run_id = run_data['id']
        dataset_id = run_data['defaultDatasetId']

        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            time.sleep(5)
            status_resp = http_requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}", timeout=15
            )
            status = status_resp.json()['data']['status']
            if status == 'SUCCEEDED':
                items_resp = http_requests.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}", timeout=30
                )
                return items_resp.json()
            if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                return {'error': f'Actor run {status}', 'run_id': run_id}

        return {'error': 'Actor run timed out waiting', 'run_id': run_id}
    except Exception as e:
        return {'error': str(e)}


def scrape_instagram(handle, posts_limit=30):
    """Scrape Instagram profile + recent posts (up to posts_limit)."""
    handle = handle.lstrip('@').strip()
    if not handle:
        return None

    # Get profile info
    data = apify_run_actor(APIFY_ACTORS['instagram'], {
        'usernames': [handle],
        'resultsLimit': 1
    }, timeout_secs=90)

    if not isinstance(data, list) or len(data) == 0:
        return {'platform': 'instagram', 'handle': handle, 'error': 'No data returned', 'raw': data}

    profile = data[0]
    posts = profile.get('latestPosts', [])
    followers = profile.get('followersCount', 0)

    # If profile scraper returned fewer posts than desired, supplement with post scraper
    if len(posts) < posts_limit:
        try:
            extra = apify_run_actor(APIFY_ACTORS['instagram_posts'], {
                'directUrls': [f"https://www.instagram.com/{handle}/"],
                'resultsLimit': posts_limit
            }, timeout_secs=120)
            if isinstance(extra, list) and len(extra) > len(posts):
                posts = extra
                logger.info(f"[SCRAPE] Extended posts for @{handle}: {len(posts)} posts via post scraper")
        except Exception as e:
            logger.warning(f"[SCRAPE] Post scraper supplement failed for @{handle}: {e}")

    post_count = len(posts)
    total_likes = sum(p.get('likesCount', 0) for p in posts)
    total_comments = sum(p.get('commentsCount', 0) for p in posts)
    avg_er = ((total_likes + total_comments) / max(followers, 1) / max(post_count, 1)) * 100 if post_count > 0 else 0

    # Smart format classification — Apify returns type='Video' for both Reels and regular videos.
    # Use productType='clips' to identify Reels specifically. Also catch cases where
    # type='Image' but videoUrl is present (misclassified video).
    format_counts = {}
    for p in posts:
        raw_type = p.get('type', 'Unknown')
        product_type = p.get('productType', '')
        has_video = bool(p.get('videoUrl'))

        if raw_type == 'Sidecar':
            fmt = 'Carousel'
        elif product_type == 'clips' or (raw_type == 'Video' and not product_type):
            fmt = 'Reel'
        elif has_video and raw_type == 'Image':
            # Misclassified video — Apify sometimes returns type=Image for videos
            fmt = 'Reel'
        elif raw_type == 'Video' and product_type and product_type != 'clips':
            fmt = 'Video'  # IGTV or other video type
        elif raw_type == 'Image':
            fmt = 'Image'
        else:
            fmt = raw_type
        p['_classified_format'] = fmt  # Store for later use
        format_counts[fmt] = format_counts.get(fmt, 0) + 1

    # Calculate total video views (Reels views)
    total_video_views = sum(p.get('videoViewCount', 0) for p in posts if p.get('videoViewCount'))
    video_posts_with_views = sum(1 for p in posts if p.get('videoViewCount'))
    avg_video_views = round(total_video_views / max(video_posts_with_views, 1)) if video_posts_with_views else 0

    captions = [p.get('caption', '') or '' for p in posts]
    hook_types = classify_hooks(captions)

    # Calculate posting frequency (posts per week)
    timestamps = [p.get('timestamp', '') for p in posts if p.get('timestamp')]
    posting_freq = None
    if len(timestamps) >= 2:
        try:
            from datetime import datetime as _dt
            dates = sorted([_dt.fromisoformat(t.replace('Z', '+00:00')) for t in timestamps if t])
            if len(dates) >= 2:
                span_days = (dates[-1] - dates[0]).days or 1
                posting_freq = round(len(dates) / (span_days / 7), 1)
        except Exception:
            pass

    # Caption length analysis
    caption_lengths = [len(c) for c in captions if c]
    avg_caption_len = round(sum(caption_lengths) / max(len(caption_lengths), 1)) if caption_lengths else 0

    # Hashtag analysis
    all_hashtags = {}
    for p in posts:
        for ht in (p.get('hashtags') or []):
            ht_lower = ht.lower().strip('#')
            all_hashtags[ht_lower] = all_hashtags.get(ht_lower, 0) + 1
    top_hashtags = sorted(all_hashtags.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        'platform': 'instagram',
        'handle': handle,
        'full_name': profile.get('fullName', ''),
        'bio': profile.get('biography', ''),
        'followers': followers,
        'following': profile.get('followsCount', 0),
        'total_posts': profile.get('postsCount', 0),
        'verified': profile.get('verified', False),
        'is_business': profile.get('isBusinessAccount', False),
        'category': profile.get('businessCategoryName', ''),
        'external_url': profile.get('externalUrl', ''),
        'highlights_count': profile.get('highlightReelCount', 0),
        'recent_posts_count': post_count,
        'avg_likes': round(total_likes / max(post_count, 1), 1),
        'avg_comments': round(total_comments / max(post_count, 1), 1),
        'avg_er_pct': round(avg_er, 4),
        'format_breakdown': format_counts,
        'hook_analysis': hook_types,
        'posting_frequency_per_week': posting_freq,
        'avg_caption_length': avg_caption_len,
        'top_hashtags': top_hashtags,
        'avg_video_views': avg_video_views,
        'total_video_views': total_video_views,
        'top_posts': sorted(posts, key=lambda p: p.get('likesCount', 0), reverse=True)[:5],
        'recent_posts': [{
            'type': p.get('_classified_format', p.get('type', '')),
            'likes': p.get('likesCount', 0),
            'comments': p.get('commentsCount', 0),
            'views': p.get('videoViewCount', 0),
            'caption': (p.get('caption', '') or '')[:300],
            'timestamp': p.get('timestamp', ''),
            'hashtags': p.get('hashtags', []),
        } for p in posts],
    }


def scrape_youtube(channel_url):
    """Scrape YouTube channel data."""
    if not channel_url or not channel_url.strip():
        return None
    channel_url = channel_url.strip()
    if not channel_url.startswith('http'):
        channel_url = f"https://www.youtube.com/@{channel_url}"
    data = apify_run_actor(APIFY_ACTORS['youtube'], {
        'channelUrls': [channel_url],
        'maxResults': 10,
        'maxResultsShorts': 5,
    }, timeout_secs=120)
    if isinstance(data, list) and len(data) > 0:
        items = data
        channel_info = items[0] if items else {}
        return {
            'platform': 'youtube',
            'url': channel_url,
            'data': items[:15],
            'video_count': len(items),
        }
    return {'platform': 'youtube', 'url': channel_url, 'error': 'No data returned', 'raw': data}


def scrape_linkedin(linkedin_url):
    """Scrape LinkedIn profile/company data."""
    if not linkedin_url or not linkedin_url.strip():
        return None
    linkedin_url = linkedin_url.strip()
    if not linkedin_url.startswith('http'):
        linkedin_url = f"https://www.linkedin.com/in/{linkedin_url}"
    data = apify_run_actor(APIFY_ACTORS['linkedin'], {
        'profileUrls': [linkedin_url],
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'linkedin',
            'url': linkedin_url,
            'data': data[0],
        }
    return {'platform': 'linkedin', 'url': linkedin_url, 'error': 'No data returned', 'raw': data}


def scrape_tiktok(handle):
    """Scrape TikTok profile data."""
    if not handle or not handle.strip():
        return None
    handle = handle.lstrip('@').strip()
    data = apify_run_actor(APIFY_ACTORS['tiktok'], {
        'profiles': [handle],
        'resultsPerPage': 10,
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'tiktok',
            'handle': handle,
            'data': data[:15],
        }
    return {'platform': 'tiktok', 'handle': handle, 'error': 'No data returned', 'raw': data}


def scrape_website(url):
    """Crawl and audit a website."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if not url.startswith('http'):
        url = f"https://{url}"
    data = apify_run_actor(APIFY_ACTORS['website'], {
        'startUrls': [{'url': url}],
        'maxCrawlPages': 5,
        'crawlerType': 'cheerio',
    }, timeout_secs=90)
    if isinstance(data, list) and len(data) > 0:
        return {
            'platform': 'website',
            'url': url,
            'pages_crawled': len(data),
            'data': [{
                'url': p.get('url', ''),
                'title': p.get('metadata', {}).get('title', '') if isinstance(p.get('metadata'), dict) else '',
                'description': p.get('metadata', {}).get('description', '') if isinstance(p.get('metadata'), dict) else '',
                'text': (p.get('text', '') or '')[:2000],
            } for p in data[:5]],
        }
    return {'platform': 'website', 'url': url, 'error': 'No data returned', 'raw': data}


def classify_hooks(captions):
    """Classify caption hooks into types based on first line patterns."""
    types = {
        'question': 0, 'curiosity': 0, 'philosophy': 0, 'story': 0,
        'negative': 0, 'achievement': 0, 'contrarian': 0, 'direct_cta': 0,
        'empathy': 0, 'authority': 0, 'other': 0
    }
    for cap in captions:
        if not cap:
            continue
        first_line = cap.split('\n')[0].lower().strip()
        if '?' in first_line:
            types['question'] += 1
        elif any(w in first_line for w in ['secret', 'hidden', 'nobody', 'most people', 'what if']):
            types['curiosity'] += 1
        elif any(w in first_line for w in ['stop', 'don\'t', 'never', 'warning', 'mistake']):
            types['negative'] += 1
        elif any(w in first_line for w in ['i was', 'my story', 'when i', 'years ago']):
            types['story'] += 1
        elif any(w in first_line for w in ['dm', 'book', 'click', 'link in bio', 'order now']):
            types['direct_cta'] += 1
        elif any(w in first_line for w in ['stuck', 'struggling', 'tired of', 'feeling']):
            types['empathy'] += 1
        elif any(w in first_line for w in ['✨', '🌙', '🔮', 'universe', 'energy', 'manifest']):
            types['philosophy'] += 1
        else:
            types['other'] += 1
    total = sum(types.values()) or 1
    return {k: {'count': v, 'pct': round(v / total * 100, 1)} for k, v in types.items() if v > 0}


def scrape_category_top_accounts(brand_category, max_accounts=25):
    """
    Scrape category hashtags to find top accounts in the niche.
    Returns aggregated account stats from hashtag post data.
    """
    # Generate category hashtags using Claude
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY not set'}

    import anthropic as _anthropic
    prompt = (
        "Generate 5 highly specific Instagram hashtags for the brand category below. "
        "These should be hashtags that active creators/brands in this EXACT niche use regularly. "
        "Rules: lowercase, alphanumeric only, no spaces, no hyphens, no special characters, no hash symbol. "
        "Return ONLY a raw JSON array. No markdown, no code fences.\n\n"
        f"Brand category: {brand_category}"
    )
    try:
        _client = _anthropic.Anthropic(api_key=api_key)
        _resp = _client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = _resp.content[0].text.strip().replace('```json', '').replace('```', '').strip()
        hashtags = json.loads(text)
        clean = [re.sub(r'[^a-z0-9]', '', h.lower()) for h in hashtags if isinstance(h, str)]
        clean = [h for h in clean if h][:5]
    except Exception as e:
        logger.error(f"[CATEGORY] Hashtag generation failed: {e}")
        return {'error': f'Hashtag generation failed: {e}'}

    logger.info(f"[CATEGORY] Generated hashtags for '{brand_category}': {clean}")

    # Scrape posts from category hashtags
    hashtag_data = apify_run_actor('apify/instagram-hashtag-scraper', {
        'hashtags': clean,
        'resultsLimit': 100,
        'resultsType': 'posts'
    }, timeout_secs=180)

    if not isinstance(hashtag_data, list) or len(hashtag_data) == 0:
        return {'error': 'No hashtag data returned', 'hashtags': clean}

    logger.info(f"[CATEGORY] Scraped {len(hashtag_data)} posts from hashtags")

    # Aggregate by account
    accounts = {}
    for post in hashtag_data:
        if not isinstance(post, dict):
            continue
        username = post.get('ownerUsername', '')
        if not username:
            continue
        if username not in accounts:
            accounts[username] = {
                'handle': username,
                'posts': [],
                'total_likes': 0,
                'total_comments': 0,
                'followers': post.get('followersCount', 0) or 0,
            }
        acc = accounts[username]
        likes = post.get('likesCount', 0) or 0
        comments = post.get('commentsCount', 0) or 0
        acc['posts'].append({
            'likes': likes,
            'comments': comments,
            'type': post.get('type', ''),
            'caption': (post.get('caption', '') or '')[:200],
            'hashtags': post.get('hashtags', []),
        })
        acc['total_likes'] += likes
        acc['total_comments'] += comments
        # Update followers if we get a non-zero value
        if (post.get('followersCount') or 0) > acc['followers']:
            acc['followers'] = post['followersCount']

    # Filter bots: min 500 followers or min 3 posts in data
    filtered = {}
    for username, acc in accounts.items():
        post_count = len(acc['posts'])
        followers = acc['followers']
        if followers >= 1000 and post_count >= 3:
            avg_likes = acc['total_likes'] / max(post_count, 1)
            avg_comments = acc['total_comments'] / max(post_count, 1)
            er = ((avg_likes + avg_comments) / max(followers, 1)) * 100 if followers > 0 else 0
            # Skip if ER is suspiciously high (likely bot or engagement pod)
            if er > 25:
                continue
            format_counts = {}
            for p in acc['posts']:
                raw_type = p.get('type', 'Unknown')
                product_type = p.get('productType', '')
                has_video = bool(p.get('videoUrl'))
                if raw_type == 'Sidecar':
                    fmt = 'Carousel'
                elif product_type == 'clips' or (raw_type == 'Video' and not product_type):
                    fmt = 'Reel'
                elif has_video and raw_type == 'Image':
                    fmt = 'Reel'
                elif raw_type == 'Video' and product_type and product_type != 'clips':
                    fmt = 'Video'
                elif raw_type == 'Image':
                    fmt = 'Image'
                else:
                    fmt = raw_type
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
            filtered[username] = {
                'handle': username,
                'followers': followers,
                'posts_in_data': post_count,
                'avg_likes': round(avg_likes, 1),
                'avg_comments': round(avg_comments, 1),
                'avg_er_pct': round(er, 4),
                'format_breakdown': format_counts,
                'hook_analysis': classify_hooks([p.get('caption', '') for p in acc['posts']]),
                'top_caption': max(acc['posts'], key=lambda p: p['likes']).get('caption', '') if acc['posts'] else '',
            }

    # Sort by engagement rate, take top N
    sorted_accounts = sorted(filtered.values(), key=lambda x: x['avg_er_pct'], reverse=True)[:max_accounts]

    # Calculate category benchmarks
    all_ers = [a['avg_er_pct'] for a in sorted_accounts if a['avg_er_pct'] > 0]
    all_followers = [a['followers'] for a in sorted_accounts if a['followers'] > 0]
    category_avg_er = round(sum(all_ers) / max(len(all_ers), 1), 4) if all_ers else 0
    category_median_followers = sorted(all_followers)[len(all_followers) // 2] if all_followers else 0

    # Format breakdown across category
    cat_formats = {}
    for acc in sorted_accounts:
        for fmt, cnt in acc.get('format_breakdown', {}).items():
            cat_formats[fmt] = cat_formats.get(fmt, 0) + cnt
    total_fmt = sum(cat_formats.values()) or 1
    cat_format_pct = {k: round(v / total_fmt * 100, 1) for k, v in cat_formats.items()}

    return {
        'hashtags_used': clean,
        'total_posts_scraped': len(hashtag_data),
        'total_accounts_found': len(accounts),
        'accounts_after_filter': len(filtered),
        'top_accounts': sorted_accounts,
        'category_benchmarks': {
            'avg_engagement_rate': category_avg_er,
            'median_followers': category_median_followers,
            'dominant_formats': cat_format_pct,
            'total_posts_analyzed': len(hashtag_data),
        }
    }


def scrape_all_platforms(form_data):
    """Scrape all platforms in parallel based on provided handles, plus category top accounts."""
    results = {}
    tasks = {}

    with ThreadPoolExecutor(max_workers=7) as executor:
        # Brand's own profiles (30 posts for brand)
        if form_data.get('instagram_handle'):
            tasks['brand_instagram'] = executor.submit(scrape_instagram, form_data['instagram_handle'], 30)
        if form_data.get('youtube_channel'):
            tasks['brand_youtube'] = executor.submit(scrape_youtube, form_data['youtube_channel'])
        if form_data.get('linkedin_url'):
            tasks['brand_linkedin'] = executor.submit(scrape_linkedin, form_data['linkedin_url'])
        if form_data.get('tiktok_handle'):
            # Only scrape TikTok for international markets (banned in India)
            market = (form_data.get('target_market') or '').lower()
            if market not in ('india',):
                tasks['brand_tiktok'] = executor.submit(scrape_tiktok, form_data['tiktok_handle'])
        if form_data.get('website_url'):
            tasks['brand_website'] = executor.submit(scrape_website, form_data['website_url'])

        # Competitor Instagram profiles (20 posts each)
        for i, comp_handle in enumerate(form_data.get('competitor_handles', []), 1):
            if comp_handle and comp_handle.strip():
                tasks[f'competitor_{i}_instagram'] = executor.submit(scrape_instagram, comp_handle, 20)

        # Category-wide scraping (top 25 accounts from hashtags)
        if form_data.get('brand_category'):
            tasks['category_data'] = executor.submit(
                scrape_category_top_accounts, form_data['brand_category'], 25
            )

        for key, future in tasks.items():
            try:
                result = future.result(timeout=240)
                if result is not None:
                    results[key] = result
            except Exception as e:
                results[key] = {'error': str(e)}
                logger.error(f"[SCRAPE] {key} failed: {e}")

    # ── Phase 2: Auto-scrape top 3 category leaders as full profiles ──
    cat_data = results.get('category_data')
    if isinstance(cat_data, dict) and not cat_data.get('error'):
        top_accounts = cat_data.get('top_accounts', [])
        # Exclude any handles that are already scraped (brand or user-submitted competitors)
        already_scraped = set()
        brand_handle = (form_data.get('instagram_handle') or '').lstrip('@').strip().lower()
        if brand_handle:
            already_scraped.add(brand_handle)
        for ch in form_data.get('competitor_handles', []):
            if ch and ch.strip():
                already_scraped.add(ch.strip().lstrip('@').lower())

        leaders_to_scrape = []
        for acc in top_accounts:
            handle = (acc.get('handle') or '').lower()
            # Only scrape leaders with meaningful following (1000+) to avoid micro-accounts
            if handle and handle not in already_scraped and acc.get('followers', 0) >= 1000:
                leaders_to_scrape.append(handle)
            if len(leaders_to_scrape) >= 3:
                break

        if leaders_to_scrape:
            logger.info(f"[SCRAPE] Auto-scraping top {len(leaders_to_scrape)} category leaders: {leaders_to_scrape}")
            with ThreadPoolExecutor(max_workers=3) as executor2:
                leader_tasks = {}
                for i, lh in enumerate(leaders_to_scrape, 1):
                    leader_tasks[f'category_leader_{i}_instagram'] = executor2.submit(scrape_instagram, lh, 20)
                for key, future in leader_tasks.items():
                    try:
                        result = future.result(timeout=120)
                        if result is not None and not result.get('error'):
                            results[key] = result
                            logger.info(f"[SCRAPE] Category leader scraped: @{result.get('handle')} — {result.get('followers',0):,} followers, {result.get('avg_er_pct',0)}% ER")
                    except Exception as e:
                        logger.warning(f"[SCRAPE] Category leader {key} failed: {e}")

    return results


# ════════════════════════════════════════════════════════════════════
# AGENT PDF BUILDER — Renders Claude's {title, content} sections
# ════════════════════════════════════════════════════════════════════

def build_agent_pdf(report_data, form_data, scraped_data):
    """Build a professional branded PDF from Claude's analysis. Returns base64."""
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    W = 170*mm
    today = datetime.now().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(tmp.name, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm)
    story = []

    brand_name = form_data.get('brand_name', 'Brand')
    brand_category = form_data.get('brand_category', '')
    target_market = form_data.get('target_market', '')

    LEGAL = ("Legal notice: This report is based exclusively on publicly available social media data. "
             "Save rates, reach, impressions, and conversion rates are AI estimates where marked. "
             "No personally identifiable information has been collected or stored. For internal strategic use only.")

    # ── PDF Styles ──
    AMBER = colors.HexColor("#F39C12")
    DEEP_RED = colors.HexColor("#E74C3C")
    TEAL = colors.HexColor("#1ABC9C")
    CONTENT_STYLE = ParagraphStyle('CONTENT', fontName='Helvetica', fontSize=9.5,
        textColor=DARK_GRAY, leading=16, spaceAfter=6)
    BULLET_STYLE = ParagraphStyle('CBULLET', fontName='Helvetica', fontSize=9.5,
        textColor=DARK_GRAY, leading=16, spaceAfter=4, leftIndent=14, bulletIndent=0)
    SUBHEAD_STYLE = ParagraphStyle('SUBHEAD', fontName='Helvetica-Bold', fontSize=10.5,
        textColor=colors.HexColor("#222222"), leading=16, spaceAfter=4, spaceBefore=8)
    METRIC_BIG = ParagraphStyle('MBIG', fontName='Helvetica-Bold', fontSize=20, textColor=ACCENT, alignment=TA_CENTER)
    METRIC_LABEL = ParagraphStyle('MLAB', fontName='Helvetica', fontSize=7.5, textColor=MID_GRAY, alignment=TA_CENTER)
    METRIC_SUB = ParagraphStyle('MSUB', fontName='Helvetica', fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER)

    def metric_card(value, label, sub_text='', bg=LIGHT_GRAY, val_color=ACCENT):
        """Create a single metric card with large number + label."""
        val_style = ParagraphStyle('MV', fontName='Helvetica-Bold', fontSize=18, textColor=val_color, alignment=TA_CENTER)
        rows = [[Paragraph(cl(str(value)), val_style)], [Paragraph(cl(label), METRIC_LABEL)]]
        if sub_text:
            rows.append([Paragraph(cl(sub_text), METRIC_SUB)])
        t = Table(rows, colWidths=[W/3 - 4*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        return t

    def score_color(er_pct, cat_avg=1.0):
        """Return color based on ER vs category average."""
        if er_pct >= cat_avg * 1.5:
            return GREEN_OK
        elif er_pct >= cat_avg * 0.7:
            return AMBER
        return DEEP_RED

    def comparison_table(rows_data, headers=None):
        """Create a professional comparison table."""
        tbl_rows = []
        if headers:
            hdr_cells = [Paragraph(f"<b>{cl(h)}</b>", ParagraphStyle('TH', fontName='Helvetica-Bold',
                fontSize=8, textColor=WHITE)) for h in headers]
            tbl_rows.append(hdr_cells)
        for row in rows_data:
            tbl_rows.append([Paragraph(cl(str(c)), S['body']) for c in row])
        cols = len(tbl_rows[0]) if tbl_rows else 3
        col_w = W / cols
        t = Table(tbl_rows, colWidths=[col_w] * cols)
        style_cmds = [
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('INNERGRID', (0,0), (-1,-1), 0.3, BORDER),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER),
        ]
        if headers:
            style_cmds.append(('BACKGROUND', (0,0), (-1,0), BLACK))
            style_cmds.append(('BACKGROUND', (0,1), (-1,-1), LIGHT_GRAY))
        else:
            style_cmds.append(('BACKGROUND', (0,0), (-1,-1), LIGHT_GRAY))
        t.setStyle(TableStyle(style_cmds))
        return t

    def verdict_box(text, verdict_type='warning'):
        """Create a colored verdict/insight box."""
        bg_map = {'critical': colors.HexColor("#FDEDEC"), 'warning': colors.HexColor("#FEF9E7"),
                  'positive': colors.HexColor("#EAFAF1"), 'info': colors.HexColor("#EBF5FB")}
        border_map = {'critical': DEEP_RED, 'warning': AMBER, 'positive': GREEN_OK, 'info': colors.HexColor("#3498DB")}
        bg = bg_map.get(verdict_type, bg_map['info'])
        border = border_map.get(verdict_type, border_map['info'])
        label_map = {'critical': 'CRITICAL', 'warning': 'ATTENTION', 'positive': 'STRENGTH', 'info': 'INSIGHT'}
        lbl = label_map.get(verdict_type, 'INSIGHT')
        lbl_style = ParagraphStyle('VL', fontName='Helvetica-Bold', fontSize=7, textColor=border, spaceAfter=3)
        txt_style = ParagraphStyle('VT', fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=14)
        rows = [[Paragraph(lbl, lbl_style)], [Paragraph(_format_bold(cl(text)), txt_style)]]
        t = Table(rows, colWidths=[W])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('BOX', (0,0), (-1,-1), 0.5, border),
            ('LINEBEFORE', (0,0), (0,-1), 3, border),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    # ── Extract scraped data ──
    brand_ig = scraped_data.get('brand_instagram', {})
    category = scraped_data.get('category_data', {})
    cat_bench = category.get('category_benchmarks', {}) if isinstance(category, dict) else {}
    cat_avg_er = cat_bench.get('avg_engagement_rate', 0)

    # Count sources
    platforms_scraped = [k for k, v in scraped_data.items() if isinstance(v, dict) and not v.get('error')]
    competitors_scraped = [k for k in platforms_scraped if k.startswith('competitor_')]
    total_posts = brand_ig.get('recent_posts_count', 0)
    cat_posts = cat_bench.get('total_posts_analyzed', 0)
    cat_accounts = category.get('accounts_after_filter', 0) if isinstance(category, dict) else 0

    # ════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ════════════════════════════════════════════════════════════════════
    cover_rows = [
        [Paragraph("SOCIAL MEDIA BRAND INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
        [Spacer(1, 16*mm)],
        [Paragraph(cl(brand_name.upper()), S['cover_brand'])],
        [Spacer(1, 3*mm)],
        [Paragraph(cl(brand_category), S['cover_sub'])],
        [Spacer(1, 2*mm)],
        [Paragraph(f"Market: {target_market}  |  {today}  |  Version 4.0", S['cover_label'])],
        [Spacer(1, 5*mm)],
        [Paragraph(f"Based on {total_posts + cat_posts} posts from {len(competitors_scraped) + cat_accounts} accounts",
            ParagraphStyle('DS', fontName='Helvetica', fontSize=8, textColor=GREEN_OK, alignment=TA_CENTER))],
        [Spacer(1, 4*mm)],
        [HRFlowable(width=60*mm, thickness=0.5, color=ACCENT)],
        [Spacer(1, 5*mm)],
        [Paragraph("Multi-Platform Intelligence Report with Category Benchmarks",
            ParagraphStyle('CV', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#CCCCCC"), alignment=TA_CENTER))],
        [Spacer(1, 12*mm)],
        [Paragraph("OffGrid Creatives AI", S['cover_og'])],
        [Paragraph("offgridcreativesai@gmail.com", S['cover_label'])],
        [Spacer(1, 6*mm)],
        [Paragraph(LEGAL, ParagraphStyle('DL', fontName='Helvetica', fontSize=6.5,
            textColor=colors.HexColor("#888888"), alignment=TA_CENTER, leading=9))],
    ]
    ct = Table(cover_rows, colWidths=[W])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BLACK),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story += [Spacer(1, 25*mm), ct, PageBreak()]

    # ════════════════════════════════════════════════════════════════════
    # EXECUTIVE SCORECARD PAGE
    # ════════════════════════════════════════════════════════════════════
    story += [Paragraph("EXECUTIVE SCORECARD", ParagraphStyle('ES', fontName='Helvetica-Bold', fontSize=14,
        textColor=BLACK, spaceAfter=4)),
        HRFlowable(width="100%", thickness=2, color=ACCENT), Spacer(1, 6*mm)]

    if brand_ig and not brand_ig.get('error'):
        brand_er = brand_ig.get('avg_er_pct', 0)
        brand_er_color = score_color(brand_er, cat_avg_er) if cat_avg_er else ACCENT

        # Top metric cards row
        card_row = Table([[
            metric_card(f"{brand_ig.get('followers', 0):,}", "FOLLOWERS", "Your Instagram", LIGHT_GRAY, ACCENT),
            metric_card(f"{brand_er}%", "ENGAGEMENT RATE",
                f"Category avg: {cat_avg_er}%" if cat_avg_er else "", LIGHT_GRAY, brand_er_color),
            metric_card(f"{brand_ig.get('recent_posts_count', 0)}", "POSTS ANALYZED", "Live scraped data", LIGHT_GRAY, ACCENT),
        ]], colWidths=[W/3, W/3, W/3])
        card_row.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story += [card_row, Spacer(1, 5*mm)]

        # Posting frequency + format
        freq = brand_ig.get('posting_frequency_per_week')
        freq_text = f"{freq} posts/week" if freq else "N/A"
        fmt = brand_ig.get('format_breakdown', {})
        fmt_str = " | ".join([f"{k}: {v}" for k, v in fmt.items()]) if fmt else "N/A"
        avg_views = brand_ig.get('avg_video_views', 0)
        views_text = f"{avg_views:,} avg views/reel" if avg_views else "No Reels data"
        story += [kv_table([
            ("POSTING FREQUENCY", freq_text),
            ("FORMAT BREAKDOWN", fmt_str),
            ("REELS PERFORMANCE", views_text),
            ("AVG CAPTION LENGTH", f"{brand_ig.get('avg_caption_length', 0)} chars"),
            ("BIO", brand_ig.get('bio', 'N/A')[:150]),
        ]), Spacer(1, 5*mm)]

    # ── CATEGORY LEADERBOARD: Rank the brand against the entire niche ──
    # Collect ALL accounts: brand + user-submitted competitors + category leaders + category top accounts
    leaderboard = []

    # Add brand
    if brand_ig and not brand_ig.get('error'):
        leaderboard.append({
            'handle': brand_ig.get('handle', '?'),
            'followers': brand_ig.get('followers', 0),
            'avg_likes': brand_ig.get('avg_likes', 0),
            'avg_er_pct': brand_ig.get('avg_er_pct', 0),
            'fmt': brand_ig.get('format_breakdown', {}),
            'label': 'YOU',
            'source': 'brand',
        })

    # Add user-submitted competitors + auto-discovered category leaders (full profile data)
    for key in sorted(scraped_data.keys()):
        is_comp = key.startswith('competitor_') and key.endswith('_instagram')
        is_leader = key.startswith('category_leader_') and key.endswith('_instagram')
        if (is_comp or is_leader) and isinstance(scraped_data[key], dict) and not scraped_data[key].get('error'):
            cd = scraped_data[key]
            if cd.get('followers', 0) == 0 and cd.get('avg_likes', 0) == 0:
                continue  # Skip empty profiles
            leaderboard.append({
                'handle': cd.get('handle', '?'),
                'followers': cd.get('followers', 0),
                'avg_likes': cd.get('avg_likes', 0),
                'avg_er_pct': cd.get('avg_er_pct', 0),
                'fmt': cd.get('format_breakdown', {}),
                'label': 'LEADER' if is_leader else 'COMP',
                'source': 'leader' if is_leader else 'competitor',
            })

    # Add remaining category top accounts (from hashtag data — lighter stats but broadens the picture)
    cat_data = scraped_data.get('category_data')
    already_in = {a['handle'].lower() for a in leaderboard}
    if isinstance(cat_data, dict) and not cat_data.get('error'):
        for acc in cat_data.get('top_accounts', []):
            handle = (acc.get('handle') or '').lower()
            if handle and handle not in already_in and acc.get('followers', 0) >= 500:
                # Get dominant format from breakdown
                fmt = acc.get('format_breakdown', {})
                leaderboard.append({
                    'handle': acc.get('handle', '?'),
                    'followers': acc.get('followers', 0),
                    'avg_likes': acc.get('avg_likes', 0),
                    'avg_er_pct': acc.get('avg_er_pct', 0),
                    'fmt': fmt,
                    'label': '',
                    'source': 'category',
                })
                already_in.add(handle)

    # Sort by engagement rate (descending) and find brand's rank
    leaderboard.sort(key=lambda x: x['avg_er_pct'], reverse=True)
    brand_rank = None
    for idx, acc in enumerate(leaderboard, 1):
        if acc['source'] == 'brand':
            brand_rank = idx
            break

    if leaderboard:
        rank_text = f"Your brand ranks #{brand_rank} out of {len(leaderboard)} accounts in this category" if brand_rank else ""
        story += [Paragraph("CATEGORY LEADERBOARD", SUBHEAD_STYLE)]
        if rank_text:
            story += [Paragraph(rank_text, ParagraphStyle('RankText', fontName='Helvetica-Bold', fontSize=9,
                textColor=colors.HexColor('#CC3333') if brand_rank and brand_rank > len(leaderboard) * 0.5 else colors.HexColor('#228B22'),
                spaceAfter=4))]

        lb_rows = []
        for idx, acc in enumerate(leaderboard, 1):
            handle_display = f"@{acc['handle']}"
            if acc['label'] == 'YOU':
                handle_display += " (YOU)"
            elif acc['label'] == 'COMP':
                handle_display += " *"
            elif acc['label'] == 'LEADER':
                handle_display += " ★"
            # Dominant format
            fmt = acc.get('fmt', {})
            top_fmt = max(fmt, key=fmt.get) if fmt else "—"
            lb_rows.append([
                str(idx),
                handle_display,
                f"{acc['followers']:,}",
                f"{acc['avg_likes']}",
                f"{acc['avg_er_pct']}%",
                top_fmt,
            ])
        story += [comparison_table(lb_rows, ["#", "ACCOUNT", "FOLLOWERS", "AVG LIKES", "ENG. RATE", "TOP FORMAT"]),
                  Spacer(1, 2*mm),
                  Paragraph("★ = Auto-discovered category leader  |  * = Your submitted competitor", ParagraphStyle(
                      'LegendStyle', fontName='Helvetica', fontSize=6, textColor=LIGHT_GRAY)),
                  Spacer(1, 5*mm)]

    # ── Category Benchmarks Summary ──
    if cat_bench:
        story += [Paragraph("CATEGORY BENCHMARKS", SUBHEAD_STYLE)]
        cat_fmt = cat_bench.get('dominant_formats', {})
        cat_fmt_str = " | ".join([f"{k}: {v}%" for k, v in cat_fmt.items()]) if cat_fmt else "N/A"
        story += [kv_table([
            ("CATEGORY AVG ENGAGEMENT", f"{cat_avg_er}%"),
            ("MEDIAN FOLLOWERS", f"{cat_bench.get('median_followers', 0):,}"),
            ("DOMINANT FORMATS", cat_fmt_str),
            ("POSTS ANALYZED", str(cat_bench.get('total_posts_analyzed', 0))),
            ("ACCOUNTS IN LEADERBOARD", str(len(leaderboard))),
        ]), Spacer(1, 5*mm)]

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CONTENT SECTIONS (from Claude analysis)
    # ════════════════════════════════════════════════════════════════════
    section_keys = [
        'category_landscape', 'competitor_success_blueprint', 'brand_positioning',
        'hook_format_intelligence', 'audience_intelligence', 'organic_to_paid_bridge',
        'content_execution_plan', 'what_to_stop', 'priority_action_plan', 'emerging_signals',
        'platform_expansion',
    ]

    for i, key in enumerate(section_keys, 1):
        section = report_data.get(key, {})
        if isinstance(section, str):
            section = {'title': key.replace('_', ' ').title(), 'content': section}
        if not isinstance(section, dict):
            continue
        title = section.get('title', key.replace('_', ' ').title())
        content = section.get('content', '')
        verdict = section.get('verdict', '')
        verdict_type = section.get('verdict_type', 'info')

        # Section header
        story += [Spacer(1, 4*mm),
            Paragraph(f"SECTION {i:02d}", S['sec_num']),
            Paragraph(cl(title), ParagraphStyle('ST2', fontName='Helvetica-Bold', fontSize=15,
                textColor=BLACK, spaceAfter=4)),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT),
            Spacer(1, 4*mm)]

        # Verdict box at top if provided
        if verdict and verdict.strip() not in ('', 'N/A', 'null', 'none'):
            story += [verdict_box(verdict, verdict_type), Spacer(1, 4*mm)]

        if not content or content.strip() in ('', 'N/A', 'null', 'none'):
            story.append(Paragraph("Data not available for this section.", CONTENT_STYLE))
            story.append(Spacer(1, 4*mm))
            continue

        # Parse content into formatted paragraphs
        paragraphs = content.split('\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # Sub-headers (lines starting with ##)
            if para.startswith('## '):
                story.append(Paragraph(_format_bold(cl(para[3:])), SUBHEAD_STYLE))
            elif para.startswith('### '):
                story.append(Paragraph(_format_bold(cl(para[4:])),
                    ParagraphStyle('SH3', fontName='Helvetica-Bold', fontSize=9.5,
                        textColor=DARK_GRAY, spaceAfter=3, spaceBefore=6)))
            # Bullet points
            elif para.startswith('- ') or para.startswith('* '):
                bullet_text = _format_bold(cl(para[2:].strip()))
                story.append(Paragraph(f"&bull; {bullet_text}", BULLET_STYLE))
            # Numbered lists (handle 1. through 99.)
            elif len(para) > 2 and para.split('.')[0].strip().isdigit() and para.index('.') < 4:
                dot_idx = para.index('.')
                num = para[:dot_idx]
                bullet_text = _format_bold(cl(para[dot_idx+1:].strip()))
                story.append(Paragraph(f"<b>{num}.</b> {bullet_text}", BULLET_STYLE))
            else:
                formatted = _format_bold(cl(para))
                story.append(Paragraph(formatted, CONTENT_STYLE))

        story.append(Spacer(1, 4*mm))

        # Add page break after every 2-3 sections to avoid overcrowding
        if i in (3, 6, 8, 10):
            story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # TOP POSTS TABLE (from scraped data)
    # ════════════════════════════════════════════════════════════════════
    if brand_ig and not brand_ig.get('error') and brand_ig.get('top_posts'):
        story += [PageBreak(), Paragraph("APPENDIX: TOP PERFORMING POSTS", SUBHEAD_STYLE),
                  HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1, 4*mm)]
        post_rows = []
        for p in brand_ig['top_posts'][:5]:
            cap = (p.get('caption', '') or '')[:100]
            cap = cap.replace('\n', ' ')
            # Use classified format if available, otherwise smart-classify inline
            raw_type = p.get('_classified_format', p.get('type', 'Unknown'))
            if raw_type == 'Sidecar':
                raw_type = 'Carousel'
            elif raw_type == 'Video' or (p.get('videoUrl') and raw_type == 'Image'):
                raw_type = 'Reel' if p.get('productType') == 'clips' or not p.get('productType') else 'Video'
            views = p.get('videoViewCount', 0)
            views_str = f" ({views:,} views)" if views else ""
            post_rows.append([
                raw_type,
                f"{p.get('likesCount', 0):,}{views_str}",
                f"{p.get('commentsCount', 0):,}",
                cl(cap) + "..." if len(cap) >= 100 else cl(cap),
            ])
        story += [comparison_table(post_rows, ["FORMAT", "LIKES", "COMMENTS", "CAPTION"]), Spacer(1, 6*mm)]

    # ════════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════════
    story += [Spacer(1, 8*mm),
        HRFlowable(width="100%", thickness=1, color=ACCENT),
        Spacer(1, 3*mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  offgridcreativesai@gmail.com  |  {today}  |  Confidential  |  Version 4.0", S['footer']),
        Spacer(1, 2*mm),
        Paragraph(LEGAL, ParagraphStyle('FL', fontName='Helvetica', fontSize=6,
            textColor=MID_GRAY, alignment=TA_CENTER, leading=8))]

    doc.build(story)
    logger.info("build_agent_pdf() COMPLETED — Version 4.0")

    with open(tmp.name, 'rb') as f:
        pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
    os.unlink(tmp.name)
    return pdf_b64


def _format_bold(text):
    """Convert **bold** markers to ReportLab <b> tags."""
    import re as _re
    return _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)


# ════════════════════════════════════════════════════════════════════
# AGENT ENDPOINT — Takes form data, scrapes, analyzes, generates PDF
# ════════════════════════════════════════════════════════════════════

@app.route('/agent-report', methods=['POST'])
def agent_report():
    """
    Full agent pipeline V4:
    1. Receive form data (brand details + handles)
    2. Scrape all platforms + category top 25 in parallel via Apify
    3. Send real scraped data to Claude for analysis (11 sections)
    4. Generate branded PDF with visual design
    5. Return base64 PDF
    """
    try:
        body = request.get_json(force=True)
        logger.info(f"[AGENT] V4 request for brand: {body.get('brand_name', 'unknown')}")

        # Step 1: Extract form data
        form_data = {
            'brand_name': body.get('brand_name', ''),
            'brand_category': body.get('brand_category', ''),
            'brand_description': body.get('brand_description', ''),
            'target_market': body.get('target_market', ''),
            'report_type': body.get('report_type', 'Brand Audit + Competitor Research'),
            'instagram_handle': body.get('instagram_handle', ''),
            'youtube_channel': body.get('youtube_channel', ''),
            'linkedin_url': body.get('linkedin_url', ''),
            'tiktok_handle': body.get('tiktok_handle', ''),
            'website_url': body.get('website_url', ''),
            'competitor_handles': [
                body.get('competitor_1', ''),
                body.get('competitor_2', ''),
                body.get('competitor_3', ''),
            ],
            'full_name': body.get('full_name', ''),
            'email': body.get('email', ''),
            'whatsapp': body.get('whatsapp', ''),
        }

        # Step 2: Scrape all platforms + category data in parallel
        logger.info(f"[AGENT] Starting multi-platform + category scrape for {form_data['brand_name']}")
        scraped_data = scrape_all_platforms(form_data)
        logger.info(f"[AGENT] Scraping complete. Sources: {list(scraped_data.keys())}")

        # Step 3: Build Claude prompt with REAL data only
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

        scraped_json = json.dumps(scraped_data, indent=2, default=str)
        # Trim if too large
        if len(scraped_json) > 100000:
            scraped_json = scraped_json[:100000] + "\n... [trimmed for length]"

        # TikTok inclusion depends on market
        target_mkt = (form_data.get('target_market') or '').lower()
        tiktok_note = ""
        if target_mkt in ('india',):
            tiktok_note = "TikTok is BANNED in India. Do NOT recommend TikTok in platform expansion."
        else:
            tiktok_note = "TikTok is available in this market. Include it in platform expansion if relevant."

        system_prompt = f"""You are a senior brand intelligence strategist at OffGrid Creatives AI.
You write brutally honest, data-backed brand audit reports that justify a Rs.6,999 / $179 price tag.
You think like a founder-advisor, not a generic marketing AI. Your advice must motivate the brand owner to take action.

ABSOLUTE RULES — BREAK ANY AND THE REPORT IS WORTHLESS:

1. DATA-FIRST: EVERY paragraph must cite specific numbers from the scraped data. Example: "Your **52,254 followers** generate an average of **14.6 likes** per post — a **0.03% engagement rate**, which is 40x below the category average of **1.2%**."

2. BAN GENERIC: NEVER write these phrases: "post consistently", "engage with your audience", "leverage trends", "increase engagement", "create quality content", "build a community". Instead write: "Post 4x/week (you currently post 1.5x). Focus on Reels — your competitors get **3.2x more engagement** on Reels than static posts."

3. CATEGORY-FIRST COMPARISON: This is a CATEGORY intelligence report, NOT a "you vs one competitor" report. The primary comparison is ALWAYS brand vs the entire category. The scraped data contains:
   - category_data.top_accounts: ranked list of top accounts in this niche with their real stats
   - category_leader_*_instagram: full profile scrapes of the top 3 category leaders (deep data)
   - competitor_*_instagram: user-submitted competitors (secondary reference only)
   Reference at least 5+ category accounts by @handle in every section. Show where the brand ranks among ALL accounts, not just named competitors.

4. NO FABRICATION: Only use numbers from the scraped data. If data is missing, say: "[Data point] not available."

5. MOTIVATE THE OWNER: End sections with what winning looks like. "If you match the category leaders' posting frequency, at your current follower base, you could expect roughly **X likes per post** based on category ER benchmarks."

6. USE ALL DATA SOURCES: The scraped data includes category_data (top 25 accounts from hashtag scraping), category_leader profiles (full scrapes of top 3), and user-submitted competitors. Weave ALL of them into your analysis. Name specific accounts by @handle with their real numbers. The category leaders are your PRIMARY examples of what winning looks like — they were auto-discovered from real hashtag data, not hand-picked by the user.

7. SPECIFICITY: When recommending content, describe the exact hook, format, and topic. Not "create educational content" but "Create a 15-second Reel with a curiosity hook like 'The one thing nobody tells you about [topic]' — this hook type achieves **2.8x avg engagement** in your category."

8. EACH SECTION: 200-400 words. Write paragraphs, not walls of text. Use line breaks. Use bullet points for action items only.

{tiktok_note}

FORMAT:
- Use **text** for bold (key numbers, handles, verdicts)
- Use - for bullet point lists (action items only)
- Use ## for sub-headers within sections
- Use line breaks between paragraphs

Return a JSON object with exactly 11 sections. Each section has:
- "title" (string) — section title
- "content" (string) — full multi-paragraph analysis
- "verdict" (string) — one-sentence key takeaway for this section
- "verdict_type" (string) — one of: "critical", "warning", "positive", "info"

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

PLATFORM EXPANSION SECTION RULES:
- Only recommend platforms the brand is NOT already on
- If they have no YouTube, explain what YouTube content works in their category with real examples
- If they have no LinkedIn, explain the B2B or thought-leadership angle
- If they have a weak website, give specific improvement points from the website audit data
- Each platform recommendation must include: WHY, WHAT content type, HOW OFTEN, EXPECTED IMPACT
- {tiktok_note}

Return ONLY valid JSON. No markdown fences. No preamble. Start with {{ end with }}."""

        user_prompt = f"""BRAND: {form_data['brand_name']}
CATEGORY: {form_data['brand_category']}
DESCRIPTION: {form_data['brand_description']}
TARGET MARKET: {form_data['target_market']}
REPORT TYPE: {form_data['report_type']}

=== REAL SCRAPED DATA (scraped live via Apify right now — NOT cached, NOT estimated) ===

{scraped_json}

=== END OF SCRAPED DATA ===

INSTRUCTIONS:
1. This is a CATEGORY intelligence report. The scraped data includes: brand profile, category_data (top 25 accounts from hashtag scraping), category_leader_*_instagram (full profile scrapes of top 3 leaders), and competitor_*_instagram (user-submitted competitors)
2. CATEGORY LEADERS are your PRIMARY comparison — these are the top accounts auto-discovered from real hashtag data. Reference them by @handle throughout
3. The category_data.category_benchmarks gives you the real category averages — use these as benchmarks
4. The category_data.top_accounts array has the top 25 performers — reference at least 5+ by handle across the report
5. Compare: brand ER vs category leader ERs vs category avg ER vs user-submitted competitors (in that order of importance)
6. Every recommendation must have a data-backed reason from a REAL account doing it successfully
7. Minimum 200 words per section — this is a premium report
8. Write like a strategist talking to a founder who needs to understand WHERE THEY RANK in the whole category
9. The platform_expansion section should recommend channels the brand is NOT on yet
10. User-submitted competitors are secondary — they may have empty data. Focus on what the CATEGORY data reveals"""

        logger.info(f"[AGENT] Sending {len(scraped_json)} chars of scraped data to Claude")

        claude_response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=16000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        response_text = claude_response.content[0].text
        logger.info(f"[AGENT] Claude response received: {len(response_text)} chars")

        # Parse Claude's JSON response
        response_text = escape_literal_newlines_in_strings(response_text)
        response_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', response_text)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group()
        report_data = json.loads(response_text)

        # Step 4: Generate PDF using V4 agent PDF builder
        logger.info(f"[AGENT] Generating V4 PDF for {form_data['brand_name']}")
        pdf_base64 = build_agent_pdf(report_data, form_data, scraped_data)

        return jsonify({
            'status': 'success',
            'brand': form_data['brand_name'],
            'platforms_scraped': list(scraped_data.keys()),
            'sections': len(report_data),
            'pdf_base64': pdf_base64,
            'scraped_summary': {
                k: {
                    'platform': v.get('platform', '') if isinstance(v, dict) else '',
                    'followers': v.get('followers', '') if isinstance(v, dict) else '',
                    'avg_er_pct': v.get('avg_er_pct', '') if isinstance(v, dict) else '',
                    'error': v.get('error', '') if isinstance(v, dict) else '',
                } for k, v in scraped_data.items() if isinstance(v, dict)
            }
        }), 200

    except Exception as e:
        logger.error(f"[AGENT] Error: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/agent-scrape-only', methods=['POST'])
def agent_scrape_only():
    """Scrape all platforms and return raw data — for frontend live preview."""
    try:
        body = request.get_json(force=True)
        form_data = {
            'brand_name': body.get('brand_name', ''),
            'instagram_handle': body.get('instagram_handle', ''),
            'youtube_channel': body.get('youtube_channel', ''),
            'linkedin_url': body.get('linkedin_url', ''),
            'tiktok_handle': body.get('tiktok_handle', ''),
            'website_url': body.get('website_url', ''),
            'competitor_handles': [
                body.get('competitor_1', ''),
                body.get('competitor_2', ''),
                body.get('competitor_3', ''),
            ],
        }
        scraped_data = scrape_all_platforms(form_data)
        return jsonify({'status': 'success', 'data': scraped_data}), 200
    except Exception as e:
        logger.error(f"[AGENT-SCRAPE] Error: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ════════════════════════════════════════════════════════════════════
# RAZORPAY PAYMENT INTEGRATION
# ════════════════════════════════════════════════════════════════════

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_placeholder')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

# Pricing in paise (1 INR = 100 paise)
PRICING = {
    'early_access': 250000,   # Rs. 2,500
    'standard': 699900,       # Rs. 6,999
    'agency': 2400000,        # Rs. 24,000
}


@app.route('/create-order', methods=['POST'])
def create_order():
    """Create a Razorpay order for payment."""
    try:
        body = request.get_json(force=True)
        plan = body.get('plan', 'standard')
        amount = PRICING.get(plan, PRICING['standard'])

        if not RAZORPAY_KEY_SECRET:
            return jsonify({'status': 'error', 'message': 'Razorpay not configured'}), 500

        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        order = client.order.create({
            'amount': amount,
            'currency': 'INR',
            'receipt': f'offgrid_{uuid.uuid4().hex[:12]}',
            'notes': {
                'brand_name': body.get('brand_name', ''),
                'email': body.get('email', ''),
                'plan': plan,
            }
        })

        return jsonify({
            'status': 'success',
            'order_id': order['id'],
            'amount': amount,
            'currency': 'INR',
            'key_id': RAZORPAY_KEY_ID,
        }), 200

    except Exception as e:
        logger.error(f"[RAZORPAY] Create order error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    """Verify Razorpay payment signature."""
    try:
        body = request.get_json(force=True)
        razorpay_order_id = body.get('razorpay_order_id', '')
        razorpay_payment_id = body.get('razorpay_payment_id', '')
        razorpay_signature = body.get('razorpay_signature', '')

        if not RAZORPAY_KEY_SECRET:
            return jsonify({'status': 'error', 'message': 'Razorpay not configured'}), 500

        # Verify signature
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if expected_signature != razorpay_signature:
            return jsonify({'status': 'error', 'message': 'Invalid payment signature'}), 400

        return jsonify({
            'status': 'success',
            'payment_id': razorpay_payment_id,
            'verified': True,
        }), 200

    except Exception as e:
        logger.error(f"[RAZORPAY] Verify error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ════════════════════════════════════════════════════════════════════
# ASYNC AGENT PIPELINE WITH SSE PROGRESS
# ════════════════════════════════════════════════════════════════════

# In-memory job store (works for single-worker Railway deployment)
agent_jobs = {}


def emit_progress(job_id, step, message, status='active', data=None):
    """Update job progress store."""
    if job_id not in agent_jobs:
        agent_jobs[job_id] = {'steps': [], 'status': 'running', 'result': None}
    agent_jobs[job_id]['steps'].append({
        'step': step,
        'message': message,
        'status': status,
        'data': data,
        'timestamp': datetime.now().isoformat(),
    })
    logger.info(f"[JOB {job_id}] Step {step}: {message}")


def run_agent_pipeline(job_id, form_data):
    """Run the full agent pipeline in a background thread with progress updates."""
    try:
        agent_jobs[job_id] = {'steps': [], 'status': 'running', 'result': None}

        emit_progress(job_id, 1, f"Receiving form data: {form_data['brand_name']} — {form_data['brand_category']}, {form_data['target_market']}", 'done')

        # Step 2: Scrape all platforms
        emit_progress(job_id, 2, f"Starting multi-platform scrape for @{form_data.get('instagram_handle', '').lstrip('@')}", 'active')

        scraped_data = {}
        tasks = {}

        with ThreadPoolExecutor(max_workers=7) as executor:
            if form_data.get('instagram_handle'):
                tasks['brand_instagram'] = executor.submit(scrape_instagram, form_data['instagram_handle'], 30)
                emit_progress(job_id, 3, f"Scraping brand profile: @{form_data['instagram_handle'].lstrip('@')}", 'active')

            if form_data.get('website_url'):
                tasks['brand_website'] = executor.submit(scrape_website, form_data['website_url'])

            for i, comp_handle in enumerate(form_data.get('competitor_handles', []), 1):
                if comp_handle and comp_handle.strip():
                    tasks[f'competitor_{i}_instagram'] = executor.submit(scrape_instagram, comp_handle, 20)
                    emit_progress(job_id, 3 + i, f"Scraping competitor: @{comp_handle.strip().lstrip('@')}", 'active')

            if form_data.get('brand_category'):
                tasks['category_data'] = executor.submit(
                    scrape_category_top_accounts, form_data['brand_category'], 25
                )
                emit_progress(job_id, 7, f"Scraping category hashtags for {form_data['brand_category']}", 'active')

            if form_data.get('youtube_channel'):
                tasks['brand_youtube'] = executor.submit(scrape_youtube, form_data['youtube_channel'])
            if form_data.get('linkedin_url'):
                tasks['brand_linkedin'] = executor.submit(scrape_linkedin, form_data['linkedin_url'])

            for key, future in tasks.items():
                try:
                    result = future.result(timeout=240)
                    if result is not None:
                        scraped_data[key] = result
                        # Emit progress for completed scrapes
                        if key == 'brand_instagram' and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 8, f"Brand profile scraped: {result.get('followers', 0):,} followers, {result.get('post_count', 0)} posts, {result.get('avg_er_pct', 0)}% ER", 'done',
                                          {'type': 'brand_data', 'followers': result.get('followers', 0), 'posts': result.get('post_count', 0), 'er': result.get('avg_er_pct', 0), 'handle': result.get('handle', '')})
                        elif key.startswith('competitor_') and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 9, f"Competitor scraped: @{result.get('handle', '')} — {result.get('followers', 0):,} followers, {result.get('avg_er_pct', 0)}% ER", 'done',
                                          {'type': 'competitor_data', 'handle': result.get('handle', ''), 'followers': result.get('followers', 0), 'er': result.get('avg_er_pct', 0)})
                        elif key == 'category_data' and isinstance(result, dict) and not result.get('error'):
                            n_accounts = len(result.get('top_accounts', []))
                            emit_progress(job_id, 10, f"Category scraped: {n_accounts} accounts found from hashtag data", 'done',
                                          {'type': 'category_data', 'accounts_found': n_accounts, 'benchmarks': result.get('category_benchmarks', {})})
                        elif key == 'brand_website' and isinstance(result, dict) and not result.get('error'):
                            emit_progress(job_id, 11, f"Website audited: {form_data.get('website_url', '')}", 'done')
                        else:
                            emit_progress(job_id, 11, f"Scraped: {key}", 'done')
                except Exception as e:
                    scraped_data[key] = {'error': str(e)}
                    emit_progress(job_id, 11, f"Failed: {key} — {str(e)}", 'done')

        # Phase 2: Auto-scrape category leaders
        cat_data = scraped_data.get('category_data')
        if isinstance(cat_data, dict) and not cat_data.get('error'):
            top_accounts = cat_data.get('top_accounts', [])
            already_scraped = set()
            brand_handle = (form_data.get('instagram_handle') or '').lstrip('@').strip().lower()
            if brand_handle:
                already_scraped.add(brand_handle)
            for ch in form_data.get('competitor_handles', []):
                if ch and ch.strip():
                    already_scraped.add(ch.strip().lstrip('@').lower())

            leaders_to_scrape = []
            for acc in top_accounts:
                handle = (acc.get('handle') or '').lower()
                if handle and handle not in already_scraped and acc.get('followers', 0) >= 1000:
                    leaders_to_scrape.append(handle)
                if len(leaders_to_scrape) >= 3:
                    break

            if leaders_to_scrape:
                emit_progress(job_id, 12, f"Auto-scraping top {len(leaders_to_scrape)} category leaders: {', '.join(['@' + h for h in leaders_to_scrape])}", 'active')
                with ThreadPoolExecutor(max_workers=3) as executor2:
                    leader_tasks = {}
                    for i, lh in enumerate(leaders_to_scrape, 1):
                        leader_tasks[f'category_leader_{i}_instagram'] = executor2.submit(scrape_instagram, lh, 20)
                    for key, future in leader_tasks.items():
                        try:
                            result = future.result(timeout=120)
                            if result is not None and not result.get('error'):
                                scraped_data[key] = result
                                emit_progress(job_id, 13, f"Category leader scraped: @{result.get('handle', '')} — {result.get('followers', 0):,} followers", 'done')
                        except Exception as e:
                            logger.warning(f"[SCRAPE] Category leader {key} failed: {e}")

        emit_progress(job_id, 14, "All scraping complete. Starting AI analysis...", 'done')

        # Step 3: Claude analysis
        emit_progress(job_id, 15, "Sending scraped data to Claude Opus for 11-section deep analysis...", 'active')

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

        scraped_json = json.dumps(scraped_data, indent=2, default=str)
        if len(scraped_json) > 100000:
            scraped_json = scraped_json[:100000] + "\n... [trimmed for length]"

        target_mkt = (form_data.get('target_market') or '').lower()
        tiktok_note = "TikTok is BANNED in India. Do NOT recommend TikTok in platform expansion." if target_mkt in ('india',) else "TikTok is available in this market. Include it in platform expansion if relevant."

        system_prompt = f"""You are a senior brand intelligence strategist at OffGrid Creatives AI.
You write brutally honest, data-backed brand audit reports that justify a Rs.6,999 / $179 price tag.
You think like a founder-advisor, not a generic marketing AI. Your advice must motivate the brand owner to take action.

ABSOLUTE RULES — BREAK ANY AND THE REPORT IS WORTHLESS:

1. DATA-FIRST: EVERY paragraph must cite specific numbers from the scraped data.
2. BAN GENERIC: NEVER write these phrases: "post consistently", "engage with your audience", "leverage trends", "increase engagement", "create quality content", "build a community".
3. CATEGORY-FIRST COMPARISON: This is a CATEGORY intelligence report. Primary comparison is brand vs entire category.
4. NO FABRICATION: Only use numbers from the scraped data. If data is missing, say: "[Data point] not available."
5. MOTIVATE THE OWNER: End sections with what winning looks like.
6. USE ALL DATA SOURCES: Weave category_data, category leaders, and competitors into analysis.
7. SPECIFICITY: Describe exact hooks, formats, and topics in recommendations.
8. EACH SECTION: 200-400 words.

{tiktok_note}

FORMAT: Use **text** for bold, - for bullets, ## for sub-headers, line breaks between paragraphs.

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

Return ONLY valid JSON. No markdown fences. No preamble. Start with {{ end with }}."""

        user_prompt = f"""BRAND: {form_data['brand_name']}
CATEGORY: {form_data['brand_category']}
DESCRIPTION: {form_data['brand_description']}
TARGET MARKET: {form_data['target_market']}
REPORT TYPE: {form_data['report_type']}

=== REAL SCRAPED DATA ===
{scraped_json}
=== END ===

INSTRUCTIONS: Category-first comparison. Reference 5+ accounts by @handle. Minimum 200 words per section."""

        claude_response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=16000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        response_text = claude_response.content[0].text
        emit_progress(job_id, 16, f"Claude analysis complete: {len(response_text):,} characters of intelligence", 'done')

        # Parse response
        response_text = escape_literal_newlines_in_strings(response_text)
        response_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', response_text)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group()
        report_data = json.loads(response_text)

        emit_progress(job_id, 17, f"Parsed {len(report_data)} report sections. Generating PDF...", 'active')

        # Step 4: Generate PDF
        pdf_base64 = build_agent_pdf(report_data, form_data, scraped_data)
        emit_progress(job_id, 18, "Branded PDF generated successfully!", 'done')

        # Step 5: Send via email (Gmail via Make.com webhook or direct)
        emit_progress(job_id, 19, f"Report ready! Delivering to {form_data.get('email', 'client')}", 'done')

        agent_jobs[job_id]['status'] = 'completed'
        agent_jobs[job_id]['result'] = {
            'pdf_base64': pdf_base64,
            'brand': form_data['brand_name'],
            'sections': len(report_data),
            'platforms_scraped': list(scraped_data.keys()),
        }

    except Exception as e:
        logger.error(f"[JOB {job_id}] Pipeline error: {traceback.format_exc()}")
        emit_progress(job_id, 99, f"Error: {str(e)}", 'error')
        agent_jobs[job_id]['status'] = 'failed'
        agent_jobs[job_id]['result'] = {'error': str(e)}


@app.route('/agent-report-async', methods=['POST'])
def agent_report_async():
    """Start the agent pipeline asynchronously. Returns a job_id for SSE tracking."""
    try:
        body = request.get_json(force=True)
        job_id = uuid.uuid4().hex[:16]

        form_data = {
            'brand_name': body.get('brandName', body.get('brand_name', '')),
            'brand_category': body.get('category', body.get('brand_category', '')),
            'brand_description': body.get('brandDescription', body.get('brand_description', '')),
            'target_market': body.get('targetMarket', body.get('target_market', '')),
            'report_type': body.get('reportType', body.get('report_type', 'Brand Audit + Competitor Research')),
            'instagram_handle': body.get('instagramHandle', body.get('instagram_handle', '')),
            'youtube_channel': body.get('youtubeChannel', body.get('youtube_channel', '')),
            'linkedin_url': body.get('linkedinUrl', body.get('linkedin_url', '')),
            'tiktok_handle': body.get('tiktokHandle', body.get('tiktok_handle', '')),
            'website_url': body.get('websiteUrl', body.get('website_url', '')),
            'competitor_handles': [
                body.get('competitor1', body.get('competitor_1', '')),
                body.get('competitor2', body.get('competitor_2', '')),
                body.get('competitor3', body.get('competitor_3', '')),
            ],
            'full_name': body.get('fullName', body.get('full_name', '')),
            'email': body.get('email', ''),
            'whatsapp': body.get('whatsapp', ''),
            'payment_id': body.get('payment_id', ''),
        }

        # Clean empty competitor handles
        form_data['competitor_handles'] = [h for h in form_data['competitor_handles'] if h and h.strip()]

        logger.info(f"[AGENT-ASYNC] Starting job {job_id} for brand: {form_data['brand_name']}")
        agent_jobs[job_id] = {'steps': [], 'status': 'starting', 'result': None}

        # Run pipeline in background thread
        thread = threading.Thread(target=run_agent_pipeline, args=(job_id, form_data), daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'job_id': job_id,
            'message': f'Agent pipeline started for {form_data["brand_name"]}',
        }), 200

    except Exception as e:
        logger.error(f"[AGENT-ASYNC] Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/agent-status/<job_id>', methods=['GET'])
def agent_status_sse(job_id):
    """SSE endpoint to stream real-time agent progress."""
    def generate():
        last_index = 0
        while True:
            job = agent_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            # Send any new steps
            steps = job.get('steps', [])
            while last_index < len(steps):
                step = steps[last_index]
                yield f"data: {json.dumps(step)}\n\n"
                last_index += 1

            # Check if job is done
            if job['status'] in ('completed', 'failed'):
                yield f"data: {json.dumps({'type': 'complete', 'status': job['status'], 'result': job.get('result', {})})}\n\n"
                break

            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*',
        }
    )


@app.route('/agent-result/<job_id>', methods=['GET'])
def agent_result(job_id):
    """Get the final result of a completed agent job (including PDF)."""
    job = agent_jobs.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404
    if job['status'] == 'running':
        return jsonify({'status': 'running', 'steps_completed': len(job.get('steps', []))}), 202
    if job['status'] == 'failed':
        return jsonify({'status': 'failed', 'error': job.get('result', {}).get('error', 'Unknown error')}), 500

    return jsonify({
        'status': 'completed',
        'result': job.get('result', {}),
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
