# action.py
import time
from typing import List, Dict, Optional, AsyncGenerator
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_ollama.llms import OllamaLLM
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from sqlalchemy.orm import Session
from processors import (
    PDFProcessor, BM25SparseVectorGenerator, QdrantManager,
    DocumentLoader, ChainBuilder
)
from utils.encryption import decrypt_api_key
from model import UserModelAssignment, ApiKey, ProviderEnum, User
from qdrant_client.models import Filter
from config import settings
from globals import global_embedding_model

DEBUG = True


class llmProcessor:
    def __init__(self, user_id: Optional[int] = None, db: Optional[Session] = None):
        self.user_id = user_id
        self.db = db
        self.embedding_model = global_embedding_model
        self.LLM = self._get_llm()   # calls the method

        self.prompt = ChatPromptTemplate.from_template("""
            You are a Retrieval-Augmented Generation (RAG) assistant.
            Answer the user's question using the retrieved context below.

            ================ RETRIEVED CONTEXT ================
            <context>
            {context}
            </context>
            ====================================================

            ================ USER QUESTION =====================
            {input}
            ====================================================

            Use ONLY the context when relevant. If the question is casual, answer naturally.
            Use Markdown formatting with headings, lists, and code blocks where appropriate.
        """)

        self.condense_prompt = ChatPromptTemplate.from_template("""
            Convert the follow-up question into a standalone question using the chat history.

            CHAT HISTORY:
            {chat_history}

            FOLLOW-UP QUESTION:
            {input}

            STANDALONE QUESTION:
        """)

        # Sub‑modules
        self.pdf_processor = PDFProcessor(fallback_ocr=True)
        self.doc_loader = DocumentLoader(pdf_processor=self.pdf_processor)
        self.qdrant = QdrantManager()
        self.qdrant.set_embedding_model(self.embedding_model)
        self.chain_builder = ChainBuilder()

    def _get_llm(self):
        """
        Determine the LLM to use:
        1. If user has a custom model assignment, use that (with decrypted API key).
        2. Else, use OpenAI with system credentials (if available).
        3. Else, fallback to Ollama.
        """
        # 1. User-specific assignment
        if self.user_id and self.db:
            assignment = self.db.query(UserModelAssignment).filter(
                UserModelAssignment.user_id == self.user_id,
                UserModelAssignment.is_active == True
            ).first()
            if assignment:
                user = self.db.query(User).filter(User.id == self.user_id).first()
                if user:
                    api_key_record = self.db.query(ApiKey).filter(
                        ApiKey.organization_id == user.organization_id,
                        ApiKey.provider == assignment.provider,
                        ApiKey.is_active == True
                    ).first()
                if api_key_record:
                    api_key = decrypt_api_key(api_key_record.api_key_encrypted).strip()
                    if assignment.provider == ProviderEnum.OPENAI:
                        return ChatOpenAI(
                            model=assignment.model_name,
                            api_key=api_key,
                            temperature=0
                        )
                    elif assignment.provider == ProviderEnum.ANTHROPIC:
                        return ChatAnthropic(
                            model=assignment.model_name,
                            api_key=api_key,
                            temperature=0
                        )
                    elif assignment.provider == ProviderEnum.GOOGLE:
                        return ChatGoogleGenerativeAI(
                            model=assignment.model_name,
                            google_api_key=api_key,
                            temperature=0
                        )

        # 2. Default to OpenAI (if API key is provided)
        if settings.OPENAI_API_KEY:
            if DEBUG:
                print(f"[LLM] Using default OpenAI with model {settings.OPENAI_DEFAULT_MODEL}")
            return ChatOpenAI(
                model=settings.OPENAI_DEFAULT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                temperature=0
            )

        # 3. Ultimate fallback – Ollama
        if DEBUG:
            print("[LLM] No OpenAI API key, falling back to Ollama")
        return OllamaLLM(model="gemma3:12b", temperature=0)

    # ---------- Delegation methods ----------
    def load_process_from_path(self, file_path: str, document_id: str = None, org_id: str = None, file_name: str = None):
        return self.doc_loader.load_from_path(file_path, document_id, org_id, file_name)

    async def ensure_collection_exists(self, org_id: str):
        await self.qdrant.ensure_collection_exists(org_id)

    async def add_documents_to_company_with_metadata(self, org_id: str, documents: List[Document], metadata_list: List[Dict]):
        await self.qdrant.add_documents_with_metadata_list(org_id, documents, metadata_list)

    async def hybrid_search(self, org_id: str, query: str, filters: Optional[Filter] = None,
                      top_k: int = 50, final_k: int = 10) -> List[Document]:
        return await self.qdrant.hybrid_search(org_id, query, filters, top_k, final_k)

    def create_retriever(self, org_id: str, filters: Optional[Filter] = None):
        return lambda q: self.hybrid_search(org_id, q, filters, top_k=50, final_k=10)

    def create_chain(self, org_id: str, filters: Optional[Filter] = None):
        retriever_func = self.create_retriever(org_id, filters)
        return self.chain_builder.build_chain(self.LLM, self.prompt, retriever_func, self.condense_prompt)

    async def get_llm_response(self, chain, user_input, chat_history):
        return await chain.ainvoke({"input": user_input})

    async def astream_response(self, chain, user_input, chat_history) -> AsyncGenerator[str, None]:
        async for chunk in chain.astream({"input": user_input}):
            # Yield thought tokens if model supports it (like deepseek-r1)
            # Some models use <thought>...</thought> tags natively, which will stream as normal text.
            # Langchain might return a dict like {'answer': '...'} or {'context': ...}.
            if 'answer' in chunk:
                yield chunk['answer']
            elif isinstance(chunk, str):
                yield chunk
            elif hasattr(chunk, 'content'):
                yield chunk.content

