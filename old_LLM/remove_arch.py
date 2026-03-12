import pandas as pd
import re

# Load CSV
df = pd.read_csv("Filtered_Data/resume_job_pairs6.csv")

# Define regex pattern (4 digits)
# pattern = r"Applicant Archetype \d{4}\."
pattern = r"Applicant Archetype"

# Replace in every cell of the dataframe
df = df.applymap(lambda x: re.sub(pattern, "", str(x)))

# Save back to CSV
df.to_csv("Filtered_Data/resume_job_pairs6.csv", index=False)
