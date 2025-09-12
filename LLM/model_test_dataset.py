import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, evaluation

# 1. Load held-out test set
test_df = pd.read_csv("Filtered_Data/test_split.csv")

# 2. Convert rows into InputExamples
test_examples = [
    InputExample(texts=[row["resume_text"], row["job_text"]], label=float(row["label"]))
    for _, row in test_df.iterrows()
]

# 3. Load your trained model
model = SentenceTransformer("fine_tuned_resume_model")

# 4. Build evaluator
test_evaluator = evaluation.EmbeddingSimilarityEvaluator.from_input_examples(
    test_examples,
    name="resume-job-test"
)

# 5. Run evaluation
results = test_evaluator(model, output_path="fine_tuned_resume_model")

print("Final test results:", results)
