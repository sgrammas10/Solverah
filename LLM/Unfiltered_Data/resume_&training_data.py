import pandas as pd
import random

#  Load datasets 
# Resume dataset (must have: "Resume_str", "Category")
resumes = pd.read_csv("Resume.csv")

# Job dataset (must have: "job_description", "position_title")
jobs = pd.read_csv("training_data.csv")

# Normalize case
resumes["Category"] = resumes["Category"].str.strip().str.lower()
jobs["position_title"] = jobs["position_title"].str.strip().str.lower()

pairs = []

#  Positive pairs 
for _, r in resumes.iterrows():
    cat = r["Category"]
    # Look for jobs with category keyword in position title
    matches = jobs[jobs["position_title"].str.contains(cat, case=False, na=False)]
    
    if not matches.empty:
        job = matches.sample(1).iloc[0]
        pairs.append({
            "resume_text": r["Resume_str"],
            "job_text": job["job_description"],
            "label": 1
        })

#  Negative pairs 
for _, r in resumes.iterrows():
    cat = r["Category"]
    # Jobs NOT containing the category in title
    non_matches = jobs[~jobs["position_title"].str.contains(cat, case=False, na=False)]
    
    if not non_matches.empty:
        job = non_matches.sample(1).iloc[0]
        pairs.append({
            "resume_text": r["Resume_str"],
            "job_text": job["job_description"],
            "label": 0
        })

#  Save result
pairs_df = pd.DataFrame(pairs)
pairs_df.to_csv("../Filtered_data/resume_job_pairs2.csv", index=False)

print(" Created resume_job_pairs2.csv with", len(pairs_df), "pairs")
