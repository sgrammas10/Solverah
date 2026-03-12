import pandas as pd

# Resume dataset (must have: "resume_string", "label")
resumes = pd.read_csv("resume_dataset.csv")

# Job dataset (must have: "Title", "RoleDescription")
jobs = pd.read_csv("job_postings.csv")

# Normalize case
resumes["label"] = resumes["label"].str.strip().str.lower()
jobs["Title"] = jobs["Title"].str.strip().str.lower()

pairs = []

#  Positive pairs 
for _, r in resumes.iterrows():
    cat = r["label"]
    # Look for jobs with category keyword in position title
    matches = jobs[jobs["Title"].str.contains(cat, case=False, na=False)]
    
    if not matches.empty:
        job = matches.sample(1).iloc[0]
        pairs.append({
            "resume_text": r["resume_string"],
            "job_text": job["RoleDescription"],
            "label": 1
        })


#  Negative pairs 
for _, r in resumes.iterrows():
    cat = r["label"]
    # Jobs NOT containing the category in title
    non_matches = jobs[~jobs["Title"].str.contains(cat, case=False, na=False)]
    
    if not non_matches.empty:
        job = non_matches.sample(1).iloc[0]
        pairs.append({
            "resume_text": r["resume_string"],
            "job_text": job["RoleDescription"],
            "label": 0
        })

# === Save result ===
pairs_df = pd.DataFrame(pairs)
pairs_df.to_csv("../Filtered_data/resume_job_pairs3.csv", index=False)

print(" Created resume_job_pairs3.csv with", len(pairs_df), "pairs")