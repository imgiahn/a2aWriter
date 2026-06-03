"""
LH PDF 첨부파일 텍스트 추출

사용:
  from tools.pdf_parser import extract_text_from_bytes, extract_text_from_file
"""

import io
import re
import sys


# 금액 관련 키워드 (이 키워드가 포함된 페이지 우선 추출)
PRICE_KEYWORDS = ["공급금액", "분양가", "계약금", "중도금", "잔금", "납부일정",
                  "공급가격", "분양대금", "납부방법", "만원", "억원"]


def extract_text_from_bytes(data: bytes) -> str:
    """PDF bytes에서 전체 텍스트 추출."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:
        return f"[PDF 파싱 오류: {e}]"


def extract_text_from_file(path: str) -> str:
    """PDF 파일 경로에서 텍스트 추출."""
    try:
        with open(path, "rb") as f:
            return extract_text_from_bytes(f.read())
    except Exception as e:
        return f"[PDF 파일 읽기 오류: {e}]"


def extract_price_focused(data: bytes, max_chars: int = 10000) -> str:
    """금액 관련 페이지를 우선 추출한다.

    전략:
    1. 가격 키워드 포함 페이지 → 앞에 배치
    2. 나머지 페이지는 뒤에 붙임
    3. 총 max_chars 제한
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            price_pages = []
            other_pages = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if any(kw in t for kw in PRICE_KEYWORDS):
                    price_pages.append(t)
                else:
                    other_pages.append(t)

            combined = "\n\n".join(price_pages + other_pages)
            return clean_pdf_text(combined, max_chars)
    except Exception as e:
        return f"[PDF 파싱 오류: {e}]"


def clean_pdf_text(text: str, max_chars: int = 10000) -> str:
    """PDF 텍스트 정제 — 반복 문자 제거 후 반환."""
    if not text:
        return ""
    text = re.sub(r"(.)\1{3,}", r"\1", text)
    text = re.sub(r" {3,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_chars]


if __name__ == "__main__":
    # 테스트: python tools/pdf_parser.py /path/to/file.pdf
    if len(sys.argv) > 1:
        text = extract_text_from_file(sys.argv[1])
        print(clean_pdf_text(text))
