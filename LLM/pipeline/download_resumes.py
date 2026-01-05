"""Download raw resumes from R2 using the intake manifest."""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import boto3
import pandas as pd


MIME_EXTENSION_MAP = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


@dataclass
class ResumeDownloader:
    bucket: str
    endpoint_url: str
    access_key: str
    secret_key: str

    def _client(self):
        session = boto3.session.Session()
        return session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

    def _determine_extension(self, resume_key: str, resume_mime: str | None) -> str:
        if resume_mime and resume_mime in MIME_EXTENSION_MAP:
            return MIME_EXTENSION_MAP[resume_mime]
        guess, _ = mimetypes.guess_type(resume_key)
        if guess and guess in MIME_EXTENSION_MAP:
            return MIME_EXTENSION_MAP[guess]
        return Path(resume_key).suffix or ".bin"

    def download(self, intake_csv: Path, output_dir: Path) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        df = pd.read_csv(intake_csv)
        client = self._client()
        for _, row in df.iterrows():
            resume_key = row["resume_key"]
            submission_id = row["id"]
            resume_mime = row.get("resume_mime")
            ext = self._determine_extension(resume_key, resume_mime)
            destination = output_dir / f"{submission_id}{ext}"
            client.download_file(self.bucket, resume_key, str(destination))


def download_from_env(version: str = "v1") -> None:
    required_env = [
        "R2_BUCKET",
        "R2_ENDPOINT_URL",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ]
    missing = [key for key in required_env if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    downloader = ResumeDownloader(
        bucket=os.environ["R2_BUCKET"],
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        access_key=os.environ["R2_ACCESS_KEY_ID"],
        secret_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    dataset_root = Path("datasets") / version
    downloader.download(dataset_root / "intake.csv", dataset_root / "resumes")


if __name__ == "__main__":
    download_from_env()