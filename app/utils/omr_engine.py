"""
OptiMark OMR Engine - Robust OMR processing using OpenCV, NumPy, Imutils.

Implements:
- Four corner marker detection (black squares) for Perspective Transform
- Preprocessing: Grayscale, Gaussian Blur, Canny Edge, Adaptive Thresholding
- Zone segmentation: Roll Number (top-left), Set Code, MCQ Grid (60 questions)
- Pixel Counting / Contour method: bubble marked if highest black pixel density in row
- Supports Bengali set codes: ক, খ, গ, ঘ
- Error handling: "No bubbles detected", "Image too blurry"
"""

import cv2
import numpy as np
from imutils.perspective import four_point_transform
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field


# --- Error codes for robust handling ---
class OMRProcessingError(Exception):
    """Base exception for OMR processing errors."""

    pass


class NoBubblesDetectedError(OMRProcessingError):
    """Raised when no bubbles could be detected in the image."""

    pass


class ImageTooBlurryError(OMRProcessingError):
    """Raised when image is too blurry for reliable processing."""

    pass


@dataclass
class OMRResult:
    """Structured result from OMR processing."""

    roll_number: str = ""
    set_code: str = ""
    answers: List[int] = field(default_factory=list)  # 0-3 for each question
    success: bool = False
    error_message: str = ""


# --- OMR Sheet Layout Constants ---
SHEET_WIDTH = 2480
SHEET_HEIGHT = 3508
MARKER_MIN_AREA_RATIO = 0.001
MARKER_MAX_AREA_RATIO = 0.15
QUESTIONS_PER_COLUMN = 15
OPTIONS_PER_QUESTION = 4
TOTAL_QUESTIONS = 60

# Bengali set codes (ক=0, খ=1, গ=2, ঘ=3) - maps index to character
BENGALI_SET_CODES = ["ক", "খ", "গ", "ঘ"]
ENGLISH_SET_CODES = ["A", "B", "C", "D"]

# Blur detection threshold (Laplacian variance) - lower = blurrier
BLUR_THRESHOLD = 100


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _check_image_blur(gray: np.ndarray) -> bool:
    """
    Check if image is too blurry using Laplacian variance.
    Returns True if image is acceptable, False if too blurry.
    """
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return laplacian_var >= BLUR_THRESHOLD


def _preprocess_image(img: np.ndarray) -> np.ndarray:
    """
    Full preprocessing pipeline:
    1. Grayscale
    2. Gaussian Blur (noise reduction)
    3. Adaptive Thresholding
    Also used for edge detection: Canny after Gaussian Blur.
    """
    # Step 1: Grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Step 2: Gaussian Blur - reduces noise for better edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    return blurred


