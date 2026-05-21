import json
import re
import os
import tempfile
import base64
import threading
import logging
import traceback
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, send_file, jsonify
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER

app = Flask(__name__)

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

        # Try claude_response key first
        claude_response = body.get('claude_response')
        if claude_response:
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
    brand_name     = body.get('brand_name', 'Brand')
    brand_category = body.get('brand_category', 'D2C Brand')
    brand_market   = body.get('brand_market', 'India')
    email          = body.get('email', '')

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
        body = request.get_json(force=True) or {}
        category = body.get('category', '').strip()
        if not category:
            return jsonify({"error": "category is required"}), 400

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
            "model": "claude-haiku-3-5-20241022",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')

        req = _urlreq.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with _urlreq.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))

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
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
