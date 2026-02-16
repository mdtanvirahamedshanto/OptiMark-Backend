"""
OptiMark OMR Engine - Core image processing and bubble detection logic.

Uses OpenCV for:
- Corner marker detection (cv2.findContours)
- Perspective correction (cv2.getPerspectiveTransform)
- Grid-based bubble detection via pixel counting

Designed to handle slightly low-light mobile photos through:
- CLAHE (Contrast Limited Adaptive Histogram Equalization)
- Adaptive thresholding
- Morphological operations
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field


@dataclass
class OMRResult:
    """Structured result from OMR processing."""

    class_code: str = ""
    roll_number: str = ""
    subject_code: str = ""
    set_code: str = ""
    answers: list[int] = field(default_factory=list)  # 0-3 for each question
    success: bool = False
    error_message: str = ""


# --- OMR Sheet Layout Constants ---
# Standard A4 OMR sheet dimensions (in pixels after perspective correction)
# These can be tuned based on your actual OMR sheet template
SHEET_WIDTH = 2480
SHEET_HEIGHT = 3508

# Corner marker size (approximate ratio of marker to sheet)
MARKER_MIN_AREA_RATIO = 0.001
MARKER_MAX_AREA_RATIO = 0.15

# Bubble detection thresholds
BUBBLE_FILL_THRESHOLD = 0.35  # Min ratio of dark pixels to consider bubble "marked"
BUBBLE_MIN_AREA = 50
BUBBLE_MAX_AREA = 2000

# Grid layout for 60 questions (4 options each, typically 15 questions per column)
QUESTIONS_PER_COLUMN = 15
OPTIONS_PER_QUESTION = 4
TOTAL_QUESTIONS = 60


def _preprocess_for_low_light(img: np.ndarray) -> np.ndarray:
    """
    Enhance image for low-light conditions.
    Uses CLAHE to improve contrast without over-amplifying noise.
    """
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # CLAHE - Contrast Limited Adaptive Histogram Equalization
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    return enhanced


def _find_corner_markers(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Locate the 4 large square corner markers using contour detection.
    Returns ordered points: top-left, top-right, bottom-right, bottom-left.
    """
    # Adaptive threshold - robust for varying lighting
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )

    # Morphological operations to clean up
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # Find contours
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = gray.shape
    total_area = h * w
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Filter by area - markers are large squares
        if MARKER_MIN_AREA_RATIO * total_area < area < MARKER_MAX_AREA_RATIO * total_area:
            # Approximate to polygon - squares have 4 vertices
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                # Check aspect ratio (roughly square)
                x, y, w_rect, h_rect = cv2.boundingRect(approx)
                aspect = max(w_rect, h_rect) / (min(w_rect, h_rect) + 1e-6)
                if 0.5 < aspect < 2.0:
                    candidates.append((area, approx))

    if len(candidates) < 4:
        return None

    # Sort by area descending, take top 4
    candidates.sort(key=lambda x: x[0], reverse=True)
    markers = [c[1] for c in candidates[:4]]

    # Order: top-left, top-right, bottom-right, bottom-left
    def order_points(pts: list) -> np.ndarray:
        pts = np.concatenate(pts)
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left
        rect[2] = pts[np.argmax(s)]   # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right
        rect[3] = pts[np.argmax(diff)]  # bottom-left
        return rect

    ordered = order_points(markers)
    return ordered.astype(np.float32)


