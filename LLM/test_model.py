from sentence_transformers import SentenceTransformer, util

# Load your fine-tuned model
model = SentenceTransformer("fine_tuned_resume_model")

resume = """Experienced backend engineer skilled in Python, AWS, and cloud architecture.
            Built scalable microservices and deployed on Kubernetes."""
job = "Looking for a backend engineer with strong Python and AWS cloud background."

# Encode both
embeddings = model.encode([resume, job], convert_to_tensor=True)

# Cosine similarity (fit score)
score = util.cos_sim(embeddings[0], embeddings[1]).item()
print("Fit score:", score)
