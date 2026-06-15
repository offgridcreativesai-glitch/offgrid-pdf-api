"""
PDF color palette, styles, and reusable table/box helpers for ReportLab.
"""

import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER

W = 170 * mm

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
    """Clean text for ReportLab: XML-escape and replace unsupported Unicode chars."""
    if not isinstance(t, str):
        t = str(t)
    t = t.replace('₹', 'Rs.').replace('₹', 'Rs.')
    t = t.replace('■', '').replace('●', '-').replace('•', '-')
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def format_bold(text):
    """Convert **bold** markers to ReportLab <b> tags."""
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)


def sec_header(num, title):
    return [Spacer(1, 6*mm), Paragraph(f"SECTION {num:02d}", S['sec_num']),
            Paragraph(cl(title), S['sec_title']),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT), Spacer(1, 4*mm)]


def tag(label):
    return Paragraph(cl(label), S['label'])


def chip_row(items, cols=3):
    if not items:
        return Spacer(1, 2)
    rows, row = [], []
    for i, item in enumerate(items):
        row.append(Paragraph(f"• {cl(str(item))}", S['bullet']))
        if len(row) == cols or i == len(items) - 1:
            while len(row) < cols:
                row.append(Spacer(1, 1))
            rows.append(row)
            row = []
    t = Table(rows, colWidths=[W / cols] * cols)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('BOX', (0, 0), (-1, -1), 0.3, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def kv_table(rows_data, c1=50*mm):
    rows = [[Paragraph(cl(str(k)), S['label']), Paragraph(cl(str(v)), S['body'])] for k, v in rows_data]
    t = Table(rows, colWidths=[c1, W - c1])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def hook_box(text):
    t = Table([[Paragraph(f'"{cl(text)}"', S['hook'])]], colWidths=[W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('BOX', (0, 0), (-1, -1), 0.3, BORDER),
        ('LINEBEFORE', (0, 0), (0, -1), 4, ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    return t


def black_hdr(text, left_color=ACCENT):
    h = Table([[Paragraph(cl(text), S['brief_hdr'])]], colWidths=[W])
    h.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BLACK),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('LINEBEFORE', (0, 0), (0, -1), 4, left_color),
    ]))
    return h


def insight_box(text):
    if not text or not isinstance(text, str) or text.strip().lower() in ('', 'none', 'null', 'n/a'):
        return Spacer(1, 1)
    INSIGHT_BG = colors.HexColor("#FFF8EC")
    INSIGHT_LBL = ParagraphStyle('ILB', fontName='Helvetica-Bold', fontSize=7, textColor=ACCENT, spaceAfter=3)
    INSIGHT_TXT = ParagraphStyle('ITX', fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=14)
    rows = [[Paragraph("WHAT THIS MEANS FOR YOU", INSIGHT_LBL)],
            [Paragraph(cl(text.strip()), INSIGHT_TXT)]]
    t = Table(rows, colWidths=[W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), INSIGHT_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, ACCENT),
        ('LINEBEFORE', (0, 0), (0, -1), 3, ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def risk_box(title, content, color=RED_ALERT):
    rs = ParagraphStyle('RS', fontName='Helvetica-Bold', fontSize=9, textColor=color)
    t = Table([[Paragraph(cl(title), rs), Paragraph(cl(str(content)), S['body'])]], colWidths=[45*mm, 125*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBEFORE', (0, 0), (0, -1), 3, color),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
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
