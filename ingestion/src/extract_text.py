import os
import json
import pdfplumber
import pandas as pd
import pytesseract
from PIL import Image

# Tell pytesseract where Tesseract is installed (adjust if your install path differs)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DATA_DIR = "ingestion/data"
OUTPUT_FILE = "ingestion/data/extracted_documents.json"

def extract_pdf_text(filepath):
    """Extract both plain text and tables from a digital PDF, page by page."""
    text_by_page = []
    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            
            tables = page.extract_tables()
            table_text = ""
            for t_idx, table in enumerate(tables, start=1):
                table_text += f"\n[TABLE {t_idx}]\n"
                for row in table:
                    clean_row = [cell if cell else "" for cell in row]
                    table_text += " | ".join(clean_row) + "\n"

            combined = page_text.strip() + "\n" + table_text.strip()
            text_by_page.append({"page": page_num, "text": combined.strip()})
    return text_by_page

def extract_txt_text(filepath):
    """Read a plain text file directly."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return [{"page": 1, "text": f.read().strip()}]

def extract_spreadsheet_text(filepath):
    """Convert spreadsheet rows into readable text, one 'page' per sheet/file."""
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    # Convert the whole table into a readable text block
    text = df.to_string(index=False)
    return [{"page": 1, "text": text.strip()}]

def extract_image_text(filepath):
    """Run OCR on an image (e.g., P&ID diagrams, scanned pages)."""
    image = Image.open(filepath)
    raw_text = pytesseract.image_to_string(image)
    return [{"page": 1, "text": raw_text.strip()}]

def process_all_documents():
    all_documents = []

    for filename in os.listdir(DATA_DIR):
        filepath = os.path.join(DATA_DIR, filename)
        ext = filename.lower().split(".")[-1]

        try:
            if ext == "pdf":
                pages = extract_pdf_text(filepath)
            elif ext == "txt":
                pages = extract_txt_text(filepath)
            elif ext in ("csv", "xlsx"):
                pages = extract_spreadsheet_text(filepath)
            elif ext == "png":
                pages = extract_image_text(filepath)
            else:
                print(f"Skipping (not handled yet): {filename}")
                continue

            all_documents.append({
                "document_id": filename,
                "source_type": ext,
                "pages": pages
            })
            print(f"Extracted: {filename} ({len(pages)} page(s)/section(s))")

        except Exception as e:
            print(f"FAILED on {filename}: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_documents, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved {len(all_documents)} documents to {OUTPUT_FILE}")

if __name__ == "__main__":
    process_all_documents()