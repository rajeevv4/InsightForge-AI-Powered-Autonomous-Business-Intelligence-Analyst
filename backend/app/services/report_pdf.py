"""
PDF rendering for the one-click report (reportlab + matplotlib Agg). Built fully in memory.

* A4, 18 mm margins, "Page x of y" footer on every page.
* Every table cell is a Paragraph, so long text wraps instead of overflowing.
* Unicode-safe: the first available Unicode TrueType font is registered (Arial Unicode on macOS,
  Noto / DejaVu on Linux, else the DejaVu Sans that ships inside matplotlib). If no TTF can be
  loaded, Helvetica is used and characters outside Latin-1 become "?". Text is XML-escaped before
  it reaches reportlab's Paragraph parser, so user labels (e.g. "<b>&") can never break the layout.
  reportlab does not shape complex scripts (Devanagari conjuncts may render unjoined) but never crashes.
"""

import io
import logging
import os
import re
import threading
import warnings
from datetime import datetime
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
from matplotlib import font_manager  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from backend.app.schemas.report import ReportResponse  # noqa: E402

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
INDIGO = colors.HexColor("#4f46e5")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748b")
GRID = colors.HexColor("#e2e8f0")
STATUS_COLOR = {"PASS": colors.HexColor("#047857"), "WARN": colors.HexColor("#b45309"), "FAIL": colors.HexColor("#b91c1c")}

FONT_CANDIDATES = [
    os.getenv("REPORT_FONT_PATH", ""),
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf"),  # always shipped with matplotlib
]
_font_lock = threading.Lock()
_font: Optional[Tuple[str, str, Optional[str]]] = None  # (regular, bold, ttf path)


def report_fonts() -> Tuple[str, str, Optional[str]]:
    """Register (once) the first loadable Unicode TTF. Returns (regular name, bold name, path)."""
    global _font
    with _font_lock:
        if _font is not None:
            return _font
        for path in FONT_CANDIDATES:
            if not path or not os.path.isfile(path):
                continue
            try:
                pdfmetrics.registerFont(TTFont("IFUnicode", path))
                bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace("NotoSans-Regular", "NotoSans-Bold")
                bold = "IFUnicode"
                if bold_path != path and os.path.isfile(bold_path):
                    pdfmetrics.registerFont(TTFont("IFUnicodeBold", bold_path))
                    bold = "IFUnicodeBold"
                _font = ("IFUnicode", bold, path)
                return _font
            except Exception as e:  # unreadable / unsupported font file: try the next one
                logger.warning(f"Report font {path} unusable: {e}")
        _font = ("Helvetica", "Helvetica-Bold", None)
        return _font


def safe(text_value: object) -> str:
    """XML-escape for Paragraph; with the Helvetica fallback, replace characters it cannot encode."""
    s = "" if text_value is None else str(text_value)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    if report_fonts()[2] is None:
        s = s.encode("latin-1", "replace").decode("latin-1")
    return escape(s)


def safe_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "").strip("_")[:60] or "dataset"
    return f"InsightForge_Report_{base}_{datetime.now().strftime('%Y-%m-%d')}.pdf"


