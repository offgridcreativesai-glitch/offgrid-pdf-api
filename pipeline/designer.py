"""
PDF report generator.
Builds branded PDF from Claude's analysis + scraped data using ReportLab.
"""

import os
import tempfile
import base64
import logging
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER

from .pdf_styles import (
    W, BLACK, WHITE, ACCENT, DARK_GRAY, MID_GRAY, LIGHT_GRAY, BORDER, RED_ALERT, GREEN_OK,
    S, cl, format_bold, kv_table,
)

logger = logging.getLogger(__name__)

LEGAL = ("Legal notice: This report is based exclusively on publicly available social media data. "
         "Save rates, reach, impressions, and conversion rates are AI estimates where marked. "
         "No personally identifiable information has been collected or stored. For internal strategic use only.")


def _metric_card(value, label, sub_text='', bg=LIGHT_GRAY, val_color=ACCENT):
    val_style = ParagraphStyle('MV', fontName='Helvetica-Bold', fontSize=18, textColor=val_color, alignment=TA_CENTER)
    metric_label = ParagraphStyle('MLAB', fontName='Helvetica', fontSize=7.5, textColor=MID_GRAY, alignment=TA_CENTER)
    metric_sub = ParagraphStyle('MSUB', fontName='Helvetica', fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER)
    rows = [[Paragraph(cl(str(value)), val_style)], [Paragraph(cl(label), metric_label)]]
    if sub_text:
        rows.append([Paragraph(cl(sub_text), metric_sub)])
    t = Table(rows, colWidths=[W / 3 - 4 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    return t


def _score_color(er_pct, cat_avg=1.0):
    AMBER = colors.HexColor("#F39C12")
    DEEP_RED = colors.HexColor("#E74C3C")
    if er_pct >= cat_avg * 1.5:
        return GREEN_OK
    elif er_pct >= cat_avg * 0.7:
        return AMBER
    return DEEP_RED


def _comparison_table(rows_data, headers=None):
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
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
    ]
    if headers:
        style_cmds.append(('BACKGROUND', (0, 0), (-1, 0), BLACK))
        style_cmds.append(('BACKGROUND', (0, 1), (-1, -1), LIGHT_GRAY))
    else:
        style_cmds.append(('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY))
    t.setStyle(TableStyle(style_cmds))
    return t


def _verdict_box(text, verdict_type='warning'):
    AMBER = colors.HexColor("#F39C12")
    DEEP_RED = colors.HexColor("#E74C3C")
    bg_map = {'critical': colors.HexColor("#FDEDEC"), 'warning': colors.HexColor("#FEF9E7"),
              'positive': colors.HexColor("#EAFAF1"), 'info': colors.HexColor("#EBF5FB")}
    border_map = {'critical': DEEP_RED, 'warning': AMBER, 'positive': GREEN_OK, 'info': colors.HexColor("#3498DB")}
    bg = bg_map.get(verdict_type, bg_map['info'])
    border = border_map.get(verdict_type, border_map['info'])
    label_map = {'critical': 'CRITICAL', 'warning': 'ATTENTION', 'positive': 'STRENGTH', 'info': 'INSIGHT'}
    lbl = label_map.get(verdict_type, 'INSIGHT')
    lbl_style = ParagraphStyle('VL', fontName='Helvetica-Bold', fontSize=7, textColor=border, spaceAfter=3)
    txt_style = ParagraphStyle('VT', fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=14)
    rows = [[Paragraph(lbl, lbl_style)], [Paragraph(format_bold(cl(text)), txt_style)]]
    t = Table(rows, colWidths=[W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('BOX', (0, 0), (-1, -1), 0.5, border),
        ('LINEBEFORE', (0, 0), (0, -1), 3, border),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def build_agent_pdf(report_data, form_data, scraped_data):
    """Build a professional branded PDF from Claude's analysis. Returns base64."""
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    today = datetime.now().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(tmp.name, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story = []

    brand_name = form_data.get('brand_name', 'Brand')
    brand_category = form_data.get('brand_category', '')
    target_market = form_data.get('target_market', '')

    CONTENT_STYLE = ParagraphStyle('CONTENT', fontName='Helvetica', fontSize=9.5,
        textColor=DARK_GRAY, leading=16, spaceAfter=6)
    BULLET_STYLE = ParagraphStyle('CBULLET', fontName='Helvetica', fontSize=9.5,
        textColor=DARK_GRAY, leading=16, spaceAfter=4, leftIndent=14, bulletIndent=0)
    SUBHEAD_STYLE = ParagraphStyle('SUBHEAD', fontName='Helvetica-Bold', fontSize=10.5,
        textColor=colors.HexColor("#222222"), leading=16, spaceAfter=4, spaceBefore=8)

    # ── Extract scraped data ──
    brand_ig = scraped_data.get('brand_instagram', {})
    category = scraped_data.get('category_data', {})
    cat_bench = category.get('category_benchmarks', {}) if isinstance(category, dict) else {}
    cat_avg_er = cat_bench.get('avg_engagement_rate', 0)

    # ════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ════════════════════════════════════════════════════════════════════
    cover_rows = [
        [Paragraph("SOCIAL MEDIA BRAND INTELLIGENCE REPORT", ParagraphStyle('CT', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, alignment=TA_CENTER))],
        [Spacer(1, 20 * mm)],
        [Paragraph(cl(brand_name.upper()), S['cover_brand'])],
        [Spacer(1, 4 * mm)],
        [Paragraph(cl(brand_category), S['cover_sub'])],
        [Spacer(1, 3 * mm)],
        [Paragraph(f"Market: {target_market}  |  {today}  |  Version 6.0", S['cover_label'])],
        [Spacer(1, 8 * mm)],
        [HRFlowable(width=60 * mm, thickness=0.5, color=ACCENT)],
        [Spacer(1, 8 * mm)],
        [Paragraph("Prepared exclusively for your brand by OffGrid Creatives AI",
            ParagraphStyle('CV', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#CCCCCC"), alignment=TA_CENTER))],
        [Spacer(1, 16 * mm)],
        [Paragraph("OffGrid Creatives AI", S['cover_og'])],
        [Paragraph("offgridcreativesai@gmail.com", S['cover_label'])],
        [Spacer(1, 8 * mm)],
        [Paragraph(LEGAL, ParagraphStyle('DL', fontName='Helvetica', fontSize=6.5,
            textColor=colors.HexColor("#666666"), alignment=TA_CENTER, leading=9))],
    ]
    ct = Table(cover_rows, colWidths=[W])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BLACK),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story += [Spacer(1, 25 * mm), ct, PageBreak()]

    # ════════════════════════════════════════════════════════════════════
    # TABLE OF CONTENTS
    # ════════════════════════════════════════════════════════════════════
    TOC_STYLE = ParagraphStyle('TOC', fontName='Helvetica', fontSize=10, textColor=DARK_GRAY, leading=20, spaceAfter=2)
    TOC_NUM = ParagraphStyle('TOCN', fontName='Helvetica-Bold', fontSize=10, textColor=ACCENT, leading=20)
    story += [Paragraph("CONTENTS", ParagraphStyle('TOCH', fontName='Helvetica-Bold', fontSize=16,
        textColor=BLACK, spaceAfter=6)),
        HRFlowable(width="100%", thickness=2, color=ACCENT), Spacer(1, 6 * mm)]

    toc_sections = [
        ("Executive Scorecard", "Your brand at a glance"),
        ("Competitor Comparison", "Side-by-side with your competition"),
        ("Where You Stand Right Now", "Category landscape and positioning"),
        ("Who Is Winning In Your Space and Why", "Competitor deep-dive"),
        ("Your Brand vs The Market Reality", "Honest positioning assessment"),
        ("What Stops The Scroll", "Hook and format intelligence"),
        ("Who Is Actually Watching", "Audience intelligence"),
        ("Content Ready To Become Paid Ads", "Organic-to-paid bridge"),
        ("Your 30-Day Content Playbook", "Execution plan"),
        ("Stop These Immediately", "What to kill"),
        ("5 Priority Actions Ranked By Impact", "Your action plan"),
        ("Trends and Opportunities", "Before they peak"),
        ("New Channels You Should Be On", "Platform expansion"),
    ]
    for idx, (title, subtitle) in enumerate(toc_sections, 1):
        toc_row = Table([
            [Paragraph(f"<b>{idx:02d}</b>", TOC_NUM),
             Paragraph(f"<b>{cl(title)}</b>  <font size='8' color='#888888'>— {cl(subtitle)}</font>", TOC_STYLE)]
        ], colWidths=[12 * mm, W - 12 * mm])
        toc_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(toc_row)

    story += [Spacer(1, 10 * mm),
        Paragraph("This report is built entirely from real Instagram data scraped live on the date above.",
            ParagraphStyle('TOCF', fontName='Helvetica', fontSize=8, textColor=MID_GRAY, alignment=TA_CENTER)),
        PageBreak()]

    # ════════════════════════════════════════════════════════════════════
    # EXECUTIVE SCORECARD PAGE
    # ════════════════════════════════════════════════════════════════════
    story += [Paragraph("EXECUTIVE SCORECARD", ParagraphStyle('ES', fontName='Helvetica-Bold', fontSize=16,
        textColor=BLACK, spaceAfter=4)),
        HRFlowable(width="100%", thickness=2, color=ACCENT), Spacer(1, 6 * mm)]

    if brand_ig and not brand_ig.get('error'):
        brand_er = round(brand_ig.get('avg_er_pct', 0), 1)
        brand_er_color = _score_color(brand_er, cat_avg_er) if cat_avg_er else ACCENT

        freq = brand_ig.get('posting_frequency_per_week')
        freq_text = f"{freq}/week" if freq else "N/A"
        card_row = Table([[
            _metric_card(f"{brand_ig.get('followers', 0):,}", "FOLLOWERS", "Your Instagram", LIGHT_GRAY, ACCENT),
            _metric_card(f"{brand_er}%", "ENGAGEMENT RATE",
                f"Category avg: {round(cat_avg_er, 1)}%" if cat_avg_er else "Calculating...", LIGHT_GRAY, brand_er_color),
            _metric_card(freq_text, "POSTING FREQUENCY", "Posts per week", LIGHT_GRAY, ACCENT),
        ]], colWidths=[W / 3, W / 3, W / 3])
        card_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story += [card_row, Spacer(1, 5 * mm)]

        fmt = brand_ig.get('format_breakdown', {})
        total_fmt_posts = sum(fmt.values()) if fmt else 0
        fmt_parts = []
        for k, v in sorted(fmt.items(), key=lambda x: x[1], reverse=True):
            pct = round(v / max(total_fmt_posts, 1) * 100)
            fmt_parts.append(f"{k}: {v} ({pct}%)")
        fmt_str = "  |  ".join(fmt_parts) if fmt_parts else "N/A"
        avg_views = brand_ig.get('avg_video_views', 0)
        views_text = f"{avg_views:,} avg views/reel" if avg_views else "No Reels data"
        story += [kv_table([
            ("FORMAT MIX", fmt_str),
            ("REELS PERFORMANCE", views_text),
            ("TOTAL POSTS ON PROFILE", str(brand_ig.get('total_posts', brand_ig.get('recent_posts_count', 'N/A')))),
            ("BIO", brand_ig.get('bio', 'N/A')[:150]),
        ]), Spacer(1, 5 * mm)]

    # ════════════════════════════════════════════════════════════════════
    # COMPETITOR COMPARISON TABLE
    # ════════════════════════════════════════════════════════════════════
    story += [Paragraph("COMPETITOR COMPARISON", ParagraphStyle('CCH', fontName='Helvetica-Bold', fontSize=14,
        textColor=BLACK, spaceAfter=4)),
        HRFlowable(width="100%", thickness=1.5, color=ACCENT), Spacer(1, 4 * mm)]

    comp_accounts = []
    if brand_ig and not brand_ig.get('error'):
        comp_accounts.append(('YOUR BRAND', brand_ig))
    for key in sorted(scraped_data.keys()):
        is_comp = key.startswith('competitor_') and key.endswith('_instagram')
        is_leader = key.startswith('category_leader_') and key.endswith('_instagram')
        if (is_comp or is_leader) and isinstance(scraped_data[key], dict) and not scraped_data[key].get('error'):
            cd = scraped_data[key]
            label = f"@{cd.get('handle', '?')}"
            comp_accounts.append((label, cd))

    if len(comp_accounts) >= 2:
        comp_headers = ["METRIC"] + [cl(name) for name, _ in comp_accounts]
        comp_rows = []
        metrics = [
            ("Followers", lambda d: f"{d.get('followers', 0):,}"),
            ("Engagement Rate", lambda d: f"{round(d.get('avg_er_pct', 0), 1)}%"),
            ("Avg Likes/Post", lambda d: f"{round(d.get('avg_likes', 0)):,}"),
            ("Avg Comments/Post", lambda d: f"{round(d.get('avg_comments', 0)):,}"),
            ("Avg Reel Views", lambda d: f"{d.get('avg_video_views', 0):,}" if d.get('avg_video_views') else "N/A"),
            ("Posting Frequency", lambda d: f"{d.get('posting_frequency_per_week', 'N/A')}/week"),
            ("Top Format", lambda d: max(d.get('format_breakdown', {'N/A': 1}), key=d.get('format_breakdown', {'N/A': 1}).get)),
            ("Dominant Hook Type", lambda d: max(d.get('hook_analysis', {'N/A': 1}), key=d.get('hook_analysis', {'N/A': 1}).get) if d.get('hook_analysis') else "N/A"),
        ]
        for metric_name, extractor in metrics:
            row = [metric_name]
            for _, data in comp_accounts:
                try:
                    row.append(extractor(data))
                except Exception:
                    row.append("N/A")
            comp_rows.append(row)

        n_cols = len(comp_headers)
        first_col = 35 * mm
        other_col = (W - first_col) / (n_cols - 1)
        col_widths = [first_col] + [other_col] * (n_cols - 1)

        comp_tbl = Table(
            [[Paragraph(f"<b>{cl(h)}</b>", ParagraphStyle('CTH', fontName='Helvetica-Bold', fontSize=7.5, textColor=WHITE)) for h in comp_headers]] +
            [[Paragraph(cl(str(c)), ParagraphStyle('CTD', fontName='Helvetica', fontSize=8, textColor=DARK_GRAY, leading=12)) for c in row] for row in comp_rows],
            colWidths=col_widths
        )
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), BLACK),
            ('BACKGROUND', (0, 1), (-1, -1), LIGHT_GRAY),
            ('BACKGROUND', (1, 1), (1, -1), colors.HexColor("#FFF8EC")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, BORDER),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ]
        comp_tbl.setStyle(TableStyle(style_cmds))
        story += [comp_tbl, Spacer(1, 5 * mm)]

    # ── CATEGORY LEADERBOARD ──
    leaderboard = []
    if brand_ig and not brand_ig.get('error'):
        leaderboard.append({
            'handle': brand_ig.get('handle', '?'), 'followers': brand_ig.get('followers', 0),
            'avg_likes': brand_ig.get('avg_likes', 0), 'avg_er_pct': brand_ig.get('avg_er_pct', 0),
            'fmt': brand_ig.get('format_breakdown', {}), 'label': 'YOU', 'source': 'brand',
        })
    for key in sorted(scraped_data.keys()):
        is_comp = key.startswith('competitor_') and key.endswith('_instagram')
        is_leader = key.startswith('category_leader_') and key.endswith('_instagram')
        if (is_comp or is_leader) and isinstance(scraped_data[key], dict) and not scraped_data[key].get('error'):
            cd = scraped_data[key]
            if cd.get('followers', 0) == 0 and cd.get('avg_likes', 0) == 0:
                continue
            leaderboard.append({
                'handle': cd.get('handle', '?'), 'followers': cd.get('followers', 0),
                'avg_likes': cd.get('avg_likes', 0), 'avg_er_pct': cd.get('avg_er_pct', 0),
                'fmt': cd.get('format_breakdown', {}),
                'label': 'LEADER' if is_leader else 'COMP', 'source': 'leader' if is_leader else 'competitor',
            })
    cat_data = scraped_data.get('category_data')
    already_in = {a['handle'].lower() for a in leaderboard}
    if isinstance(cat_data, dict) and not cat_data.get('error'):
        for acc in cat_data.get('top_accounts', []):
            handle = (acc.get('handle') or '').lower()
            if handle and handle not in already_in:
                if acc.get('followers', 0) == 0 and acc.get('avg_likes', 0) == 0:
                    continue
                leaderboard.append({
                    'handle': acc.get('handle', '?'), 'followers': acc.get('followers', 0),
                    'avg_likes': acc.get('avg_likes', 0), 'avg_er_pct': acc.get('avg_er_pct', 0),
                    'fmt': acc.get('format_breakdown', {}), 'label': '', 'source': 'category',
                })
                already_in.add(handle)

    leaderboard = [a for a in leaderboard if a['source'] == 'brand' or a.get('followers', 0) > 0 or a.get('avg_likes', 0) > 0]
    leaderboard.sort(key=lambda x: x['avg_er_pct'], reverse=True)
    brand_rank = None
    for idx, acc in enumerate(leaderboard, 1):
        if acc['source'] == 'brand':
            brand_rank = idx
            break

    if len(leaderboard) > 1:
        story += [Spacer(1, 4 * mm), Paragraph("CATEGORY LEADERBOARD", SUBHEAD_STYLE)]
        if brand_rank:
            rank_color = colors.HexColor('#CC3333') if brand_rank > len(leaderboard) * 0.5 else colors.HexColor('#228B22')
            story += [Paragraph(f"Your brand ranks #{brand_rank} out of {len(leaderboard)} accounts in this category",
                ParagraphStyle('RankText', fontName='Helvetica-Bold', fontSize=9, textColor=rank_color, spaceAfter=4))]

        lb_rows = []
        for idx, acc in enumerate(leaderboard[:10], 1):
            handle_display = f"@{acc['handle']}"
            if acc['label'] == 'YOU':
                handle_display += " (YOU)"
            elif acc['label'] == 'COMP':
                handle_display += " *"
            elif acc['label'] == 'LEADER':
                handle_display += " +"
            fmt = acc.get('fmt', {})
            top_fmt = max(fmt, key=fmt.get) if fmt else "-"
            lb_rows.append([str(idx), handle_display, f"{acc['followers']:,}",
                f"{round(acc['avg_likes'], 1)}", f"{round(acc['avg_er_pct'], 1)}%", top_fmt])
        story += [_comparison_table(lb_rows, ["#", "ACCOUNT", "FOLLOWERS", "AVG LIKES", "ENG. RATE", "TOP FORMAT"]),
                  Spacer(1, 2 * mm),
                  Paragraph("+ = Auto-discovered category leader  |  * = Your submitted competitor", ParagraphStyle(
                      'LegendStyle', fontName='Helvetica', fontSize=6.5, textColor=MID_GRAY)),
                  Spacer(1, 5 * mm)]

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

        story.append(PageBreak())

        story += [Spacer(1, 2 * mm),
            Paragraph(f"SECTION {i:02d}", S['sec_num']),
            Paragraph(cl(title), ParagraphStyle('ST2', fontName='Helvetica-Bold', fontSize=15,
                textColor=BLACK, spaceAfter=4)),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT),
            Spacer(1, 5 * mm)]

        if verdict and verdict.strip() not in ('', 'N/A', 'null', 'none'):
            story += [_verdict_box(verdict, verdict_type), Spacer(1, 4 * mm)]

        if not content or content.strip() in ('', 'N/A', 'null', 'none'):
            story.append(Paragraph("Data not available for this section.", CONTENT_STYLE))
            story.append(Spacer(1, 4 * mm))
            continue

        paragraphs = content.split('\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if para.startswith('## '):
                story.append(Paragraph(format_bold(cl(para[3:])), SUBHEAD_STYLE))
            elif para.startswith('### '):
                story.append(Paragraph(format_bold(cl(para[4:])),
                    ParagraphStyle('SH3', fontName='Helvetica-Bold', fontSize=9.5,
                        textColor=DARK_GRAY, spaceAfter=3, spaceBefore=6)))
            elif para.startswith('- ') or para.startswith('* '):
                bullet_text = format_bold(cl(para[2:].strip()))
                story.append(Paragraph(f"&bull; {bullet_text}", BULLET_STYLE))
            elif len(para) > 2 and para.split('.')[0].strip().isdigit() and para.index('.') < 4:
                dot_idx = para.index('.')
                num = para[:dot_idx]
                bullet_text = format_bold(cl(para[dot_idx + 1:].strip()))
                story.append(Paragraph(f"<b>{num}.</b> {bullet_text}", BULLET_STYLE))
            else:
                formatted = format_bold(cl(para))
                story.append(Paragraph(formatted, CONTENT_STYLE))

        story.append(Spacer(1, 6 * mm))

    # ════════════════════════════════════════════════════════════════════
    # TOP POSTS APPENDIX
    # ════════════════════════════════════════════════════════════════════
    if brand_ig and not brand_ig.get('error') and brand_ig.get('top_posts'):
        story += [PageBreak(), Paragraph("APPENDIX: TOP PERFORMING POSTS", SUBHEAD_STYLE),
                  HRFlowable(width="100%", thickness=1, color=ACCENT), Spacer(1, 4 * mm)]
        post_rows = []
        for p in brand_ig['top_posts'][:5]:
            cap = (p.get('caption', '') or '')[:100]
            cap = cap.replace('\n', ' ')
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
        story += [_comparison_table(post_rows, ["FORMAT", "LIKES", "COMMENTS", "CAPTION"]), Spacer(1, 6 * mm)]

    # ════════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════════
    story += [Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=1, color=ACCENT),
        Spacer(1, 3 * mm),
        Paragraph(f"Prepared by OffGrid Creatives AI  |  offgridcreativesai@gmail.com  |  {today}  |  Confidential  |  Version 6.0", S['footer']),
        Spacer(1, 2 * mm),
        Paragraph(LEGAL, ParagraphStyle('FL', fontName='Helvetica', fontSize=6,
            textColor=MID_GRAY, alignment=TA_CENTER, leading=8))]

    doc.build(story)
    logger.info("build_agent_pdf() COMPLETED — Version 6.0")

    with open(tmp.name, 'rb') as f:
        pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
    os.unlink(tmp.name)
    return pdf_b64
