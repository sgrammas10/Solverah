from sentence_transformers import SentenceTransformer, util
import pandas as pd
import json

jobs_path = "../zensearchData/job_postings.csv"
model_path = "LLM/fine_tuned_resume_model"
model = SentenceTransformer(model_path)

def parse_profile_pipeline(profile_pipeline_str):
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
    profile_emb = model.encode(profile_text, convert_to_tensor=True)
    job_emb = model.encode(job_text, convert_to_tensor=True)

    # Compute cosine similarity score
    ml_score = float(util.cos_sim(profile_emb, job_emb).item())

    return ml_score


def sorted_mlscores(profile_json):
    profile_text = parse_profile_pipeline(profile_json)
    jobs_df = pd.read_csv(jobs_path)
    scores = []

    for _, row in jobs_df.iterrows():
        job_text = row['RoleDescription']
        score = profile_to_model(profile_text, job_text)
        scores.append((row['ID'], score, job_text))

    # Sort scores in descending order
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)

    return sorted_scores