# --------------------------------------------------------------------------- styles
def _styles():
    reg, bold, _ = report_fonts()
    return {
        "title": ParagraphStyle("t", fontName=bold, fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=4),
        "subtitle": ParagraphStyle("st", fontName=reg, fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, textColor=INDIGO, spaceBefore=10, spaceAfter=5, keepWithNext=1),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=10, leading=13, textColor=SLATE, spaceBefore=6, spaceAfter=3, keepWithNext=1),
        "body": ParagraphStyle("b", fontName=reg, fontSize=9.5, leading=13, textColor=SLATE, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bl", fontName=reg, fontSize=9.5, leading=13, textColor=SLATE, leftIndent=10, bulletIndent=0, spaceAfter=2),
        "small": ParagraphStyle("s", fontName=reg, fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("c", fontName=reg, fontSize=8.5, leading=11, textColor=SLATE),
        "cell_b": ParagraphStyle("cb", fontName=bold, fontSize=8.5, leading=11, textColor=colors.HexColor("#0f172a")),
        "head": ParagraphStyle("hd", fontName=bold, fontSize=8, leading=10, textColor=MUTED),
        "kpi_label": ParagraphStyle("kl", fontName=reg, fontSize=7.5, leading=9.5, textColor=MUTED),
        "kpi_value": ParagraphStyle("kv", fontName=bold, fontSize=11.5, leading=14, textColor=colors.HexColor("#0f172a")),
        "unavailable": ParagraphStyle("u", fontName=reg, fontSize=9, leading=12, textColor=colors.HexColor("#b45309"),
                                      backColor=colors.HexColor("#fffbeb"), borderPadding=4, spaceBefore=2, spaceAfter=4),
    }


def _table(rows: List[List[object]], widths: List[float], st, header: bool = True, status_col: Optional[int] = None) -> Table:
    data = []
    for i, row in enumerate(rows):
        cells = []
        for j, v in enumerate(row):
            style = st["head"] if (header and i == 0) else st["cell"]
            txt = safe(v)
            if status_col is not None and j == status_col and i > 0 and str(v) in STATUS_COLOR:
                txt = f'<font color="{STATUS_COLOR[str(v)].hexval()}"><b>{txt}</b></font>'
            cells.append(Paragraph(txt, style))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc") if header else colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _unavailable(st, reason: str) -> Paragraph:
    return Paragraph(f"Section unavailable: {safe(reason)}", st["unavailable"])


def _trend_png(r: ReportResponse) -> Optional[bytes]:
    pts = r.trend.points if r.trend else []
    if not pts:
        return None
    _, _, path = report_fonts()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # missing-glyph warnings for exotic scripts must never fail the PDF
        if path:
            try:
                font_manager.fontManager.addfont(path)
                family = font_manager.FontProperties(fname=path).get_name()
            except Exception:
                family = "DejaVu Sans"
        else:
            family = "DejaVu Sans"
        with plt.rc_context({"font.family": family, "font.size": 8}):
            fig, ax = plt.subplots(figsize=(7.2, 2.7), dpi=160)
            x = list(range(len(pts)))
            ax.plot(x, [p.value for p in pts], color="#4f46e5", linewidth=1.8, marker="o", markersize=2.5)
            ax.fill_between(x, [p.value for p in pts], color="#6366f1", alpha=0.08)
            step = max(1, -(-len(pts) // 12))  # at most 12 month labels
            ax.set_xticks(x[::step])
            ax.set_xticklabels([p.period for p in pts][::step], rotation=40, ha="right")
            cur = r.currency or ""
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _p: f"{cur + ' ' if cur else ''}{_compact(v)}"))
            ax.grid(axis="y", color="#e2e8f0", linewidth=0.6)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.set_ylim(bottom=min(0, min(p.value for p in pts)))
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            plt.close(fig)
    return buf.getvalue()


def _compact(v: float) -> str:
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:.1f}".rstrip("0").rstrip(".") + suf
    return f"{v:.0f}"


