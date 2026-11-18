from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

MARGIN = 1.5 * cm
_base = getSampleStyleSheet()

TITLE = ParagraphStyle("SthimTitle", parent=_base["Title"], fontSize=16, leading=19, alignment=0, spaceAfter=6)
H2 = ParagraphStyle("SthimH2", parent=_base["Heading2"], fontSize=12, leading=14, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("SthimH3", parent=_base["Heading3"], fontSize=9.5, leading=12, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("SthimBody", parent=_base["BodyText"], fontSize=9, leading=11.5)
LABEL = ParagraphStyle("SthimLabel", parent=BODY, fontName="Helvetica-Bold")
RIGHT = ParagraphStyle(
    "SthimRight", parent=BODY, alignment=TA_RIGHT, fontName="Helvetica-Bold",
    spaceBefore=3, spaceAfter=6,
)
CELL_STYLE = ParagraphStyle("SthimCell", parent=BODY, fontSize=7.5, leading=9)
HEAD_STYLE = ParagraphStyle(
    "SthimHead", parent=CELL_STYLE, fontName="Helvetica-Bold", textColor=colors.white
)


def p(text, style=BODY):
    safe = escape("" if text is None else str(text)).replace("\n", "<br/>")
    return Paragraph(safe, style)


def cell(text):
    return p(text, CELL_STYLE)


def data_table(header, rows, col_widths, *, zebra=True):
    data = [[p(title, HEAD_STYLE) for title in header]] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F3F3")]))
    table.setStyle(TableStyle(style))
    return table


class _NumberedCanvas(canvas.Canvas):
    footer_text = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        width = self._pagesize[0]
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.grey)
        self.drawString(MARGIN, 1 * cm, self.footer_text)
        self.drawRightString(width - MARGIN, 1 * cm, f"Página {self._pageNumber} de {total}")


def _canvas_with_footer(text):
    return type("FooterCanvas", (_NumberedCanvas,), {"footer_text": text})


def _draw_header(canv, doc):
    width, height = doc.pagesize
    canv.saveState()
    canv.setFont("Helvetica-Bold", 9)
    canv.drawString(MARGIN, height - 1 * cm, "STHIM")
    canv.setFont("Helvetica", 8)
    canv.drawString(MARGIN + 1.3 * cm, height - 1 * cm, "Sistema de Transporte Hospitalar Intermunicipal")
    canv.setStrokeColor(colors.lightgrey)
    canv.line(MARGIN, height - 1.15 * cm, width - MARGIN, height - 1.15 * cm)
    canv.restoreState()

def render_pdf(story, *, title, footer, wide=False):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4) if wide else A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.8 * cm, bottomMargin=1.6 * cm,
        title=title, author="STHIM",
    )
    doc.build(
        story,
        onFirstPage=_draw_header,
        onLaterPages=_draw_header,
        canvasmaker=_canvas_with_footer(footer),
    )
    buffer.seek(0)
    return buffer