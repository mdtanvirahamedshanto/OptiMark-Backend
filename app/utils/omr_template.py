"""Generate standardized OMR sheet PDF template."""

import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def generate_omr_template_pdf(
    exam_title: str = "OMR Answer Sheet",
    subject_code: str = "",
    total_questions: int = 60,
    questions_per_column: int = 15,
    options_per_question: int = 4,
) -> io.BytesIO:
    """
    Generate a printable OMR sheet PDF.
    Layout: Header (title, subject), Roll number zone, Set code, MCQ grid.
    """
    buffer = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    # Margins
    margin_left = 15 * mm
    margin_top = 15 * mm
    content_width = width - 2 * margin_left
    content_height = height - 2 * margin_top

    # --- Header ---
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - margin_top - 8 * mm, exam_title)
    if subject_code:
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - margin_top - 14 * mm, f"Subject: {subject_code}")

    # --- Corner markers (black squares for alignment) ---
    marker_size = 8 * mm
    corners = [
        (margin_left, height - margin_top - 25 * mm),
        (width - margin_left - marker_size, height - margin_top - 25 * mm),
        (width - margin_left - marker_size, margin_top + 25 * mm),
        (margin_left, margin_top + 25 * mm),
    ]
    for x, y in corners:
        c.setFillColor(colors.black)
        c.rect(x, y, marker_size, marker_size, fill=1, stroke=0)

    # --- Roll Number zone (6 digits, 0-9 each) ---
    roll_y = height - margin_top - 45 * mm
    c.setFont("Helvetica", 10)
    c.drawString(margin_left, roll_y + 6 * mm, "Roll Number:")
    roll_box_w = content_width * 0.35
    roll_box_h = 12 * mm
    digit_w = roll_box_w / 6
    digit_h = roll_box_h / 10
    for col in range(6):
        for row in range(10):
            x = margin_left + col * digit_w + 1
            y = roll_y - row * digit_h
            c.rect(x, y, digit_w - 1, digit_h - 1, fill=0, stroke=1)
            c.setFont("Helvetica", 6)
            c.drawCentredString(x + (digit_w - 1) / 2, y + (digit_h - 1) / 2 - 2, str(row))
            c.setFont("Helvetica", 10)

    # --- Set Code zone (A, B, C, D or ক, খ, গ, ঘ) ---
    set_x = margin_left + content_width * 0.65
    c.drawString(set_x, roll_y + 6 * mm, "Set:")
    set_codes = ["A", "B", "C", "D"]
    set_w = 12 * mm
    for i, code in enumerate(set_codes):
        x = set_x + i * set_w
        c.rect(x, roll_y, set_w - 1, roll_box_h - 2 * mm, fill=0, stroke=1)
        c.drawCentredString(x + (set_w - 1) / 2, roll_y + (roll_box_h - 2 * mm) / 2 - 2, code)

    # --- MCQ Grid (60 questions, 4 columns of 15) ---
    grid_top = roll_y - 25 * mm
    num_cols = (total_questions + questions_per_column - 1) // questions_per_column
    grid_width = content_width
    grid_height = grid_top - margin_top - 10 * mm
    block_h = grid_height / questions_per_column
    block_w = grid_width / num_cols
    opt_h = block_h / options_per_question
    opt_w = block_w / options_per_question
    opt_labels = ["A", "B", "C", "D"][:options_per_question]

    for q in range(total_questions):
        col_idx = q // questions_per_column
        row_idx = q % questions_per_column
        x_base = margin_left + col_idx * block_w
        y_base = grid_top - (row_idx + 1) * block_h

        # Question number
        c.setFont("Helvetica", 8)
        c.drawString(x_base + 2, y_base + block_h - 4, str(q + 1))

        for opt in range(options_per_question):
            x = x_base + 4 * mm + opt * opt_w
            y = y_base + (options_per_question - 1 - opt) * opt_h
            c.circle(x + opt_w / 2 - 1, y + opt_h / 2 - 1, 2 * mm, fill=0, stroke=1)
            c.drawString(x + opt_w - 4, y + opt_h / 2 - 2, opt_labels[opt])

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
