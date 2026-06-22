# globals.py
from langchain_ollama.embeddings import OllamaEmbeddings

# Initialize the embedding model once globally
print("[Init] Initializing OllamaEmbeddings (nomic-embed-text) to match existing vector dimensions...")
global_embedding_model = OllamaEmbeddings(model="nomic-embed-text")
print("[Init] Model initialized successfully.")
