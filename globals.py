# globals.py
from langchain_community.embeddings import HuggingFaceEmbeddings

# Initialize the embedding model once globally
print("[Init] Initializing HuggingFace open-source embedding model (all-MiniLM-L6-v2) for production...")
global_embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
print("[Init] Model initialized successfully.")