def _warp_perspective(img: np.ndarray, src_pts: np.ndarray) -> np.ndarray:
    """
    Apply perspective transform to get a top-down view of the OMR sheet.
    """
    dst_pts = np.array([
        [0, 0],
        [SHEET_WIDTH, 0],
        [SHEET_WIDTH, SHEET_HEIGHT],
        [0, SHEET_HEIGHT]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img, M, (SHEET_WIDTH, SHEET_HEIGHT))
    return warped


def _detect_bubble_marked(roi: np.ndarray) -> bool:
    """
    Pixel counting method: a bubble is marked if the ratio of dark pixels
    exceeds BUBBLE_FILL_THRESHOLD.
    """
    if roi.size == 0:
        return False

    # Use adaptive threshold for the bubble region
    if len(roi.shape) == 3:
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark_ratio = np.sum(binary > 0) / binary.size
    return dark_ratio >= BUBBLE_FILL_THRESHOLD


def _extract_bubble_region(
    img: np.ndarray,
    row: int,
    col: int,
    total_rows: int,
    total_cols: int,
    x_start: int,
    y_start: int,
    cell_width: int,
    cell_height: int,
    padding: int = 2
) -> np.ndarray:
    """Extract a single bubble region from the grid."""
    x = x_start + col * cell_width + padding
    y = y_start + row * cell_height + padding
    w = cell_width - 2 * padding
    h = cell_height - 2 * padding
    return img[y:y + h, x:x + w]


def _detect_marked_option_in_row(
    img: np.ndarray,
    row_start: int,
    col_start: int,
    cell_width: int,
    cell_height: int,
    num_options: int
) -> int:
    """
    For a single question row, check which option (0 to num_options-1) is marked.
    Returns -1 if none or multiple are marked (ambiguous).
    """
    marked_indices = []
    for opt in range(num_options):
        roi = _extract_bubble_region(
            img, 0, opt, 1, num_options,
            col_start, row_start, cell_width, cell_height
        )
        if _detect_bubble_marked(roi):
            marked_indices.append(opt)

    if len(marked_indices) == 1:
        return marked_indices[0]
    return -1


def _read_numeric_bubbles(
    img: np.ndarray,
    num_digits: int,
    options_per_digit: int = 10
) -> str:
    """
    Read numeric bubbles (e.g., roll number 0-9 per digit).
    Layout: num_digits columns, each column has options_per_digit rows (0-9).
    Returns string of detected digits.
    """
    h, w = img.shape[:2]
    if num_digits <= 0 or options_per_digit <= 0:
        return ""

    cell_width = w // num_digits
    cell_height = h // options_per_digit
    if cell_width < 2 or cell_height < 2:
        return "?" * num_digits

    result = ""
    for digit_pos in range(num_digits):
        digit = -1
        for opt in range(options_per_digit):
            x = digit_pos * cell_width
            y = opt * cell_height
            roi = img[y + 1 : y + cell_height - 1, x + 1 : x + cell_width - 1]
            if roi.size > 0 and _detect_bubble_marked(roi):
                if digit >= 0:
                    digit = -1
                    break
                digit = opt
        result += str(digit) if digit >= 0 else "?"
    return result


def _detect_letter_bubble(img: np.ndarray, num_options: int = 4) -> str:
    """Detect single letter/set code (A, B, C, D) from 4 option bubbles."""
    h, w = img.shape[:2]
    if w < num_options:
        return "?"
    cell_width = w // num_options
    letters = "ABCD"
    marked = -1
    for i in range(num_options):
        x = i * cell_width
        roi = img[1 : h - 1, x + 1 : x + cell_width - 1]
        if roi.size > 0 and _detect_bubble_marked(roi):
            if marked >= 0:
                return "?"
            marked = i
    return letters[marked] if marked >= 0 else "?"


def process_omr_image(
    image_path: str | Path,
    num_questions: int = 60,
    questions_per_column: int = 15
) -> OMRResult:
    """
    Main entry point: process an OMR sheet image and extract all data.

    Args:
        image_path: Path to the OMR sheet image
        num_questions: Total MCQ questions (default 60)
        questions_per_column: Questions per column (default 15)

    Returns:
        OMRResult with class_code, roll_number, subject_code, set_code, answers
    """
    result = OMRResult()

    try:
        img = cv2.imread(str(image_path))
        if img is None:
            result.error_message = f"Could not load image: {image_path}"
            return result

        # Step 1: Preprocess for low-light
        gray = _preprocess_for_low_light(img)

        # Step 2: Find corner markers
        markers = _find_corner_markers(gray)
        if markers is None:
            # Fallback: use full image as-is (no perspective correction)
            warped = gray
            # Resize to standard dimensions for consistent processing
            warped = cv2.resize(warped, (SHEET_WIDTH, SHEET_HEIGHT))
        else:
            # Step 3: Apply perspective transform
            warped = _warp_perspective(img, markers)
            if len(warped.shape) == 3:
                warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        # Binary threshold for bubble detection
        _, binary = cv2.threshold(
            warped, 0, 255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        h, w = warped.shape

        # --- Define grid regions (tune these for your OMR template) ---
        # Typical layout: header (class, roll, subject, set) then question grid
        header_height = int(h * 0.15)
        grid_top = int(h * 0.20)
        grid_height = h - grid_top - int(h * 0.05)
        grid_width = int(w * 0.85)
        grid_left = int(w * 0.08)

        # Class (single letter A-D) - approximate region
        class_region = warped[header_height // 2 : header_height, grid_left : grid_left + int(grid_width * 0.1)]
        result.class_code = _detect_letter_bubble(class_region, 4)

        # Roll number (e.g., 6 digits) - approximate region
        roll_region = warped[header_height // 2 : header_height, grid_left + int(grid_width * 0.12) : grid_left + int(grid_width * 0.4)]
        result.roll_number = _read_numeric_bubbles(roll_region, 6)

        # Subject code - often 3-4 digits
        subj_region = warped[header_height // 2 : header_height, grid_left + int(grid_width * 0.45) : grid_left + int(grid_width * 0.6)]
        result.subject_code = _read_numeric_bubbles(subj_region, 4)

        # Set code (A, B, C, D)
        set_region = warped[header_height // 2 : header_height, grid_left + int(grid_width * 0.65) : grid_left + int(grid_width * 0.75)]
        result.set_code = _detect_letter_bubble(set_region, 4)

        # --- MCQ Answers (60 questions, 4 options each) ---
        num_cols = (num_questions + questions_per_column - 1) // questions_per_column
        cell_height = grid_height // (questions_per_column * OPTIONS_PER_QUESTION)
        cell_width = grid_width // (num_cols * OPTIONS_PER_QUESTION)

        answers = []
        for q in range(num_questions):
            col_idx = q // questions_per_column
            row_idx = q % questions_per_column
            # Each question has 4 rows (A,B,C,D)
            base_row = row_idx * OPTIONS_PER_QUESTION
            base_col = col_idx * OPTIONS_PER_QUESTION

            x_start = grid_left + col_idx * (grid_width // num_cols)
            y_start = grid_top + row_idx * (grid_height // questions_per_column)

            # Get cell dimensions for this question block
            q_block_height = (grid_height // questions_per_column)
            q_block_width = grid_width // num_cols
            opt_height = q_block_height // OPTIONS_PER_QUESTION
            opt_width = q_block_width // OPTIONS_PER_QUESTION

            marked = -1
            for opt in range(OPTIONS_PER_QUESTION):
                x = x_start + opt * opt_width
                y = y_start + opt * opt_height
                roi = warped[y + 2 : y + opt_height - 2, x + 2 : x + opt_width - 2]
                if roi.size > 0 and _detect_bubble_marked(roi):
                    if marked >= 0:
                        marked = -1
                        break
                    marked = opt
            answers.append(marked)

        result.answers = answers
        result.success = True

    except Exception as e:
        result.error_message = str(e)
        result.success = False

    return result


def grade_omr_result(
    omr_result: OMRResult,
    answer_key: Dict[Tuple[str, int], int],
    marks_per_question: float = 1.0,
    negative_marking: float = 0.0
) -> Tuple[int, int, float]:
    """
    Grade OMR result against answer key.

    Args:
        omr_result: OMRResult from process_omr_image
        answer_key: Dict mapping (set_code, question_no) -> correct_option (0-3)
        marks_per_question: Marks for each correct answer
        negative_marking: Deduction for wrong answer (e.g., 0.25)

    Returns:
        (marks_obtained, wrong_answers, percentage)
    """
    correct = 0
    wrong = 0

    set_code = omr_result.set_code.upper() if omr_result.set_code else "A"
    for q_no, marked in enumerate(omr_result.answers, start=1):
        key = (set_code, q_no)
        if key not in answer_key:
            continue
        correct_opt = answer_key[key]
        if marked == correct_opt:
            correct += 1
        elif marked >= 0:
            wrong += 1

    total_questions = len([k for k in answer_key if k[0] == set_code])
    marks_obtained = max(
        0,
        correct * marks_per_question - wrong * negative_marking
    )
    percentage = (
        (marks_obtained / (total_questions * marks_per_question) * 100)
        if total_questions > 0 else 0.0
    )

    return int(marks_obtained), wrong, round(percentage, 2)
