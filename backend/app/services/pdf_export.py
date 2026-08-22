import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from sqlmodel import Session, select
from app.models import Product, ProductAttribute, EnrichmentResult


class NumberedCanvas(canvas.Canvas):
    """Canvas for adding page numbers 'Page X of Y' and header/footer to all pages."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(36, 762, "CatalogIQ — Unilog Product Delivery & Intelligence Catalog")
            self.drawRightString(576, 762, "Authoritative 252-Column Format")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(36, 756, 576, 756)

        # Footer
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 45, 576, 45)
        self.drawString(36, 32, "Confidential — Unilog Content & Normalization Specification")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(576, 32, page_str)
        self.restoreState()


def build_catalog_pdf(products: List[Product], session: Session, delivery_rows: List[Dict[str, Any]]) -> bytes:
    """
    Generates an executive-ready PDF catalog and product specification report.
    Supports both full catalog rosters and individual product specification sheets.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A")
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#64748B")
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=6
    )
    card_title = ParagraphStyle(
        'CardTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F172A")
    )
    meta_label = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B")
    )
    meta_val = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B")
    )
    body_desc = ParagraphStyle(
        'BodyDesc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155")
    )

    elements = []
    is_single_product = len(products) == 1

    # 1. Header Block
    header_title = f"CatalogIQ — Product Specification Dossier" if is_single_product else "CatalogIQ — Master Product Delivery Catalog"
    elements.append(Paragraph(header_title, title_style))
    elements.append(Paragraph(
        f"Authoritative 252-Column Standardized Delivery Report • Generated {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        subtitle_style
    ))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#9B8F77"), spaceAfter=12))

    # Pre-map delivery rows by SKU / MPN for O(1) attribute lookup
    delivery_map: Dict[str, Dict[str, Any]] = {}
    for drow in delivery_rows:
        mpn_key = drow.get("Mfg_Part_Num") or drow.get("SKU - MY_PART_NUMBER") or drow.get("MANUFACTURER_PART_NUMBER") or ""
        if mpn_key:
            delivery_map[mpn_key] = drow

    if not is_single_product:
        # 2. Executive KPI Summary Box
        total_count = len(products)
        avg_score = round(sum(p.quality_score or 0 for p in products) / max(total_count, 1), 1) if total_count > 0 else 0
        verified_count = sum(1 for p in products if p.status in ('verified', 'approved') or (p.quality_score and p.quality_score >= 80))
        verif_rate = round((verified_count / max(total_count, 1)) * 100.0, 1)

        kpi_data = [
            [
                Paragraph("<b>Total Catalog Items</b>", meta_label),
                Paragraph("<b>Average Quality Score</b>", meta_label),
                Paragraph("<b>Verified Compliance Rate</b>", meta_label),
                Paragraph("<b>Delivery Standard</b>", meta_label),
            ],
            [
                Paragraph(f"<b>{total_count:,} Products</b>", title_style),
                Paragraph(f"<b>{avg_score}%</b>", title_style),
                Paragraph(f"<b>{verif_rate}%</b>", title_style),
                Paragraph("<b>252 Columns</b>", title_style),
            ]
        ]
        kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 14))

        # 3. Product Catalog Overview Table (Top items summary)
        elements.append(Paragraph("Product Inventory & Specification Roster", section_heading))

        table_rows = [
            [
                Paragraph("<b>SKU / MPN</b>", meta_label),
                Paragraph("<b>Brand & Manufacturer</b>", meta_label),
                Paragraph("<b>Classpath & Product Name</b>", meta_label),
                Paragraph("<b>Quality Score</b>", meta_label),
                Paragraph("<b>Status</b>", meta_label),
            ]
        ]

        sample_products = products[:80]
        for p in sample_products:
            q_color = "#059669" if (p.quality_score or 0) >= 80 else "#D97706"
            status_text = "Verified" if p.status in ('verified', 'approved') else "Needs Review"
            status_color = "#065F46" if status_text == "Verified" else "#92400E"

            sku_p = Paragraph(f"<b>{p.sku}</b>", meta_val)
            brand_p = Paragraph(f"<b>{p.brand}</b>", meta_val)
            name_p = Paragraph(f"<b>{p.product_name[:42]}</b><br/><font size=7 color='#64748B'>{p.category[:40]}</font>", body_desc)
            score_p = Paragraph(f"<font color='{q_color}'><b>{int(p.quality_score or 0)}%</b></font>", meta_val)
            status_p = Paragraph(f"<font color='{status_color}'><b>{status_text}</b></font>", meta_val)

            table_rows.append([sku_p, brand_p, name_p, score_p, status_p])

        overview_table = Table(table_rows, colWidths=[110, 110, 200, 60, 60])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
        ]))
        elements.append(overview_table)
        elements.append(Spacer(1, 14))

        # 4. Featured Detailed Product Specification Cards (First 10 items)
        elements.append(PageBreak())
        elements.append(Paragraph("Detailed Product Intelligence Sheets", section_heading))
        elements.append(Paragraph("Includes 5-channel descriptions, extracted attribute values, UOM normalization, and evidence provenance.", subtitle_style))
        elements.append(Spacer(1, 8))

    # Detail Cards for products (up to 15 items for multi-product or 1 for single product)
    detail_prods = products if is_single_product else products[:15]
    for p in detail_prods:
        drow = delivery_map.get(p.sku) or {}
        inv_desc = drow.get("INVOICE_DESC") or p.product_name[:40].upper()
        mob_desc = drow.get("MOBILE_DESC") or f"{p.brand}, {p.product_name}, {p.sku}"
        short_d = drow.get("SHORT_DESC") or p.product_name
        long_d = drow.get("LONG_DESC1") or p.commerce_description or p.description or ""
        retail_d = drow.get("RETAIL_DESC") or ""

        card_elements = []
        card_elements.append(Paragraph(f"<b>{p.brand} — {p.product_name}</b>", card_title))
        card_elements.append(Paragraph(
            f"<b>SKU / MPN:</b> {p.sku} &nbsp;|&nbsp; <b>Classpath:</b> {p.category} &nbsp;|&nbsp; <b>Quality Score:</b> {int(p.quality_score or 0)}% &nbsp;|&nbsp; <b>Status:</b> {p.status.upper()}",
            subtitle_style
        ))
        card_elements.append(Spacer(1, 4))

        # 5 Channel Descriptions table
        desc_rows = [
            [Paragraph("<b>Invoice Desc (≤40 CAPS):</b>", meta_label), Paragraph(inv_desc, body_desc)],
            [Paragraph("<b>Mobile Desc (60–80 chars):</b>", meta_label), Paragraph(mob_desc, body_desc)],
            [Paragraph("<b>Short Title:</b>", meta_label), Paragraph(short_d, body_desc)],
            [Paragraph("<b>Long Commerce Desc:</b>", meta_label), Paragraph(long_d, body_desc)],
        ]
        if retail_d:
            desc_rows.append([Paragraph("<b>Retail Summary:</b>", meta_label), Paragraph(retail_d, body_desc)])

        desc_table = Table(desc_rows, colWidths=[130, 410])
        desc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        card_elements.append(desc_table)
        card_elements.append(Spacer(1, 4))

        # Extract attributes from drow (ATTRIBUTE_LABEL 1..50, ATTRIBUTE_VALUE 1..50, ATTRIBUTE_UOM 1..50)
        attr_strings = []
        for i in range(1, 51):
            lbl = drow.get(f"ATTRIBUTE_LABEL {i}")
            val = drow.get(f"ATTRIBUTE_VALUE {i}")
            uom = drow.get(f"ATTRIBUTE_UOM {i}")
            if lbl and val:
                uom_str = f" {uom}" if uom else ""
                attr_strings.append(f"<b>{lbl}:</b> {val}{uom_str}")

        if attr_strings:
            max_show = 12 if is_single_product else 8
            card_elements.append(Paragraph(f"<b>Extracted Specifications:</b> {'; '.join(attr_strings[:max_show])}", body_desc))

        card_elements.append(Spacer(1, 10))
        elements.append(KeepTogether(card_elements))

    doc.build(elements, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
