# # processors/zoho_ocr.py
# import requests
# import base64
# import os

# ZOHO_CATALYST_PROJECT_ID = os.getenv("ZOHO_CATALYST_PROJECT_ID")
# ZOHO_CATALYST_PROJECT_KEY = os.getenv("ZOHO_CATALYST_PROJECT_KEY")
# ZOHO_CATALYST_ENVIRONMENT = os.getenv("ZOHO_CATALYST_ENVIRONMENT", "development")

# def zoho_ocr_from_bytes(image_bytes: bytes, language: str = "eng") -> str:
#     """
#     Calls Zoho Catalyst Zia OCR API directly.
#     """
#     # API endpoint (adjust version if needed)
#     url = f"https://catalyst.zoho.com/api/v1/project/{ZOHO_CATALYST_PROJECT_ID}/zia/ocr"

#     headers = {
#         "Authorization": f"Zoho-oauthtoken {ZOHO_CATALYST_PROJECT_KEY}",  # or use Basic auth? check Zoho docs
#         "Content-Type": "application/json"
#     }

#     # Encode image to base64
#     encoded_image = base64.b64encode(image_bytes).decode("utf-8")

#     payload = {
#         "image": encoded_image,
#         "language": language   # e.g., "eng", "eng+fra"
#     }

#     response = requests.post(url, json=payload, headers=headers)
#     if response.status_code == 200:
#         return response.json().get("text", "")
#     else:
#         raise Exception(f"Zoho OCR failed: {response.status_code} - {response.text}")