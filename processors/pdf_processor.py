# processors/pdf_processor.py
import os
import fitz
from typing import List
from langchain_core.documents import Document
import easyocr
import numpy as np
from PIL import Image
import io

class PDFProcessor:
    def __init__(self, fallback_ocr: bool = True):
        self.fallback_ocr = fallback_ocr
        self.reader = None
        if self.fallback_ocr:
            try:
                self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            except Exception as e:
                print(f"EasyOCR init failed: {e}")

    def _ocr_image(self, image_bytes):
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img_np = np.array(img)
            result = self.reader.readtext(img_np, detail=0, paragraph=True)
            return " ".join(result)
        except Exception as e:
            print(f"OCR error: {e}")
            return ""

    def process_pdf(self, file_path: str, document_id: str, org_id: str, file_name: str) -> List[Document]:
        docs = []
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if not text.strip() and self.fallback_ocr and self.reader:
                    pix = page.get_pixmap()
                    img_bytes = pix.tobytes("png")
                    text = self._ocr_image(img_bytes)
                metadata = {
                    "page": page_num + 1,
                    "source": file_path,
                    "document_id": document_id,
                    "organization_id": org_id,
                    "file_name": file_name, 
                    "confidence": 1.0 if text.strip() else 0.0
                }
                docs.append(Document(page_content=text, metadata=metadata))
            doc.close()
        except Exception as e:
            print(f"PDF error: {e}")
        return docs