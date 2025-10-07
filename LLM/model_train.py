import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split

#  1. Load  dataset 
df = pd.read_csv("Filtered_Data/resume_job_pairs6.csv")

#  2. Split into train, validation, and test 
# First split: train vs temp (val + test)
train_df, temp_df = train_test_split(df, test_size=0.2, stratify=df["label"], random_state=42)

# Second split: temp into validation and test (50/50)
val_df, test_df = train_test_split(temp_df, test_size=0.5, stratify=temp_df["label"], random_state=42)

print("Train size:", len(train_df))
print("Validation size:", len(val_df))
print("Test size:", len(test_df))

# Save test set for later evaluation
test_df.to_csv("Filtered_Data/test_split.csv", index=False)

#  3. Convert rows into InputExamples 
train_examples = [
    InputExample(texts=[row["resume_text"], row["job_text"]], label=float(row["label"]))
    for _, row in train_df.iterrows()
]

val_examples = [
    InputExample(texts=[row["resume_text"], row["job_text"]], label=float(row["label"]))
    for _, row in val_df.iterrows()
]

#  4. Load pretrained sentence transformer 
model = SentenceTransformer("all-MiniLM-L6-v2")

#  5. Create dataloaders 
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)

# Loss function for similarity learning
train_loss = losses.CosineSimilarityLoss(model)

# Validation evaluator
evaluator = evaluation.EmbeddingSimilarityEvaluator.from_input_examples(val_examples, name="resume-job-val")

#  6. Fine-tune 
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    evaluator=evaluator,
    epochs=4,
    warmup_steps=63,              # ~10% of total steps
    evaluation_steps=100-120,     # ~half an epoch
    output_path="fine_tuned_resume_model",
    use_amp=True
)

print(" Training complete! Model saved to fine_tuned_resume_model/")
print(" Held-out test set saved to Filtered_Data/test_split.csv")
