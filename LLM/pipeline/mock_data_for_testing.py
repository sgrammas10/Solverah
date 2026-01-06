#!/usr/bin/env python3
from pathlib import Path
import csv
import random
import string

from docx import Document
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

VERSION = "v1"
BASE = Path("datasets") / VERSION
RESUMES = BASE / "resumes"

N = 4  # generates: 1.pdf, 2.docx, 3.pdf, 4.docx

def rand_word(n=8):
    return "".join(random.choices(string.ascii_letters, k=n))

def create_pdf(path: Path, lines):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    y = height - 60
    for line in lines:
        c.drawString(60, y, line)
        y -= 14
    c.save()

def create_docx(path: Path, lines):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(str(path))

def main():
    RESUMES.mkdir(parents=True, exist_ok=True)
    intake_path = BASE / "intake.csv"

    rows = []
    for i in range(1, N + 1):
        ext = "pdf" if i % 2 == 1 else "docx"
        fname = f"{i}.{ext}"

        text_lines = [
            f"Name: {rand_word(6).title()} {rand_word(7).title()}",
            "Title: Software Engineer",
            "Experience: Built APIs, pipelines, and ML features",
            "Education: B.S. Computer Science",
            "Skills: Python, SQL, Docker, AWS",
        ]

        out_path = RESUMES / fname
        if ext == "pdf":
            create_pdf(out_path, text_lines)
        else:
            create_docx(out_path, text_lines)

        rows.append({"id": i, "resume_key": fname, "state": random.choice(["NY", "CA", "TX", "MA"])})

    with intake_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "resume_key", "state"])
        w.writeheader()
        w.writerows(rows)

    print("Created:")
    print(f"  {intake_path}")
    print(f"  {RESUMES}")
    print("Files:")
    for p in sorted(RESUMES.iterdir()):
        print(f"  - {p}")

if __name__ == "__main__":
    main()
