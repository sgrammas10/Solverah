from sentence_transformers import SentenceTransformer, util
import pandas as pd
import json
import re

MAX_TOTAL_LEN = 20000        # Max chars for final model text
MAX_JOB_TEXT_LEN = 4000


jobs_path = "zensearchData/job_postings.csv"
model_path = "LLM/fine_tuned_resume_model"
model = SentenceTransformer(model_path)

def sanitize_job_text(raw: str) -> str:
    """Sanitizes job description text before sending to the ML model."""

    if not isinstance(raw, str):
        return ""

    text = raw.strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[^\x09\x0A\x20-\x7E]", "", text)  # strip weird control chars

    if len(text) > MAX_JOB_TEXT_LEN:
        text = text[:MAX_JOB_TEXT_LEN]

    return text

def prepare_profile_text(raw_text: str) -> str:
    """
    Sanitizes and bounds raw text passed from the frontend before
    sending it into the ML model.
    The frontend has already removed PII and formatted sections.
    """
    # Ensure it's a string
    if not isinstance(raw_text, str):
        return ""
    # Strip leading/trailing whitespace
    text = raw_text.strip()
    # Normalize CRLF → LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive blank lines (limit 2 in a row)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove weird control characters except tab/newline
    text = re.sub(r"[^\x09\x0A\x20-\x7E]", "", text)
    # Global length cap
    if len(text) > MAX_TOTAL_LEN:
        text = text[:MAX_TOTAL_LEN]

    return text

#currently not being used anymore
def parse_profile_pipeline(profile_pipeline_str):
    """
    Parses the profile pipeline JSON string into a combined text string for the model.
    Expects a JSON array of objects with 'section' and 'content' fields.
    """
    try:
        sections = json.loads(profile_pipeline_str)
        if not isinstance(sections, list):
            raise ValueError("Expected a list of sections")
    except Exception as e:
        print(f"[parse_profile_pipeline] JSON decode error: {e}")
        return str(profile_pipeline_str)  # fallback to raw

    # Build the combined string
    combined_text = "\n\n".join(
        f"{item.get('section', 'Unknown Section')}:\n{item.get('content', '')}".strip()
        for item in sections
    )
    return combined_text

def profile_to_model(profile_text, job_text):
    """Computes the ML similarity score between profile and job texts."""
    try:
        profile_emb = model.encode(profile_text, convert_to_tensor=True)
        job_emb = model.encode(job_text, convert_to_tensor=True)

        # Compute cosine similarity score
        ml_score = float(util.cos_sim(profile_emb, job_emb).item())

        return ml_score
    except Exception as e:
        # Log minimal info, not the full texts
        print(f"[profile_to_model] Error during encoding/scoring: {e}")
        return 0.0  # or some neutral default that might need to be changed


def sorted_mlscores(profile_text):
    """Returns a list of (job_id, score, job_text) tuples sorted by score desc."""
    # print(profile_json)
    # profile_text = parse_profile_pipeline(profile_json)
    profile_text = prepare_profile_text(profile_text)

    # If we end up with nothing useful, short-circuit
    if not profile_text:
        return []
    
    jobs_df = pd.read_csv(jobs_path)
    scores = []

    for _, row in jobs_df.iterrows():
        job_text = row['RoleDescription']
        score = profile_to_model(profile_text, job_text)
        scores.append((row['ID'], score, job_text))

    # Sort scores in descending order
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)

    return sorted_scores

