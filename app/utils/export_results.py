"""Export exam results to Excel and PDF."""

import io
from typing import List
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet


def export_results_excel(
    results: List[dict],
    exam_title: str,
    total_marks: int,
) -> io.BytesIO:
    """Export results to Excel (xlsx) using openpyxl."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Border, Side
    except ImportError:
        # Fallback: create CSV if openpyxl not installed
        buffer = io.BytesIO()
        lines = [
            "Roll Number,Set Code,Marks Obtained,Total Marks,Percentage,Wrong Answers,Scanned At"
        ]
        for r in results:
            wrong = ",".join(str(x) for x in (r.get("wrong_answers") or []))
            scanned = (r.get("created_at") or "").replace(",", " ")
            lines.append(
                f"{r.get('roll_number', '')},{r.get('set_code', '')},"
                f"{r.get('marks_obtained', 0)},{total_marks},"
                f"{r.get('percentage', 0)},\"{wrong}\",{scanned}"
            )
        buffer.write("\n".join(lines).encode("utf-8"))
        buffer.seek(0)
        return buffer

    wb = Workbook()
    ws = wb.active
    ws.title = "Results"

    header_font = Font(bold=True)
    headers = ["Roll Number", "Set Code", "Marks", "Total", "Percentage", "Wrong Answers", "Scanned At"]
    ws.append([exam_title])
    ws.append([])
    ws.append(headers)
    for cell in ws[3]:
        cell.font = header_font

    for r in results:
        wrong = ", ".join(str(x) for x in (r.get("wrong_answers") or []))
        scanned = r.get("created_at", "")
        if hasattr(scanned, "strftime"):
            scanned = scanned.strftime("%Y-%m-%d %H:%M")
        ws.append([
            r.get("roll_number", ""),
            r.get("set_code", ""),
            r.get("marks_obtained", 0),
            total_marks,
            f"{r.get('percentage', 0):.2f}%",
            wrong,
            str(scanned),
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def export_results_pdf(
    results: List[dict],
    exam_title: str,
    total_marks: int,
    stats: dict,
) -> io.BytesIO:
    """Export results to PDF using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(f"<b>{exam_title}</b> - Results", styles["Title"])
    elements.append(title)
    elements.append(Paragraph(f"Total Marks: {total_marks}", styles["Normal"]))
    if stats:
        elements.append(
            Paragraph(
                f"Statistics: Average {stats.get('average', 0):.1f}% | "
                f"Highest {stats.get('highest', 0)} | Lowest {stats.get('lowest', 0)}",
                styles["Normal"],
            )
        )
    elements.append(Paragraph("<br/>", styles["Normal"]))

    data = [["Roll #", "Set", "Marks", "Total", "%", "Wrong"]]
    for r in results:
        wrong = ", ".join(str(x) for x in (r.get("wrong_answers") or []))
        data.append([
            str(r.get("roll_number", "")),
            str(r.get("set_code", "")),
            str(r.get("marks_obtained", 0)),
            str(total_marks),
            f"{r.get('percentage', 0):.2f}%",
            wrong[:30] + "..." if len(wrong) > 30 else wrong,
        ])

    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer
