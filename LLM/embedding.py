from langchain_community.embeddings import OllamaEmbeddings
from sklearn.metrics.pairwise import cosine_similarity

# Load Ollama embeddings model
def embed_and_compare(resume_text, job_text):
    embeddings = OllamaEmbeddings(model="nomic-embed-text")


    # resume_text = "Software engineer with 5 years of Python and ML experience on AWS."
    # job_text = "Looking for a backend engineer with strong Python and AWS cloud background."

    # Generate embeddings
    resume_emb = embeddings.embed_query(resume_text)
    job_emb = embeddings.embed_query(job_text)

    # Compute similarity
    similarity = cosine_similarity([resume_emb], [job_emb])[0][0]

    print(f"Resume ↔ Job Similarity: {similarity:.4f}")