class _NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so the footer can say 'Page x of y'."""

    footer_text = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            reg = report_fonts()[0]
            self.setFont(reg, 7.5)
            self.setFillColor(MUTED)
            self.drawString(MARGIN, 10 * mm, self.footer_text[:110])
            self.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            self.setStrokeColor(GRID)
            self.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
            super().showPage()
        super().save()


# --------------------------------------------------------------------------- document
def build_pdf(r: ReportResponse) -> bytes:
    st = _styles()
    E = r.section_errors
    story: List[object] = []

    # header
    story.append(Paragraph("InsightForge Report", st["title"]))
    story.append(Paragraph(safe(r.dataset_name), ParagraphStyle("dn", parent=st["h3"], fontSize=12, leading=15, spaceBefore=0)))
    meta = [f"Generated {r.generated_at.strftime('%Y-%m-%d %H:%M UTC')}", f"Period: {r.period or 'no time column'}"]
    if r.total_rows is not None:
        meta.append(f"{r.total_rows:,} rows in {len(r.row_counts)} tables")
    story.append(Paragraph(safe(" · ".join(meta)), st["subtitle"]))
    story.append(Paragraph("Deterministic report: every number comes from SQL and statistics; every sentence is a fixed template. No AI.", st["small"]))
    if r.row_counts:
        items = list(r.row_counts.items())
        rows = [["Table", "Rows", "Table", "Rows"]]
        for i in range(0, len(items), 2):
            a = items[i]
            b = items[i + 1] if i + 1 < len(items) else ("", "")
            rows.append([a[0], f"{a[1]:,}", b[0], f"{b[1]:,}" if b[1] != "" else ""])
        story += [Spacer(1, 4), _table(rows, [CONTENT_W * 0.32, CONTENT_W * 0.18] * 2, st)]
    elif "header" in E:
        story.append(_unavailable(st, E["header"]))

    # executive summary
    story.append(Paragraph("Executive summary", st["h2"]))
    if r.summary:
        story += [Paragraph(safe(s), st["bullet"], bulletText="•") for s in r.summary]
    else:
        story.append(_unavailable(st, E.get("summary", "not computed")))

    # KPI tiles (4 per row)
    story.append(Paragraph("Key figures", st["h2"]))
    if r.kpis:
        cells = [[Paragraph(safe(k.label), st["kpi_label"]), Paragraph(safe(k.display), st["kpi_value"])] for k in r.kpis]
        grid, w = [], CONTENT_W / 4
        for i in range(0, len(cells), 4):
            row = cells[i:i + 4] + [""] * (4 - len(cells[i:i + 4]))  # empty padding cells must be plain strings
            grid.append(row)
        t = Table(grid, colWidths=[w] * 4, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, GRID), ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
    else:
        story.append(_unavailable(st, E.get("kpis", "not computed")))

    # monthly trend
    story.append(Paragraph("Monthly trend", st["h2"]))
    png = None
    try:
        png = _trend_png(r)
    except Exception as e:
        logger.warning(f"Trend chart failed: {e}")
    if png:
        story.append(Paragraph(safe(r.trend.title), st["small"]))
        story.append(Image(io.BytesIO(png), width=CONTENT_W, height=CONTENT_W * 2.7 / 7.2))
    else:
        story.append(_unavailable(st, E.get("trend", "chart could not be drawn")))

    # breakdowns
    if r.breakdowns:
        for bi, b in enumerate(r.breakdowns):
            rows = [["Group", "Value", "Share of total"]] + [[i.label, i.display, f"{i.share_pct:.1f}%" if i.share_pct is not None else "—"] for i in b.items]
            if b.other_groups and b.other_display:
                rows.append([f"All other ({b.other_groups} groups)", b.other_display, ""])
            block = [Paragraph(safe(b.title), st["h3"]), _table(rows, [CONTENT_W * 0.5, CONTENT_W * 0.3, CONTENT_W * 0.2], st)]
            if b.total_line:
                block.append(Paragraph(safe(b.total_line), ParagraphStyle("tl", parent=st["small"], textColor=SLATE, spaceBefore=2)))
            if bi == 0:  # the section heading travels with the first breakdown (never stranded at a page bottom)
                block.insert(0, Paragraph("Top breakdowns", st["h2"]))
            story.append(KeepTogether(block))
    else:
        story.append(Paragraph("Top breakdowns", st["h2"]))
        story.append(_unavailable(st, E.get("breakdowns", "not computed")))

    # anomalies
    story.append(Paragraph("Top anomalies and their drivers", st["h2"]))
    if r.anomalies is not None:
        if r.anomalies:
            story.append(Paragraph(safe(f"{r.anomaly_count} anomalies flagged in the daily series; the {len(r.anomalies)} largest are shown."), st["small"]))
            rows = [["Date", "Change", "Observed / expected", "Main driver (Feature 1 explanation)"]]
            for a in r.anomalies:
                rows.append([a.period, f"{a.direction} ({a.severity})", f"{a.observed_display} vs {a.expected_display}", a.driver_sentence])
            story.append(_table(rows, [CONTENT_W * 0.14, CONTENT_W * 0.14, CONTENT_W * 0.25, CONTENT_W * 0.47], st))
            # heading + intro + table: move them to the next page together if the table would start there anyway
            story[-3:] = [KeepTogether(story[-3:])]
        else:
            story.append(Paragraph("No anomalies were flagged in the daily series.", st["body"]))
    else:
        story.append(_unavailable(st, E.get("anomalies", "not computed")))

    # forecast
    story.append(Paragraph("3-month baseline forecast", st["h2"]))
    f = r.forecast
    if f is not None:
        if f.status == "ok":
            story.append(Paragraph(safe(f"{f.metric_label}: reliability {f.reliability} (backtest MAPE {f.mape:.1f}% vs naive "
                                        f"{f.naive_mape:.1f}%). Model: {f.model}. Training window: {f.training_window}."), st["body"]))
            rows = [["Month", "Expected", "80% range"]] + [[p.period, p.expected_display, p.range_display] for p in f.points]
            story += [Spacer(1, 3), _table(rows, [CONTENT_W * 0.2, CONTENT_W * 0.3, CONTENT_W * 0.5], st)]
        else:
            story.append(Paragraph(safe(f"No forecast for {f.metric_label}: {f.reason}"), st["body"]))
        story.append(Paragraph(safe(f.disclaimer), st["small"]))
    else:
        story.append(_unavailable(st, E.get("forecast", "not computed")))

    # data quality
    story.append(Paragraph("Data quality", st["h2"]))
    if r.data_quality:
        rows = [["Check", "Status", "Detail"]] + [[d.check, d.status, d.detail] for d in r.data_quality]
        story.append(_table(rows, [CONTENT_W * 0.32, CONTENT_W * 0.12, CONTENT_W * 0.56], st, status_col=1))
    else:
        story.append(_unavailable(st, E.get("data_quality", "not computed")))

    # caveats + methodology
    story.append(Paragraph("Caveats", st["h2"]))
    story += [Paragraph(safe(c), st["bullet"], bulletText="•") for c in (r.caveats or ["None."])]
    story.append(Paragraph("Methodology", st["h2"]))
    story += [Paragraph(safe(m), st["bullet"], bulletText="•") for m in r.methodology]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=18 * mm,
                            title=f"InsightForge Report - {r.dataset_name}", author="InsightForge")
    footer = f"InsightForge report · {r.dataset_name} · {r.generated_at.strftime('%Y-%m-%d')}"
    if report_fonts()[2] is None:
        footer = footer.encode("latin-1", "replace").decode("latin-1")
    canvas_cls = type("ReportCanvas", (_NumberedCanvas,), {"footer_text": footer})
    doc.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()
