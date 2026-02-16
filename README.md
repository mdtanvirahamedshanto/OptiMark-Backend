# OptiMark Backend

**Automated OMR (Optical Mark Recognition) Grading System** — A FastAPI backend that allows teachers to upload images of OMR sheets, processes them using OpenCV, and generates results based on a predefined answer key.

---

## Features

- **JWT Authentication** — Secure register and login for teachers
- **Exam Management** — Create exams with answer keys (multiple sets: A, B, C, D)
- **OMR Scanning** — Upload OMR sheet images, auto-detect bubbles, grade against answer key
- **Low-Light Support** — CLAHE and adaptive thresholding for mobile photos
- **PostgreSQL** — Async SQLAlchemy with proper models and relationships

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Database | PostgreSQL (async via SQLAlchemy + asyncpg) |
| Computer Vision | OpenCV, NumPy |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Validation | Pydantic |

---

## Prerequisites

- **Python** 3.9+
- **PostgreSQL** 12+
- **Virtual environment** (recommended)

---

## Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, routes
│   ├── config.py            # Pydantic settings (env vars)
│   ├── database.py          # Async SQLAlchemy engine & session
│   ├── models.py            # User, Exam, AnswerKey, Result
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── auth.py              # JWT & password hashing
│   ├── dependencies.py      # get_current_user (JWT dependency)
│   ├── routers/
│   │   ├── auth.py          # POST /auth/register, /auth/login
│   │   └── exams.py         # POST /exams/create, /exams/{id}/scan
│   └── utils/
│       └── omr_engine.py     # OMR processing (OpenCV)
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/            # Migration scripts
├── uploads/                 # Scanned OMR images (created at runtime)
├── requirements.txt
├── .env.example
├── run.py
└── README.md
```

---

## Installation & Setup

### 1. Clone and enter the project

```bash
cd backend
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment configuration

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (async) | `postgresql+asyncpg://user:pass@localhost:5432/optimark` |
| `SECRET_KEY` | JWT signing key (use a strong random value) | `your-super-secret-key` |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry | `30` |
| `UPLOAD_DIR` | Directory for scanned images | `uploads` |
| `MAX_UPLOAD_SIZE_MB` | Max image size (MB) | `10` |

### 5. Create PostgreSQL database

```bash
createdb optimark
```

Ensure the user in `DATABASE_URL` has access to this database.

### 6. Run the server

```bash
python run.py
```

Or with uvicorn directly:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **API**: http://localhost:8000  
- **Swagger docs**: http://localhost:8000/docs  
- **ReDoc**: http://localhost:8000/redoc  

---

## API Endpoints

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | No | Register new user |
| POST | `/auth/login` | No | Login, returns JWT |

### Exams

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/exams/create` | Yes (Bearer) | Create exam + answer key |
| POST | `/exams/{exam_id}/scan` | Yes (Bearer) | Upload OMR image, process & grade |

---

## API Usage Examples

### 1. Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "teacher@school.com", "password": "securepass123"}'
```

### 2. Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "teacher@school.com", "password": "securepass123"}'
```

Response: `{"access_token": "...", "token_type": "bearer"}`

### 3. Create exam with answer key

```bash
curl -X POST http://localhost:8000/exams/create \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Physics Midterm 2024",
    "subject_code": "PHY101",
    "total_questions": 60,
    "answer_key": [
      {"set_code": "A", "question_no": 1, "correct_option": 2},
      {"set_code": "A", "question_no": 2, "correct_option": 0},
      {"set_code": "B", "question_no": 1, "correct_option": 1}
    ]
  }'
```

`correct_option`: 0 = A, 1 = B, 2 = C, 3 = D

### 4. Scan OMR sheet

```bash
curl -X POST http://localhost:8000/exams/1/scan \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/omr_sheet.jpg"
```

Response includes: `roll_number`, `set_code`, `marks_obtained`, `wrong_answers`, `percentage`, `answers`, `success`, `message`.

---

## Database Models

| Model | Key Fields |
|-------|------------|
| **User** | id, email, hashed_password, is_subscribed |
| **Exam** | id, teacher_id, name, subject_code, total_questions |
| **AnswerKey** | id, exam_id, set_code, question_no, correct_option (0–3) |
| **Result** | id, exam_id, roll_number, set_code, marks_obtained, wrong_answers, percentage, uploaded_image_url |

---

## OMR Engine

The `omr_engine.py` module handles:

1. **Corner markers** — `cv2.findContours` to find 4 large square markers
2. **Perspective correction** — `cv2.getPerspectiveTransform` + `cv2.warpPerspective` for alignment
3. **Bubble detection** — Grid-based pixel counting (dark pixel ratio ≥ 35%)
4. **Low-light** — CLAHE and adaptive thresholding

### Assumed OMR layout

- **Header**: Class (A–D), Roll (6 digits), Subject Code (4 digits), Set Code (A–D)
- **Body**: 60 MCQ questions, 4 options each (0–3 = A–D)

### Customization

Edit `app/utils/omr_engine.py` to match your sheet:

- `SHEET_WIDTH`, `SHEET_HEIGHT` — Warped image size
- `BUBBLE_FILL_THRESHOLD` — Sensitivity (lower = more sensitive)
- `header_height`, `grid_top`, `grid_left` — Region positions

---

## Migrations (Alembic)

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Activate venv and run `pip install -r requirements.txt` |
| Database connection error | Check `DATABASE_URL`, PostgreSQL is running, database exists |
| OMR detection fails | Ensure image has clear corner markers; tune constants in `omr_engine.py` |
| 401 Unauthorized | Use valid JWT in `Authorization: Bearer <token>` header |

---

## License

MIT
