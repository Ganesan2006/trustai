# processors/qdrant_db.py
import uuid
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    Filter, PointStruct
)
from qdrant_client import QdrantClient
from config import QDRANT_URL, QDRANT_API_KEY
from langchain_core.documents import Document
from .sparse_vector import BM25SparseVectorGenerator

DEBUG = False

class QdrantManager:
    def __init__(self, collection_prefix: str = "org_"):
        # Use cloud URL if provided, otherwise fallback to localhost
        if QDRANT_URL and "cloud.qdrant.io" in QDRANT_URL:
            self.client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                timeout=60
            )
        self.collection_prefix = collection_prefix
        self.embedding_model = None
        self._vector_size = None

    def set_embedding_model(self, model):
        self.embedding_model = model

    def _get_vector_size(self) -> int:
        if self._vector_size is None:
            test_vec = self.embedding_model.embed_query("test")
            self._vector_size = len(test_vec)
        return self._vector_size

    def _get_collection_name(self, org_id: str) -> str:
        return f"{self.collection_prefix}{org_id}"

    def ensure_collection_exists(self, org_id: str):
        col_name = self._get_collection_name(org_id)
        if not self.client.collection_exists(col_name):
            self.client.create_collection(
                collection_name=col_name,
                vectors_config={
                    "dense": VectorParams(size=self._get_vector_size(), distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
                }
            )
            print(f"Created Qdrant collection for org {org_id}")

            # ✅ Create payload indexes for filtering fields
            try:
                # Index for access_level (used in filtering)
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name="access_level",
                    field_type="keyword"
                )
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name="department",
                    field_type="keyword"
                )
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name="team",
                    field_type="keyword"
                )
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name="uploaded_by",
                    field_type="keyword"
                )
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name="document_id",
                    field_type="keyword"
                )
                print(f"Payload indexes created for {col_name}")
            except Exception as e:
                print(f"Warning: Could not create payload indexes: {e}")
                
    def add_documents_with_metadata_list(self, org_id: str, documents: List[Document], metadata_list: List[Dict]):
        self.ensure_collection_exists(org_id)
        col_name = self._get_collection_name(org_id)
        points = []
        for doc, meta in zip(documents, metadata_list):
            dense_vec = self.embedding_model.embed_query(doc.page_content)
            sparse_vec = BM25SparseVectorGenerator.generate(doc.page_content)
            payload = {"text": doc.page_content}
            for key, value in meta.items():
                if value is not None and value != "":
                    payload[key] = value
            for key, value in doc.metadata.items():
                if key not in payload and value is not None and value != "":
                    payload[key] = value
            point_id = meta.get("chunk_id", str(uuid.uuid4()))
            point = PointStruct(id=point_id, vector={"dense": dense_vec, "sparse": sparse_vec}, payload=payload)
            points.append(point)
        if points:
            self.client.upsert(collection_name=col_name, points=points)
            if DEBUG:
                print(f"Added {len(points)} chunks to org {org_id}")

    def hybrid_search(self, org_id: str, query: str, q_filter: Optional[Filter] = None,
                      top_k: int = 20, final_k: int = 5) -> List[Document]:
        col_name = self._get_collection_name(org_id)
        if not self.client.collection_exists(col_name):
            return []
        MIN_SIMILARITY = 0.65
        dense_vec = self.embedding_model.embed_query(query)
        dense_results_raw = self.client.query_points(collection_name=col_name, query=dense_vec, query_filter=q_filter, limit=top_k, using="dense").points
        dense_results = [hit for hit in dense_results_raw if hit.score >= MIN_SIMILARITY]
        sparse_vec = BM25SparseVectorGenerator.generate(query)
        sparse_results = []
        try:
            sparse_results_raw = self.client.query_points(collection_name=col_name, query=sparse_vec, query_filter=q_filter, limit=top_k, using="sparse").points
            sparse_results = [hit for hit in sparse_results_raw if hit.score >= MIN_SIMILARITY]
        except Exception as e:
            print(f"Sparse error: {e}")
        if len(sparse_results) == 0 and len(dense_results) > 0:
            return [Document(page_content=hit.payload["text"], metadata=hit.payload) for hit in dense_results[:final_k]]
        rrf_k = 60
        scores = {}
        for rank, hit in enumerate(dense_results):
            scores[hit.id] = scores.get(hit.id, 0) + 1.0 / (rrf_k + rank + 1)
        for rank, hit in enumerate(sparse_results):
            scores[hit.id] = scores.get(hit.id, 0) + 1.0 / (rrf_k + rank + 1)
        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        payload_map = {}
        for hit in dense_results + sparse_results:
            if hit.id not in payload_map:
                payload_map[hit.id] = (hit.payload["text"], hit.payload)
        
        fused_docs = []
        for doc_id, rrf_score in fused:      # ← rrf_score is defined here
            if doc_id in payload_map:
                text, meta = payload_map[doc_id]
                meta["score"] = rrf_score    # ← attach the RRF score
                fused_docs.append(Document(page_content=text, metadata=meta))
        return fused_docs[:final_k]

    def search_by_vector(self, org_id: str, vector: List[float], limit: int = 5, threshold: float = 0.95) -> List[tuple]:
        col_name = self._get_collection_name(org_id)
        if not self.client.collection_exists(col_name):
            return []
        results = self.client.query_points(collection_name=col_name, query=vector, limit=limit, using="dense").points
        return [(hit.id, hit.score, hit.payload) for hit in results if hit.score >= threshold]