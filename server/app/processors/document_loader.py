# processors/document_loader.py
import os
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .pdf_processor import PDFProcessor

DEBUG = True

class DocumentLoader:
    def __init__(self, pdf_processor: PDFProcessor = None):
        self.pdf_processor = pdf_processor or PDFProcessor(fallback_ocr=True)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    def load_from_path(self, file_path: str, document_id: str, org_id: str, file_name: str) -> List[Document]:
        """
        Load a document from the given file path, process it (PDF with OCR fallback or text),
        split into chunks, and attach metadata including document_id, organization_id, file_name.
        """
        if DEBUG:
            print(f"[DEBUG] Loading document: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            # PDFProcessor already returns Document objects with metadata (page, source, etc.)
            page_docs = self.pdf_processor.process_pdf(file_path, document_id, org_id, file_name)
        else:
            # Handle other file types
            from langchain_community.document_loaders import (
                TextLoader, Docx2txtLoader, UnstructuredWordDocumentLoader,
                UnstructuredMarkdownLoader, UnstructuredFileLoader
            )
            if ext == '.docx':
                loader = Docx2txtLoader(file_path)
            elif ext == '.doc':
                loader = UnstructuredWordDocumentLoader(file_path, mode="elements")
            elif ext == '.txt':
                loader = TextLoader(file_path, encoding='utf-8')
            elif ext == '.md':
                loader = UnstructuredMarkdownLoader(file_path)
            else:
                loader = UnstructuredFileLoader(file_path)
            pages = loader.load()
            # Add required metadata to each page
            for page in pages:
                page.metadata.update({
                    "document_id": document_id,
                    "organization_id": org_id,
                    "file_name": file_name,
                })
            page_docs = pages

        if DEBUG:
            print(f"[DEBUG] Page-level documents count: {len(page_docs)}")

        # Chunk the documents
        chunked = self.text_splitter.split_documents(page_docs)

        if DEBUG:
            print(f"[DEBUG] Chunking produced {len(chunked)} chunks")
            for i, chunk in enumerate(chunked[:5]):
                print(f"[DEBUG] Chunk {i+1}: {chunk.page_content[:200]}... (metadata: {chunk.metadata})")

        return chunked