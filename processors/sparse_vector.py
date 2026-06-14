from collections import defaultdict
from qdrant_client.models import SparseVector

class BM25SparseVectorGenerator:
    @staticmethod
    def generate(text: str) -> SparseVector:
        words = text.lower().split()
        freq = defaultdict(int)
        for w in words:
            freq[w] += 1
        # Assign a unique integer to each distinct word
        word_to_idx = {}
        idx = 0
        for word in freq.keys():
            word_to_idx[word] = idx
            idx += 1
        indices = []
        values = []
        for word, count in freq.items():
            indices.append(word_to_idx[word])
            values.append(count)
        return SparseVector(indices=indices, values=values)