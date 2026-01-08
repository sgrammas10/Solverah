"""Basic tests for job description parsing pipeline."""
from __future__ import annotations

import unittest

from .run import detect_columns, parse_job_description


class TestJobDescriptionPipeline(unittest.TestCase):
    def test_detect_columns(self) -> None:
        headers = ["JD_ID", "job_description"]
        id_col, text_col = detect_columns(headers)
        self.assertEqual(id_col, "JD_ID")
        self.assertEqual(text_col, "job_description")

    def test_parse_job_description_keys(self) -> None:
        text = (
            "Job Title: Data Analyst\n"
            "Requirements:\n"
            "- 3+ years of experience\n"
            "- Experience with SQL, Python, and Tableau\n"
            "- Bachelor\'s degree required\n"
            "Clearance: US Citizen\n"
        )
        parsed = parse_job_description(text, 1)
        self.assertEqual(parsed["id"], 1)
        self.assertIn("years_experience", parsed)
        self.assertIn("skills", parsed)
        self.assertIn("experience", parsed)
        self.assertEqual(parsed["clearances_or_work_auth"], "Clearance: US Citizen")


if __name__ == "__main__":
    unittest.main()