def _find_corner_markers(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Find the four black square corner markers using:
    - Canny Edge Detection
    - Contour detection
    Returns ordered points: top-left, top-right, bottom-right, bottom-left.
    """
    # Adaptive Threshold - robust for varying lighting
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )

    # Canny Edge Detection
    edges = cv2.Canny(gray, 50, 150)

    # Combine: use both for robustness
    combined = cv2.bitwise_or(thresh, edges)
    kernel = np.ones((3, 3), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(
        combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = gray.shape
    total_area = h * w
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if MARKER_MIN_AREA_RATIO * total_area < area < MARKER_MAX_AREA_RATIO * total_area:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                x, y, w_rect, h_rect = cv2.boundingRect(approx)
                aspect = max(w_rect, h_rect) / (min(w_rect, h_rect) + 1e-6)
                if 0.5 < aspect < 2.0:
                    candidates.append((area, approx))

    if len(candidates) < 4:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    markers = [c[1] for c in candidates[:4]]
    pts = np.concatenate(markers)
    ordered = _order_points(pts)
    return ordered.astype(np.float32)


def _warp_perspective(img: np.ndarray, src_pts: np.ndarray) -> np.ndarray:
    """Apply perspective transform for top-down view using imutils."""
    warped = four_point_transform(img, src_pts)
    if warped.shape[:2] != (SHEET_HEIGHT, SHEET_WIDTH):
        warped = cv2.resize(warped, (SHEET_WIDTH, SHEET_HEIGHT))
    return warped


def _get_bubble_density(roi: np.ndarray) -> float:
    """
    Pixel counting: return ratio of dark pixels in ROI.
    Higher = more filled bubble.
    """
    if roi.size == 0:
        return 0.0
    if len(roi.shape) == 3:
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return np.sum(binary > 0) / binary.size


def _detect_marked_option_by_density(
    img: np.ndarray,
    x_start: int,
    y_start: int,
    num_options: int,
    cell_width: int,
    cell_height: int,
) -> int:
    """
    A bubble is 'marked' if it has the highest density of black pixels
    compared to others in the same row.
    Returns 0 to num_options-1, or -1 if ambiguous/none.
    """
    densities = []
    for i in range(num_options):
        x = x_start + i * cell_width
        roi = img[y_start + 2 : y_start + cell_height - 2, x + 2 : x + cell_width - 2]
        densities.append(_get_bubble_density(roi))

    max_density = max(densities)
    if max_density < 0.25:  # No bubble sufficiently filled
        return -1
    max_indices = [i for i, d in enumerate(densities) if d == max_density]
    if len(max_indices) != 1:
        return -1  # Ambiguous
    return max_indices[0]


def _read_roll_number(
    img: np.ndarray,
    x_start: int,
    y_start: int,
    region_width: int,
    region_height: int,
    num_digits: int = 6,
) -> str:
    """
    Read roll number from top-left zone.
    Layout: num_digits columns, each column has 10 rows (0-9).
    """
    cell_w = region_width // num_digits
    cell_h = region_height // 10
    if cell_w < 2 or cell_h < 2:
        return "?" * num_digits

    result = ""
    for digit_pos in range(num_digits):
        x_base = x_start + digit_pos * cell_w
        densities = []
        for opt in range(10):
            y = y_start + opt * cell_h
            roi = img[y + 1 : y + cell_h - 1, x_base + 1 : x_base + cell_w - 1]
            densities.append(_get_bubble_density(roi))
        max_d = max(densities)
        if max_d >= 0.25:
            idx = [i for i, d in enumerate(densities) if d == max_d]
            result += str(idx[0]) if len(idx) == 1 else "?"
        else:
            result += "?"
    return result


def _read_set_code(
    img: np.ndarray,
    x_start: int,
    y_start: int,
    region_width: int,
    region_height: int,
    use_bengali: bool = True,
) -> str:
    """
    Read set code from zone (ক, খ, গ, ঘ or A, B, C, D).
    """
    codes = BENGALI_SET_CODES if use_bengali else ENGLISH_SET_CODES
    num_options = len(codes)
    cell_w = region_width // num_options
    cell_h = region_height
    idx = _detect_marked_option_by_density(
        img, x_start, y_start, num_options, cell_w, cell_h
    )
    return codes[idx] if idx >= 0 else "?"


class OMRProcessor:
    """
    OMR processing class - encapsulates all OMR logic.
    """

    def __init__(
        self,
        sheet_width: int = SHEET_WIDTH,
        sheet_height: int = SHEET_HEIGHT,
        total_questions: int = TOTAL_QUESTIONS,
        use_bengali_set_codes: bool = True,
    ):
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.total_questions = total_questions
        self.use_bengali_set_codes = use_bengali_set_codes

    def process(self, image_path: str | Path) -> OMRResult:
        """
        Main entry: process OMR sheet image.
        Extracts Roll Number, Set Code, and MCQ answers.
        """
        result = OMRResult()

        try:
            img = cv2.imread(str(image_path))
            if img is None:
                result.error_message = f"Could not load image: {image_path}"
                return result

            # Preprocessing
            blurred = _preprocess_image(img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

            # Blur check
            if not _check_image_blur(gray):
                result.error_message = "Image too blurry for reliable processing"
                raise ImageTooBlurryError(result.error_message)

            # Find corner markers and warp
            markers = _find_corner_markers(blurred)
            if markers is None:
                warped = cv2.resize(gray, (self.sheet_width, self.sheet_height))
            else:
                warped = _warp_perspective(img, markers)
                if len(warped.shape) == 3:
                    warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

            h, w = warped.shape

            # --- Zone definitions ---
            header_height = int(h * 0.18)
            grid_top = int(h * 0.22)
            grid_height = h - grid_top - int(h * 0.05)
            grid_width = int(w * 0.88)
            grid_left = int(w * 0.06)

            # Zone 1: Roll Number (top-left)
            roll_region_w = int(grid_width * 0.35)
            roll_region_h = header_height
            roll_x = grid_left
            roll_y = int(h * 0.05)
            roll_region = warped[roll_y : roll_y + roll_region_h, roll_x : roll_x + roll_region_w]
            result.roll_number = _read_roll_number(
                warped, roll_x, roll_y, roll_region_w, roll_region_h, 6
            )

            # Zone 2: Set Code
            set_region_w = int(grid_width * 0.15)
            set_region_x = grid_left + int(grid_width * 0.6)
            set_region = warped[roll_y : roll_y + roll_region_h, set_region_x : set_region_x + set_region_w]
            result.set_code = _read_set_code(
                warped,
                set_region_x,
                roll_y,
                set_region_w,
                roll_region_h,
                self.use_bengali_set_codes,
            )

            # Zone 3: MCQ Grid (60 questions)
            num_cols = (self.total_questions + QUESTIONS_PER_COLUMN - 1) // QUESTIONS_PER_COLUMN
            q_block_h = grid_height // QUESTIONS_PER_COLUMN
            q_block_w = grid_width // num_cols
            opt_h = q_block_h // OPTIONS_PER_QUESTION
            opt_w = q_block_w // OPTIONS_PER_QUESTION

            answers = []
            bubbles_detected = 0
            for q in range(self.total_questions):
                col_idx = q // QUESTIONS_PER_COLUMN
                row_idx = q % QUESTIONS_PER_COLUMN
                x_start = grid_left + col_idx * (grid_width // num_cols)
                y_start = grid_top + row_idx * q_block_h

                marked = _detect_marked_option_by_density(
                    warped, x_start, y_start, OPTIONS_PER_QUESTION, opt_w, opt_h
                )
                if marked >= 0:
                    bubbles_detected += 1
                answers.append(marked)

            result.answers = answers

            if bubbles_detected == 0:
                result.error_message = "No bubbles detected in the image"
                raise NoBubblesDetectedError(result.error_message)

            result.success = True

        except (NoBubblesDetectedError, ImageTooBlurryError):
            result.success = False
        except Exception as e:
            result.error_message = str(e)
            result.success = False

        return result


def process_omr_image(
    image_path: str | Path,
    num_questions: int = 60,
    use_bengali_set_codes: bool = True,
) -> OMRResult:
    """
    Convenience function - process OMR sheet image.
    """
    processor = OMRProcessor(
        total_questions=num_questions,
        use_bengali_set_codes=use_bengali_set_codes,
    )
    return processor.process(image_path)


def grade_omr_result(
    omr_result: OMRResult,
    answer_key: Dict[str, int],
    marks_per_question: float = 1.0,
    negative_marking: float = 0.0,
) -> Tuple[int, List[int], float]:
    """
    Grade OMR result against answer key.
    answer_key: {"1": 0, "2": 2, "3": 1, ...} - question_no (str) -> correct_option (0-3)

    Returns:
        (marks_obtained, wrong_answers_list, percentage)
    """
    correct = 0
    wrong_list = []

    for q_no, marked in enumerate(omr_result.answers, start=1):
        key = str(q_no)
        if key not in answer_key:
            continue
        correct_opt = answer_key[key]
        if marked == correct_opt:
            correct += 1
        elif marked >= 0:
            wrong_list.append(q_no)

    total = len(answer_key)
    marks_obtained = max(
        0,
        correct * marks_per_question - len(wrong_list) * negative_marking
    )
    percentage = (marks_obtained / (total * marks_per_question) * 100) if total > 0 else 0.0

    return int(marks_obtained), wrong_list, round(percentage, 2)
