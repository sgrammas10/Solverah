"""Generate ML-friendly model_inputs.jsonl from cleaned resumes."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable


from LLM.user_input_pipeline.resume_parser import parse_resume

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_model_inputs(dataset_root: Path, dataset_version: str) -> None:
    clean_path = dataset_root / "resumes_clean.jsonl"
    output_path = dataset_root / "model_inputs.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with clean_path.open("r", encoding="utf-8") as clean_fh, output_path.open(
        "w", encoding="utf-8"
    ) as output_fh:
        for line in clean_fh:
            record = json.loads(line)
            text = record.get("text", "")
            parsed_resume = parse_resume(text)
            model_row = {
                "id": record.get("id"),
                "text": text,
                "state": record.get("state"),
                "resume_key": record.get("resume_key"),
                "dataset_version": dataset_version,
                **parsed_resume,
            }
            output_fh.write(json.dumps(model_row) + "\n")


def build_from_env(version: str = "v1") -> None:
    dataset_root = Path("datasets") / version
    build_model_inputs(dataset_root, dataset_version=version)


if __name__ == "__main__":
    build_from_env()