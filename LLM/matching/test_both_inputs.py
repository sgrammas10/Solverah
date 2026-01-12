"""Smoke test for end-to-end two-input pipeline flow."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from LLM.jd_input_pipeline import run as jd_run
from LLM.matching.compare import compare_profiles
from LLM.user_input_pipeline.build_model_inputs import build_model_inputs
from LLM.user_input_pipeline.clean_text import clean_raw_resumes
from LLM.user_input_pipeline.extract_text import ExtractOptions, extract_resumes


class TestTwoInputPipelineFlow(unittest.TestCase):
    def test_pipeline_reaches_compare(self) -> None:
        dataset_root = Path("datasets") / "v1"
        intake_path = dataset_root / "intake.csv"
        jd_csv = dataset_root / "jddata.csv"
        jd_text_dir = dataset_root / "jd_text"
        resumes_dir = dataset_root / "resumes"

        if not intake_path.exists():
            raise unittest.SkipTest("datasets/v1/intake.csv not found")
        if not jd_csv.exists():
            raise unittest.SkipTest("datasets/v1/jddata.csv not found")
        if not jd_text_dir.exists():
            raise unittest.SkipTest("datasets/v1/jd_text not found")
        if not resumes_dir.exists():
            raise unittest.SkipTest("datasets/v1/resumes not found")

        extract_resumes(ExtractOptions(dataset_root=dataset_root))
        clean_raw_resumes(dataset_root)
        build_model_inputs(dataset_root, dataset_version="v1")

        model_inputs_path = dataset_root / "model_inputs.jsonl"
        if not model_inputs_path.exists():
            raise unittest.SkipTest("model_inputs.jsonl not generated")

        with model_inputs_path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline().strip()
            if not first_line:
                raise unittest.SkipTest("model_inputs.jsonl is empty")
            candidate_profile = json.loads(first_line)

        jd_profiles = jd_run.parse_csv(jd_csv)
        if not jd_profiles:
            raise unittest.SkipTest("No job descriptions parsed from jddata.csv")

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