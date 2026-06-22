from typing import List
from qdrant_client.models import SparseVector
from fastembed import SparseTextEmbedding

_sparse_model = None

class BM25SparseVectorGenerator:
    @staticmethod
    def _get_model():
        global _sparse_model
        if _sparse_model is None:
            _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        return _sparse_model

    @staticmethod
    def generate(text: str) -> SparseVector:
        model = BM25SparseVectorGenerator._get_model()
        res = list(model.embed([text]))[0]
        return SparseVector(indices=res.indices.tolist(), values=res.values.tolist())

    @staticmethod
    def generate_batch(texts: List[str]) -> List[SparseVector]:
        model = BM25SparseVectorGenerator._get_model()
        results = model.embed(texts)
        return [SparseVector(indices=res.indices.tolist(), values=res.values.tolist()) for res in results]