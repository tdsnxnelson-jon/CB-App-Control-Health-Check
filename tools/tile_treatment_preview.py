"""Generate a PPTX that compares four non-pastel tile treatments.

Usage:
    python tools/tile_treatment_preview.py [output-path]
"""
import os
import sys
from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from healthcheck.report import pptx_helpers as ph


WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CHARCOAL = RGBColor(0x26, 0x2C, 0x33)
GRAY = RGBColor(0xD9, 0xDE, 0xE3)
PALE_GRAY = RGBColor(0xF5, 0xF7, 0xF8)
STATUS = {
    "critical": RGBColor(0xC8, 0x2D, 0x25),
    "warning": RGBColor(0xBE, 0x68, 0x00),
    "caution": RGBColor(0x8F, 0x70, 0x00),
    "ok": RGBColor(0x16, 0x79, 0x46),
}
FINDINGS = [
    ("critical", "23 endpoints have not checked in for more than 7 days."),
    ("warning", "Approval activity is above the normal daily volume."),
    ("caution", "Five custom rules use broad wildcard paths."),
    ("ok", "Agent sync coverage is meeting the reporting target."),
]


def _card(slide, x, y, width, height, fill, line, rounded=True):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    card = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(width), Inches(height))
    card.fill.solid()
    card.fill.fore_color.rgb = fill
    card.line.color.rgb = line
    card.shadow.inherit = False
    return card


def _heading(slide, title, subtitle):
    ph._add_text(slide, ph.MARGIN, 1.12, ph.CONTENT_W, 0.3, subtitle, size=12, color=ph.MUTED_TEXT)
    ph._add_text(slide, ph.MARGIN, 1.55, ph.CONTENT_W, 0.22, "CURRENT HEALTH SNAPSHOT", size=8, bold=True, color=ph.MUTED_TEXT)
    ph._add_text(slide, ph.MARGIN, 1.78, ph.CONTENT_W, 0.45, title, size=18, bold=True, color=ph.NAVY)


def _metric_cards(slide, top, style):
    metrics = [("2", "Critical", "critical"), ("7", "Warning", "warning"), ("38", "Passing", "ok")]
    gap, width = 0.16, (ph.CONTENT_W - 0.32) / 3
    for index, (value, label, severity) in enumerate(metrics):
        x = ph.MARGIN + index * (width + gap)
        color = STATUS[severity]
        flat = style == "dense"
        fill = WHITE if style != "header" else CHARCOAL
        _card(slide, x, top, width, 0.66, fill, color if style == "outline" else GRAY, rounded=not flat)
        if style == "rail":
            ph._add_rect(slide, x, top, 0.06, 0.66, color)
        if style == "header":
            ph._add_rect(slide, x, top, 0.08, 0.66, color)
        if style == "dense":
            ph._add_rect(slide, x, top, width, 0.06, color)
        text_color = WHITE if style == "header" else ph.DARK_TEXT
        ph._add_text(slide, x + 0.18, top + 0.14, 0.5, 0.28, value, size=18, bold=True, color=color if style != "header" else WHITE, anchor=MSO_ANCHOR.MIDDLE)
        ph._add_text(slide, x + 0.82, top + 0.18, width - 0.98, 0.22, label, size=10, bold=True, color=text_color, anchor=MSO_ANCHOR.MIDDLE)


def _finding_cards(slide, top, style):
    width, height, gap = (ph.CONTENT_W - 0.18) / 2, 1.72, 0.18
    for index, (severity, message) in enumerate(FINDINGS):
        row, col = divmod(index, 2)
        x, y = ph.MARGIN + col * (width + gap), top + row * (height + gap)
        color = STATUS[severity]
        flat = style == "dense"
        fill = CHARCOAL if style == "header" else WHITE
        _card(slide, x, y, width, height, fill, color if style == "outline" else GRAY, rounded=not flat)
        if style == "rail":
            ph._add_rect(slide, x, y, 0.08, height, color)
        if style == "header":
            ph._add_rect(slide, x, y, width, 0.34, CHARCOAL)
            ph._add_rect(slide, x, y, 0.08, 0.34, color)
        if style == "dense":
            ph._add_rect(slide, x, y, width, 0.07, color)
        label_color = WHITE if style == "header" else color
        body_color = WHITE if style == "header" else ph.DARK_TEXT
        ph._add_text(slide, x + 0.22, y + (0.1 if style == "header" else 0.18), width - 0.44, 0.16, severity.upper(), size=8, bold=True, color=label_color)
        ph._add_text(slide, x + 0.22, y + (0.52 if style == "header" else 0.5), width - 0.44, 0.58, message, size=12, bold=True, color=body_color)


def build_preview(output_path: str) -> str:
    options = [
        ("White Tiles + Status Rail", "White cards, strong severity rails, and no colored fill.", "rail"),
        ("Charcoal Tile Headers", "A dark header band makes the tiles feel more deliberate and premium.", "header"),
        ("Severity-Outline Tiles", "White cards with a strong severity outline instead of a filled background.", "outline"),
        ("Dense Operational Style", "Flat panels and a status top rule for a compact engineering-report treatment.", "dense"),
    ]
    prs = ph.create_deck()
    for title, subtitle, style in options:
        slide = ph.add_content_slide(prs, title)
        _heading(slide, "Executive Summary", subtitle)
        _metric_cards(slide, 2.4, style)
        _finding_cards(slide, 3.32, style)
    prs.save(output_path)
    return output_path


if __name__ == "__main__":
    default_output = os.path.join(os.path.dirname(__file__), "tile_treatment_preview.pptx")
    print(build_preview(sys.argv[1] if len(sys.argv) > 1 else default_output))