import csv
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus import Table as PdfTable
from reportlab.platypus import TableStyle

from .reports import Report


def safe(value):
    """Stop spreadsheet programs from running text that starts like a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def to_csv(report: Report) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([report.title])
    writer.writerow([report.subtitle])
    writer.writerow([])
    for label, value in report.summary:
        writer.writerow([label, value])
    for table in report.tables:
        writer.writerow([])
        writer.writerow([table.title])
        writer.writerow(table.columns)
        for row in table.rows:
            writer.writerow([safe(v) for v in row])
    return buffer.getvalue().encode("utf-8-sig")  # opens correctly in Excel


def to_pdf(report: Report) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
        title=report.title,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(escape(report.title), styles["Title"]),
        Paragraph(escape(report.subtitle), styles["Normal"]),
        Spacer(1, 12),
    ]

    if report.summary:
        summary = PdfTable([[str(l), str(v)] for l, v in report.summary], hAlign="LEFT")
        summary.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(summary)

    for table in report.tables:
        story.append(Spacer(1, 14))
        story.append(Paragraph(escape(table.title), styles["Heading3"]))
        if not table.rows:
            story.append(Paragraph("No data for this period.", styles["Normal"]))
            continue
        data = [table.columns] + [[str(v) for v in row] for row in table.rows]
        grid = PdfTable(data, repeatRows=1)
        grid.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
                ]
            )
        )
        story.append(grid)

    doc.build(story)
    return buffer.getvalue()