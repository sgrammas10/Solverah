"""Smoke test for end-to-end two-input pipeline flow."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from LLM.jd_input_pipeline import run as jd_run
from LLM.matching.compare import compare_profiles
from LLM.user_input_pipeline.build_model_inputs import build_model_inputs
from LLM.user_input_pipeline.clean_text import clean_raw_resumes
from LLM.user_input_pipeline.extract_text import ExtractOptions, extract_resumes


class TestTwoInputPipelineFlow(unittest.TestCase):
    def test_pipeline_reaches_compare(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_root = Path(temp_dir) / "datasets" / "v1"
            resumes_dir = dataset_root / "resumes"
            resumes_dir.mkdir(parents=True, exist_ok=True)

            resume_path = resumes_dir / "1.txt"
            resume_path.write_text("Skills\n- Python\n", encoding="utf-8")

            intake_path = dataset_root / "intake.csv"
            with intake_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "resume_key", "state"])
                writer.writeheader()
                writer.writerow({"id": 1, "resume_key": "resume.txt", "state": "NY"})

            extract_resumes(ExtractOptions(dataset_root=dataset_root))
            clean_raw_resumes(dataset_root)
            build_model_inputs(dataset_root, dataset_version="v1")

            model_inputs_path = dataset_root / "model_inputs.jsonl"
            self.assertTrue(model_inputs_path.exists())
            with model_inputs_path.open("r", encoding="utf-8") as handle:
                candidate_profile = json.loads(handle.readline())

            jd_dir = Path(temp_dir) / "jd"
            jd_text_dir = jd_dir / "jd_text"
            jd_text_dir.mkdir(parents=True, exist_ok=True)
            jd_csv = jd_dir / "jddata.csv"
            with jd_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id"])
                writer.writeheader()
                writer.writerow({"id": 1})
            jd_text_dir.joinpath("1.txt").write_text(
                "Job Title: Data Analyst\n"
                "Requirements:\n"
                "- 2+ years of experience\n"
                "- Python\n"
                "- SQL\n"
                "Education: Bachelor's degree\n"
                "Certifications: AWS Certified\n"
                "Clearance: US Citizen\n",
                encoding="utf-8",
            )

            original_dataset_path = jd_run.DATASET_PATH
            original_jd_text_dir = jd_run.JD_TEXT_DIR
            try:
                jd_run.DATASET_PATH = jd_csv
                jd_run.JD_TEXT_DIR = jd_text_dir
                jd_profiles = jd_run.parse_csv(jd_csv)
            finally:
                jd_run.DATASET_PATH = original_dataset_path
                jd_run.JD_TEXT_DIR = original_jd_text_dir

            self.assertTrue(jd_profiles)
            jd_profile = jd_profiles[0]
            comparison = compare_profiles(jd_profile, candidate_profile)

            self.assertIn("score", comparison)
            self.assertIn("skills", comparison)
            self.assertIn("certifications", comparison)
            self.assertIn("years_experience", comparison)
            self.assertIn("education_match", comparison)
            self.assertIn("clearance_match", comparison)

            self.assertIn("match_ratio", comparison["skills"])
            self.assertIn("match_ratio", comparison["certifications"])


if __name__ == "__main__":
    unittest.main()