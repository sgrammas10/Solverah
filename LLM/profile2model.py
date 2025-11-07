from sentence_transformers import SentenceTransformer, util
import pandas as pd


model_path = "LLM/fine_tuned_resume_model"
model = SentenceTransformer(model_path)

jobs_path = "../zensearchData/job_postings.csv"

def profile_to_model(profile_text, job_text):
    profile_emb = model.encode(profile_text, convert_to_tensor=True)
    job_emb = model.encode(job_text, convert_to_tensor=True)

    # Compute cosine similarity score
    ml_score = float(util.cos_sim(profile_emb, job_emb).item())

    return ml_score


def sorted_mlscores(profile_text):
    jobs_df = pd.read_csv(jobs_path)
    scores = []

    for _, row in jobs_df.iterrows():
        job_text = row['RoleDescription']
        score = profile_to_model(profile_text, job_text)
        scores.append((row['ID'], score))

    # Sort scores in descending order
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)

    return sorted_scores

