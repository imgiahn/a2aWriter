"""
LH PDF 첨부파일 텍스트 추출

사용:
  from tools.pdf_parser import extract_text_from_bytes, extract_text_from_file
"""

import io
import re
import sys


def extract_text_from_bytes(data: bytes) -> str:
    """PDF bytes에서 텍스트 추출."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t.strip())
            return "\n".join(pages)
    except Exception as e:
        return f"[PDF 파싱 오류: {e}]"


def extract_text_from_file(path: str) -> str:
    """PDF 파일 경로에서 텍스트 추출."""
    try:
        with open(path, "rb") as f:
            return extract_text_from_bytes(f.read())
    except Exception as e:
        return f"[PDF 파일 읽기 오류: {e}]"


def clean_pdf_text(text: str, max_chars: int = 8000) -> str:
    """PDF 텍스트 정제 — 반복 문자(이상 렌더링) 제거 후 핵심 내용 추출."""
    if not text:
        return ""

    # 같은 글자 3회 이상 연속 반복 제거 (PDF 폰트 이슈)
    text = re.sub(r"(.)\1{3,}", r"\1", text)
    # 과도한 공백 정리
    text = re.sub(r" {3,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()[:max_chars]


if __name__ == "__main__":
    # 테스트: python tools/pdf_parser.py /path/to/file.pdf
    if len(sys.argv) > 1:
        text = extract_text_from_file(sys.argv[1])
        print(clean_pdf_text(text))
