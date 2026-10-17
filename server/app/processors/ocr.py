# processors/ocr.py
import gc
import threading
import numpy as np
import cv2
from PIL import Image
from pdf2image import convert_from_path
from pypdf import PdfReader
import easyocr
from langchain_core.documents import Document
from typing import List, Optional, Tuple, Union

class OCRProcessor:
    _lock = threading.Lock()
    _reader = None

    def __init__(self, 
                 languages: List[str] = ['en'],
                 gpu: bool = True,
                 text_threshold: float = 0.7,
                 low_text: float = 0.4,
                 paragraph: bool = True,
                 allowlist: Optional[str] = None,
                 blocklist: Optional[str] = None,
                 **reader_kwargs):
        """
        Initialize EasyOCR reader with optimal settings.
        
        Args:
            languages: List of language codes (e.g., ['en'], ['en','fr'])
            gpu: Use GPU acceleration (fallback to CPU if not available)
            text_threshold: Confidence threshold for text detection (default 0.7)
            low_text: Lower bound for text confidence (default 0.4)
            paragraph: Group text into paragraphs (default True)
            allowlist: Restrict characters to this string (e.g., '0123456789')
            blocklist: Exclude characters (e.g., '@#$%')
            **reader_kwargs: Additional EasyOCR Reader parameters
        """
        self.languages = languages
        self.gpu = gpu
        self.text_threshold = text_threshold
        self.low_text = low_text
        self.paragraph = paragraph
        self.allowlist = allowlist
        self.blocklist = blocklist
        self.reader_kwargs = reader_kwargs
        self._ensure_reader()

    def _ensure_reader(self):
        """Lazy initialization of the EasyOCR reader (thread-safe)."""
        if OCRProcessor._reader is None:
            with OCRProcessor._lock:
                if OCRProcessor._reader is None:
                    try:
                        OCRProcessor._reader = easyocr.Reader(
                            self.languages,
                            gpu=self.gpu,
                            verbose=False,
                            **self.reader_kwargs
                        )
                    except Exception as e:
                        # Fallback to CPU if GPU fails
                        if self.gpu:
                            print(f"GPU not available, falling back to CPU: {e}")
                            OCRProcessor._reader = easyocr.Reader(
                                self.languages,
                                gpu=False,
                                verbose=False,
                                **self.reader_kwargs
                            )
                        else:
                            raise RuntimeError("EasyOCR init failed") from e

    def _preprocess_image(self, image: Image.Image) -> np.ndarray:
        """
        Apply preprocessing to improve OCR accuracy.
        Steps: convert to numpy, grayscale, denoise, sharpen, binarize, deskew.
        """
        # Convert PIL to numpy (RGB)
        img_np = np.array(image)
        
        # Convert to grayscale (EasyOCR works best with grayscale)
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np
        
        # Denoise (fastNlMeansDenoising) – reduces noise without blurring edges
        denoised = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
        
        # Sharpen – enhance edges
        kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(denoised, -1, kernel)
        
        # Adaptive thresholding (binarization) – works well for variable lighting
        binary = cv2.adaptiveThreshold(sharpened, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        
        # Optional: deskew (if needed) – detect skew angle and rotate
        # (We'll add a simple deskew; can be disabled if not needed)
        coords = np.column_stack(np.where(binary > 0))
        angle = cv2.minAreaRect(coords)[-1] if coords.size > 0 else 0
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:
            (h, w) = binary.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h),
                                    flags=cv2.INTER_CUBIC,
                                    borderMode=cv2.BORDER_REPLICATE)
        
        return binary

    def _ocr_image(self, image: Union[Image.Image, np.ndarray]) -> str:
        """
        Perform OCR on a single image (PIL or numpy) using preprocessed version.
        """
        self._ensure_reader()
        # Convert PIL to numpy if needed
        if isinstance(image, Image.Image):
            image_np = self._preprocess_image(image)
        else:
            image_np = self._preprocess_image(Image.fromarray(image))
        
        # Run EasyOCR with tuned parameters
        result = OCRProcessor._reader.readtext(
            image_np,
            detail=0,                     # return only text (no boxes/confidence)
            paragraph=self.paragraph,
            text_threshold=self.text_threshold,
            low_text=self.low_text,
            allowlist=self.allowlist,
            blocklist=self.blocklist
        )
        return ' '.join(result)

    def _ocr_image_batch(self, images: List[Image.Image]) -> List[str]:
        """
        Process a batch of images using EasyOCR's built-in batching (faster).
        Note: EasyOCR's readtext_batch is not publicly exposed; we simulate by
        concatenating images? Actually EasyOCR does not support true batching.
        But we can call readtext sequentially; the real speed gain comes from
        GPU parallelism. For true batching, we would need to reshape images
        into a single tensor – complex. Here we just loop; the GPU will still
        accelerate each call.
        """
        return [self._ocr_image(img) for img in images]

    def extract_text_from_pdf(self, pdf_path: str,
                              dpi: int = 300,
                              batch_size: int = 4) -> List[Document]:
        """
        Extract text from every page of a PDF using OCR.
        
        Args:
            pdf_path: Path to the PDF file.
            dpi: Resolution for PDF to image conversion (higher = better OCR).
            batch_size: Number of pages to process in a batch (for memory/GPU).
        Returns:
            List of LangChain Document objects, one per page.
        """
        self._ensure_reader()
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)
        docs = []
        
        # Convert all pages to images upfront (could be memory heavy for large PDFs)
        # Alternative: process in batches
        for start in range(0, num_pages, batch_size):
            end = min(start + batch_size, num_pages)
            images = convert_from_path(
                pdf_path,
                first_page=start+1,
                last_page=end,
                dpi=dpi,
                fmt='JPEG'
            )
            # Process batch
            for page_num, img in enumerate(images, start=start+1):
                try:
                    text = self._ocr_image(img)
                    if text.strip():
                        docs.append(Document(
                            page_content=text.strip(),
                            metadata={"page": page_num, "source": pdf_path}
                        ))
                finally:
                    img.close()
                    gc.collect()
        
        return docs