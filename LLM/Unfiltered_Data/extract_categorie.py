import pandas as pd

# Load your dataset (adjust path if needed)
df = pd.read_csv("UpdatedResumeDataSet.csv")  

# Extract unique categories
categories = df["Category"].unique().tolist()

# Print them
print("Unique Categories:")
for c in categories:
    print("-", c)

print(f"\nTotal categories: {len(categories)}")
