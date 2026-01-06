"""
generate_dummy_pipeline_data.py

Creates synthetic intake.csv + PDF/DOCX resumes
so the resume ingestion pipeline can be tested end-to-end
WITHOUT Postgres, R2, or real user data.
"""

from pathlib import Path
import csv
import random
import string

from docx import Document
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

# ---------------- CONFIG ----------------
DATASET_VERSION = "v1"
BASE_DIR = Path("datasets") / DATASET_VERSION
RESUMES_DIR = BASE_DIR / "resumes"
NUM_RECORDS = 4
# ----------------------------------------


def random_name():
    return "".join(random.choices(string.ascii_letters, k=6)).title()


def create_pdf(path: Path, text: str):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    y = height - 50
    for line in text.split("\n"):
        c.drawString(50, y, line)
        y -= 14
    c.save()


def create_docx(path: Path, text: str):
    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    doc.save(path)


def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)

    intake_path = BASE_DIR / "intake.csv"

    rows = []

    for i in range(1, NUM_RECORDS + 1):
        first = random_name()
        last = random_name()
        state = random.choice(["NY", "CA", "TX", "MA"])

        if i % 2 == 0:
            filename = f"resume_{i}.docx"
            create_docx(
                RESUMES_DIR / filename,
                f"""
{first} {last}
Software Engineer

Experience
- Built scalable backend systems
- Worked with Python, APIs, and databases

Education
B.S. Computer Science

Skills
Python, SQL, Docker, AWS
""".strip(),
            )
        else:
            filename = f"resume_{i}.pdf"
            create_pdf(
                RESUMES_DIR / filename,
                f"""
{first} {last}
Machine Learning Engineer

Experience
- Trained ML models
- Processed large datasets

Education
B.S. Computer Science

Skills
Python, PyTorch, Pandas
""".strip(),
            )

        rows.append({
            "id": i,
            "resume_key": filename,
            "state": state,
        })

    with intake_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "resume_key", "state"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("✅ Dummy pipeline data created")
    print(f"  → {intake_path}")
    print(f"  → {RESUMES_DIR} ({NUM_RECORDS} files)")


if __name__ == "__main__":
    main()