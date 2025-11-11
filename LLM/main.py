import os
import pandas as pd
from resume_parser import parse_resume
# from spacy_score import dynamic_skill_features
# from spacy_soft_skills import soft_skills_score
from sentence_transformers import SentenceTransformer, util

# Load your fine-tuned model
model_path = "LLM/fine_tuned_resume_model"
model = SentenceTransformer(model_path)

output_file = "Filtered_Data/untrained_data.csv"
os.makedirs("Filtered_Data", exist_ok=True)


def evaluate_and_save(resume_path, job_file):
    # Parse resume
    resume_text = parse_resume(resume_path)

    # Read job description
    with open(job_file, "r", encoding="utf-8") as f:
        job_text = f.read().replace("\n", " ")

    # Compute embeddings
    resume_emb = model.encode(resume_text, convert_to_tensor=True)
    job_emb = model.encode(job_text, convert_to_tensor=True)

    # Compute cosine similarity score
    ml_score = float(util.cos_sim(resume_emb, job_emb).item())
    print(f"Similarity Score From Model: {ml_score:.4f}")

    # soft_skills = soft_skills_score(resume_text)
    # features = dynamic_skill_features(job_text, resume_text, top_n=60)
    # final = ml_score + 0.25*features["coverage"] + 0.1*features["experience_match"] + 0.15*soft_skills["soft_skills_score"]
    
    #print(f"Final Combined Score: {final:.4f} (Coverage: {features['coverage']}, Experience Match: {features['experience_match']})")

    # # Assign label
    # label = 1 if score >= 0.7 else 0

    # # Save to CSV (append if exists)
    # new_row = pd.DataFrame([{
    #     "resume_text": resume_text,
    #     "job_text": job_text,
    #     "label": label
    # }])

    # if os.path.exists(output_file):
    #     new_row.to_csv(output_file, mode="a", header=False, index=False)
    # else:
    #     new_row.to_csv(output_file, index=False)

    # print(f"Saved to {output_file} with label {label}")

# Example usage
evaluate_and_save("Sebastian Grammas .pdf", "mock_job1.txt")