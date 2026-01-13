import boto3, os
from dotenv import load_dotenv
from pathlib import Path


env_path = Path(__file__).resolve().parent / ".env"

load_dotenv()

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
    region_name="auto",
)

bucket = os.environ["S3_BUCKET_NAME"]

obj = s3.get_object(
    Bucket=bucket,
    Key="intake/43da82b0-cdde-466b-b422-04ef39f1c116/resume.pdf",
)

raw_bytes = obj["Body"].read()
print(f"Read {len(raw_bytes)} bytes from S3 object")