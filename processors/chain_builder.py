from typing import Callable, List
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from pydantic import Field

class SimpleRetriever(BaseRetriever):
    func: Callable = Field(description="The function to retrieve documents")
    class Config:
        arbitrary_types_allowed = True
    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        return self.func(query)
    async def _aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        return self._get_relevant_documents(query, **kwargs)

class ChainBuilder:
    @staticmethod
    def create_retriever_func(qdrant_manager, org_id: str, filters: dict):
        return lambda query, **kwargs: qdrant_manager.hybrid_search(org_id, query, filters, top_k=20, final_k=5)

    @staticmethod
    def build_chain(llm, prompt, retriever_func, condense_prompt):
        lc_retriever = SimpleRetriever(func=retriever_func)
        combine_docs_chain = create_stuff_documents_chain(llm, prompt)
        return create_retrieval_chain(lc_retriever, combine_docs_chain)
    