import json
import re
import os
import tempfile
from flask import Flask, request, send_file, jsonify
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER

app = Flask(__name__)

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

def risk_box(title, content, color=RED_ALERT):
    W = 170*mm
    rs = ParagraphStyle('RS', fontName='Helvetica-Bold', fontSize=9, textColor=color)
    t = Table([[Paragraph(cl(title), rs), Paragraph(cl(str(content)), S['body'])]], colWidths=[45*mm,125*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.5,BORDER),
        ('LINEBEFORE',(0,0),(0,-1),3,color),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8)]))
    return t

def build_pdf(data, brand_name, brand_category, brand_market, output_file):
    W = 170*mm
    today = datetime.now().strftime("%B %d, %Y")
    doc = SimpleDocTemplate(output_file, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    story = []

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

    # S1 KEYWORD UNIVERSE
    kw = data.get('keyword_universe', {})
    story += sec_header(1, "Keyword Universe")
    for key, label in [('search_intent_keywords','SEARCH INTENT'),('emotional_trigger_keywords','EMOTIONAL TRIGGERS'),
        ('culture_keywords','CULTURE'),('style_keywords','STYLE'),('seasonal_keywords','SEASONAL')]:
        items = kw.get(key, [])
        if items: story += [tag(label), chip_row(items, 3), Spacer(1,3*mm)]

    # S2 MARKET SATURATION
    ms = data.get('market_saturation', {})
    story += sec_header(2, "Market Saturation")
    for key, label in [('category_maturity','CATEGORY MATURITY'),('content_fatigue','CONTENT FATIGUE'),
        ('pricing_pressure','PRICING PRESSURE'),('differentiation_gaps','DIFFERENTIATION GAPS'),
        ('audience_fragmentation','AUDIENCE FRAGMENTATION')]:
        v = ms.get(key, '')
        if v: story += [tag(label), Paragraph(cl(v), S['body']), Spacer(1,3*mm)]

    # S3 MARKET BENCHMARKS
    mb = data.get('market_benchmarks', {})
    story += sec_header(3, "Market Benchmarks")
    bench_rows = [("CPM RANGE", mb.get('typical_cpm_range','')),("CTR RANGE", mb.get('typical_ctr_range','')),
        ("CVR RANGE", mb.get('typical_cvr_range','')),("CAC RANGE", mb.get('typical_cac_range','')),
        ("AOV RANGE", mb.get('typical_aov_range','')),("ROAS MONTH 1-2", mb.get('average_roas_month1_2','')),
        ("ROAS MONTH 3-4", mb.get('average_roas_month3_4','')),("ROAS MONTH 5-6", mb.get('average_roas_month5_6',''))]
    story += [kv_table(bench_rows), Spacer(1,4*mm)]

    # S4 COMPETITIVE AD INTELLIGENCE
    ci = data.get('competitive_ad_intelligence', {})
    story += sec_header(4, "Competitive Ad Intelligence")
    for comp_name, comp_data in ci.items():
        if not isinstance(comp_data, dict): continue
        story.append(black_hdr(comp_name.upper()))
        rows = [("AD FORMATS", comp_data.get('ad_formats_running','')),
            ("PRIMARY HOOK STYLE", comp_data.get('primary_hook_style','')),
            ("OFFER STRATEGY", comp_data.get('offer_strategy','')),
            ("AUDIENCE TARGETING", comp_data.get('audience_targeting_style','')),
            ("FATIGUE SCORE", f"{comp_data.get('creative_fatigue_score','?')}/10"),
            ("SCALING SIGNALS", comp_data.get('scaling_signals','')),
            ("STRATEGIC GAP", comp_data.get('strategic_gap',''))]
        story += [kv_table(rows, 42*mm), Spacer(1,4*mm)]

    # S5 HOOK INTELLIGENCE
    hi = data.get('hook_intelligence', {})
    story += sec_header(5, "Hook Intelligence")
    for key, label in [('scarcity_hooks','SCARCITY HOOKS'),('social_proof_hooks','SOCIAL PROOF HOOKS'),
        ('problem_agitation_hooks','PROBLEM AGITATION HOOKS'),('curiosity_gap_hooks','CURIOSITY GAP HOOKS'),
        ('direct_response_hooks','DIRECT RESPONSE HOOKS')]:
        hooks = hi.get(key, [])
        if hooks:
            story.append(tag(label))
            for h in hooks: story += [hook_box(h), Spacer(1,2*mm)]
            story.append(Spacer(1,2*mm))
    pnv = hi.get('platform_native_variants', {})
    if pnv:
        story.append(tag("TOP 3 HOOKS BY PREDICTED CTR"))
        for rk, rd in pnv.items():
            if not isinstance(rd, dict): continue
            story.append(black_hdr(f"RANK {rd.get('predicted_ctr_rank','?')} — {cl(rd.get('hook',''))}"))
            rt = Table([[Paragraph(cl(k), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
                [("WHY IT WINS", rd.get('reason','')),("REELS OVERLAY", rd.get('reels_overlay','')),
                 ("FEED STATIC", rd.get('feed_static','')),("CAPTION OPENING", rd.get('caption_opening',''))]],
                colWidths=[38*mm,132*mm])
            rt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
                ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LEFTPADDING',(0,0),(-1,-1),8)]))
            story += [rt, Spacer(1,3*mm)]

    # S6 NARRATIVE LANDSCAPE
    nl = data.get('narrative_landscape', {})
    story += sec_header(6, "Narrative Landscape")
    story.append(tag("COMPETITOR NARRATIVES"))
    for comp, narr in nl.get('competitor_narratives', {}).items():
        story.append(Paragraph(f"<b>{cl(comp.upper())}:</b> {cl(str(narr))}", S['body']))
    story.append(Spacer(1,3*mm))
    if nl.get('market_whitespace'): story += [tag("MARKET WHITESPACE"), Paragraph(cl(nl.get('market_whitespace','')), S['body']), Spacer(1,3*mm)]
    if nl.get('brand_positioning_opportunity'): story += [tag("BRAND POSITIONING OPPORTUNITY"), Paragraph(cl(nl.get('brand_positioning_opportunity','')), S['body']), Spacer(1,3*mm)]
    angles = nl.get('storytelling_angles', [])
    if angles:
        story.append(tag("PLUG-AND-PLAY NARRATIVE SCRIPTS"))
        for i, angle in enumerate(angles, 1): story += [hook_box(f"{i}. {angle}"), Spacer(1,2*mm)]

    # S7 CREATIVE FORMAT
    cf = data.get('creative_format', {})
    story += sec_header(7, "Creative Format Intelligence")
    for key, label in [('top_performing_formats','TOP PERFORMING FORMATS'),('emerging_opportunities','EMERGING OPPORTUNITIES')]:
        items = cf.get(key, [])
        if items:
            story.append(tag(label))
            for item in items: story.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
            story.append(Spacer(1,3*mm))
    if cf.get('format_recommendations'): story += [tag("FORMAT RECOMMENDATION"), Paragraph(cl(cf.get('format_recommendations','')), S['body'])]

    # S8 CREATIVE VOLUME REQUIREMENTS
    cv = data.get('creative_volume_requirements', {})
    story += sec_header(8, "Creative Volume Requirements")
    wv = cv.get('weekly_creative_volume', {})
    fm = cv.get('format_mix', {})
    story += [kv_table([("CREATIVES PER MONTH", cv.get('creatives_per_month','')),
        ("STATIC IMAGES PER WEEK", wv.get('static_images','')),
        ("VIDEO CONCEPTS PER WEEK", wv.get('video_concepts','')),
        ("FORMAT MIX", f"Reels {fm.get('reels_percentage','')}% / Carousel {fm.get('carousel_percentage','')}% / Static {fm.get('static_percentage','')}%"),
        ("REFRESH FREQUENCY", cv.get('refresh_frequency','')),
        ("MIN VIABLE SET FOR ASC", cv.get('minimum_viable_creative_set','')),
        ("PRODUCTION BUDGET", cv.get('creative_production_budget_estimate',''))]), Spacer(1,4*mm)]

    # S9 PLATFORM INTELLIGENCE
    pi = data.get('platform_intelligence', {})
    story += sec_header(9, "Platform Intelligence")
    for key, label in [('facebook_strategy','FACEBOOK STRATEGY'),('instagram_strategy','INSTAGRAM STRATEGY'),
        ('reels_strategy','REELS STRATEGY'),('asc_campaign_structure','ASC CAMPAIGN STRUCTURE'),
        ('budget_allocation','BUDGET ALLOCATION'),('content_calendar','CONTENT CALENDAR')]:
        v = pi.get(key, '')
        if v: story += [tag(label), Paragraph(cl(v), S['body']), Spacer(1,3*mm)]

    # S10 AUDIENCE INTELLIGENCE
    ai_d = data.get('audience_intelligence', {})
    story += sec_header(10, "Audience Intelligence")
    for seg_key, seg_label in [('primary_segment','PRIMARY SEGMENT'),('secondary_segment','SECONDARY SEGMENT')]:
        seg = ai_d.get(seg_key, {})
        if seg:
            story.append(tag(seg_label))
            seg_rows = [(k.replace('_',' ').upper(), ', '.join(v) if isinstance(v,list) else v) for k,v in seg.items()]
            story += [kv_table(seg_rows), Spacer(1,4*mm)]
    geo = ai_d.get('geographic_nuance', {})
    if geo: story += [tag("GEOGRAPHIC NUANCE"), kv_table([(k.replace('_',' ').upper(), v) for k,v in geo.items()]), Spacer(1,4*mm)]

    # S11 OFFER ARCHITECTURE
    oa = data.get('offer_architecture', {})
    story += sec_header(11, "Offer Architecture")
    if oa.get('recommended_price_point'): story += [tag("RECOMMENDED PRICE POINT"), Paragraph(cl(oa.get('recommended_price_point','')), S['body']), Spacer(1,3*mm)]
    if oa.get('first_order_hook'): story += [tag("FIRST ORDER HOOK"), hook_box(oa.get('first_order_hook','')), Spacer(1,3*mm)]
    bundles = oa.get('bundle_strategy', {})
    if bundles:
        story.append(tag("BUNDLE STRATEGY"))
        for k, v in bundles.items(): story.append(Paragraph(f"• <b>{cl(k.upper())}:</b> {cl(v)}", S['bullet']))
        story.append(Spacer(1,3*mm))
    if oa.get('price_justification'): story += [tag("PRICE JUSTIFICATION"), Paragraph(cl(oa.get('price_justification','')), S['body']), Spacer(1,3*mm)]
    if oa.get('discount_guardrails'): story += [tag("DISCOUNT GUARDRAILS"), Paragraph(cl(oa.get('discount_guardrails','')), S['alert']), Spacer(1,3*mm)]

    # S12 UNIT ECONOMICS
    ue = data.get('unit_economics', {})
    story += sec_header(12, "Unit Economics")
    mt = Table([[[Paragraph("TARGET CAC", S['label']), Paragraph(cl(str(ue.get('target_cac',''))), S['metric'])],
        [Paragraph("BREAK-EVEN ROAS", S['label']), Paragraph(cl(str(ue.get('break_even_roas',''))), S['metric'])],
        [Paragraph("RECOMMENDED AOV", S['label']), Paragraph(cl(str(ue.get('recommended_aov',''))), S['metric'])]]], colWidths=[W/3]*3)
    mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLACK),('BOX',(0,0),(-1,-1),1,ACCENT),
        ('INNERGRID',(0,0),(-1,-1),0.5,ACCENT),('TOPPADDING',(0,0),(-1,-1),10),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),10)]))
    story += [mt, Spacer(1,4*mm)]
    roas = ue.get('realistic_roas_timeline', {})
    if roas:
        story.append(tag("REALISTIC ROAS TIMELINE"))
        for k, label in [('month_1_2_expectation','MONTH 1-2'),('month_3_4_expectation','MONTH 3-4'),('month_5_6_expectation','MONTH 5-6')]:
            v = roas.get(k, '')
            if v: story.append(Paragraph(f"<b>{label}:</b> {cl(v)}", S['body']))
        story.append(Spacer(1,3*mm))
    india = ue.get('india_specific_factors', {})
    if india: story += [tag("INDIA-SPECIFIC FACTORS"), kv_table([(k.replace('_',' ').upper(), v) for k,v in india.items()]), Spacer(1,4*mm)]

    # S13 CREATIVE TEST MATRIX
    ctm = data.get('creative_test_matrix', {})
    story += sec_header(13, "Creative Test Matrix")
    story += [kv_table([("TESTING BUDGET", ctm.get('testing_budget_percentage','')),
        ("VALIDATION TIMELINE", ctm.get('validation_timeline','')),
        ("WEEKLY VOLUME DURING TEST", ctm.get('weekly_creative_volume_during_test',''))]), Spacer(1,4*mm)]
    for hyp_key in ['test_hypothesis_1','test_hypothesis_2','test_hypothesis_3']:
        hyp = ctm.get(hyp_key, {})
        if not isinstance(hyp, dict): continue
        story.append(black_hdr(f"HYPOTHESIS {hyp_key.split('_')[-1]} — {cl(hyp.get('hook_angle',''))}"))
        ht = Table([[Paragraph(cl(k), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
            [("FORMAT", hyp.get('ad_format','')),("AUDIENCE", hyp.get('target_audience','')),
             ("BUDGET", hyp.get('budget_allocation_percentage','')),
             ("SUCCESS METRIC", hyp.get('success_metric','')),("KILL CRITERIA", hyp.get('kill_criteria',''))]],
            colWidths=[40*mm, 130*mm])
        ht.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
            ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
            ('LEFTPADDING',(0,0),(-1,-1),8)]))
        story += [ht, Spacer(1,3*mm)]

    # S14 CREATIVE EXECUTION BRIEFS
    ceb = data.get('creative_execution_briefs', {})
    story += sec_header(14, "Creative Execution Briefs")
    story += [Paragraph("5 complete ready-to-shoot briefs. Execute on day one. No questions needed.", S['body']), Spacer(1,4*mm)]
    for brief_key, brief in ceb.items():
        if not isinstance(brief, dict): continue
        story.append(black_hdr(f"BRIEF {brief.get('brief_number','?')} — {cl(brief.get('brief_name',''))}"))
        top_t = Table([[Paragraph(cl(k), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
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
            oh = Table([[Paragraph("ON-SCREEN TEXT — IN ORDER", S['label'])]], colWidths=[W])
            oh.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#1A1A1A")),
                ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),8)]))
            ot = Table([[Paragraph(cl(ost), S['body_bold'])]], colWidths=[W])
            ot.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.5,ACCENT),
                ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),10)]))
            story += [oh, ot]
        story.append(Spacer(1,6*mm))

    # S15 LANDING PAGE INTELLIGENCE
    lp = data.get('landing_page_intelligence', {})
    story += sec_header(15, "Landing Page Intelligence")
    for key, label in [('hero_section_strategy','HERO SECTION STRATEGY'),('offer_placement','OFFER PLACEMENT'),
        ('mobile_optimization_factors','MOBILE OPTIMIZATION — INDIA')]:
        v = lp.get(key, '')
        if v: story += [tag(label), Paragraph(cl(v), S['body']), Spacer(1,3*mm)]
    trust = lp.get('trust_signals_required', [])
    if trust:
        story.append(tag("REQUIRED TRUST SIGNALS"))
        for t_item in trust: story.append(Paragraph(f"• {cl(str(t_item))}", S['bullet']))
        story.append(Spacer(1,3*mm))
    killers = lp.get('conversion_killers', [])
    if killers:
        story.append(tag("CONVERSION KILLERS"))
        for killer in killers: story += [risk_box("KILL", killer), Spacer(1,2*mm)]
    if lp.get('recommended_page_structure'): story += [tag("RECOMMENDED PAGE STRUCTURE"), Paragraph(cl(lp.get('recommended_page_structure','')), S['body'])]

    # S16 LAUNCH RECOMMENDATIONS
    lr = data.get('launch_recommendations', {})
    story += sec_header(16, "Launch Recommendations")
    for phase_key, phase_label, phase_color in [
        ('phase_1','PHASE 1 — DAYS 1-30', GREEN_OK),
        ('phase_2','PHASE 2 — DAYS 31-60', ACCENT),
        ('phase_3','PHASE 3 — DAYS 61-90+', colors.HexColor("#2980B9"))]:
        phase = lr.get(phase_key, {})
        if not isinstance(phase, dict): continue
        story.append(black_hdr(phase_label, phase_color))
        pt = Table([[Paragraph(cl(k), S['label']), Paragraph(cl(str(v)), S['body'])] for k,v in
            [("BUDGET", phase.get('budget','')),("SUCCESS METRICS", phase.get('success_metrics',''))]],
            colWidths=[35*mm, 135*mm])
        pt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT_GRAY),('BOX',(0,0),(-1,-1),0.3,BORDER),
            ('INNERGRID',(0,0),(-1,-1),0.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
            ('LEFTPADDING',(0,0),(-1,-1),8)]))
        story.append(pt)
        for action in phase.get('actions', []): story.append(Paragraph(f"• {cl(str(action))}", S['bullet']))
        story.append(Spacer(1,4*mm))

    # S17 BUDGET DEPLOYMENT
    bd = data.get('budget_deployment', {})
    story += sec_header(17, "Budget Deployment")
    if bd.get('total_monthly_budget'): story += [tag("TOTAL MONTHLY BUDGET"), Paragraph(cl(bd.get('total_monthly_budget','')), S['metric']), Spacer(1,3*mm)]
    for key, label in [('asc_campaign_structure','ASC CAMPAIGN STRUCTURE'),('creative_refresh_cadence','CREATIVE REFRESH CADENCE'),
        ('scaling_triggers','SCALING TRIGGERS'),('scalability_ceiling','SCALABILITY CEILING')]:
        v = bd.get(key, '')
        if v: story += [tag(label), Paragraph(cl(v), S['body']), Spacer(1,3*mm)]
    expected = bd.get('expected_metrics', {})
    if isinstance(expected, dict) and expected:
        story += [tag("EXPECTED METRICS BY MONTH"), kv_table([(k.replace('_',' ').upper(), v) for k,v in expected.items()]), Spacer(1,4*mm)]

    # S18 RISK FACTORS
    rf = data.get('risk_factors', {})
    story += sec_header(18, "Risk Factors")
    for key, label, color in [
        ('competitive_response_risk','COMPETITIVE RESPONSE RISK', MID_GRAY),
        ('creative_fatigue_timeline','CREATIVE FATIGUE TIMELINE', ACCENT),
        ('pricing_war_risk','PRICING WAR RISK', MID_GRAY),
        ('cod_rto_risk','COD / RTO RISK', RED_ALERT),
        ('platform_policy_risk','PLATFORM POLICY RISK', ACCENT),
        ('design_piracy_risk','DESIGN PIRACY RISK', RED_ALERT)]:
        v = rf.get(key, '')
        if v: story += [risk_box(label, v, color), Spacer(1,2*mm)]

    # FOOTER
    story += [Spacer(1,8*mm), HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1,3*mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  offgridcreativesai@gmail.com  |  {today}  |  Confidential  |  Version 3.0", S['footer'])]

    doc.build(story)


@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    try:
        body = request.get_json(force=True)
        if not body:
            return jsonify({"error": "No JSON body received"}), 400

        brand_name     = body.get('brand_name', 'Brand')
        brand_category = body.get('brand_category', 'D2C Brand')
        brand_market   = body.get('brand_market', 'India')

        # Accept either full Claude response object or pre-extracted text
        raw_json = ''
        claude_response = body.get('claude_response', {})
        if claude_response:
            if isinstance(claude_response, dict):
                content = claude_response.get('content', [])
                if content and len(content) > 0:
                    raw_json = content[0].get('text', '')
            elif isinstance(claude_response, str):
                raw_json = claude_response
        
        if not raw_json:
            raw_json = body.get('report_json', '') or body.get('Report_json', '')

        raw_json = re.sub(r'^```json\s*', '', raw_json.strip())
        raw_json = re.sub(r'^```\s*', '', raw_json)
        raw_json = re.sub(r'\s*```$', '', raw_json)

        report_data = json.loads(raw_json)

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            output_path = f.name

        build_pdf(report_data, brand_name, brand_category, brand_market, output_path)

        filename = f"{brand_name.replace(' ', '_')}_AdIntelligenceReport.pdf"
        return send_file(output_path, mimetype='application/pdf',
                         as_attachment=True, download_name=filename)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
