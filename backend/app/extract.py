"""DOCX/PDF -> text. Uploads are capped at 5 MB and stored org-scoped in Postgres."""
import io

MAX_BYTES = 5 * 1024 * 1024
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ExtractError(Exception):
    pass


def detect_kind(filename: str, data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK" and filename.lower().endswith(".docx"):
        return "docx"
    raise ExtractError("Only .docx and .pdf files are supported")


def extract_text(kind: str, data: bytes) -> str:
    try:
        if kind == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "").strip() for page in reader.pages)
        else:
            from docx import Document

            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        raise ExtractError(f"Could not read the {kind.upper()} file: {e}") from e
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not text:
        raise ExtractError(f"No text found in the {kind.upper()} file (scanned images are not supported yet)")
    return text
