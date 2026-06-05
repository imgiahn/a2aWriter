"""
LH PDF 첨부파일 텍스트 추출

사용:
  from tools.pdf_parser import extract_text_from_bytes, extract_text_from_file
"""

import io
import re
import sys


# 금액 관련 키워드
PRICE_KEYWORDS = ["공급금액", "분양가", "계약금", "중도금", "잔금", "납부일정",
                  "공급가격", "분양대금", "납부방법", "만원", "억원"]

# 소득/자산/자격 관련 키워드
QUAL_KEYWORDS = ["월평균소득", "도시근로자", "소득기준", "소득 기준",
                 "총자산", "자산기준", "자산가액", "자동차가액",
                 "소득·자산", "소득 및 자산"]

# 일정 관련 키워드
SCHEDULE_KEYWORDS = ["신청기간", "접수기간", "접수일", "당첨자발표", "당첨자 발표",
                     "계약일", "계약기간", "입주예정", "입주지정", "사전당첨",
                     "모집공고일", "발표일"]


def extract_pages_text(data: bytes) -> list:
    """PDF bytes를 페이지별 텍스트+메타데이터 리스트로 추출한다.

    Returns:
        [{"page_num": 1, "text": "...", "char_count": 100,
          "has_price": bool, "has_qual": bool, "has_schedule": bool}, ...]
    """
    try:
        import pdfplumber
        result = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                result.append({
                    "page_num":    i,
                    "text":        text,
                    "char_count":  len(text),
                    "has_price":   any(kw in text for kw in PRICE_KEYWORDS),
                    "has_qual":    any(kw in text for kw in QUAL_KEYWORDS),
                    "has_schedule": any(kw in text for kw in SCHEDULE_KEYWORDS),
                })
        return result
    except Exception as e:
        return []


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


def extract_qualification_focused(data: bytes, max_chars: int = 10000) -> str:
    """소득/자산 기준 페이지를 우선 추출한다 (2차 추출용).

    tier1: 월평균소득 + 도시근로자 동시 포함 (실제 소득기준 표가 있는 페이지)
    tier2: QUAL_KEYWORDS 하나라도 포함
    tier3: 나머지
    """
    CORE_KEYWORDS = ["월평균소득", "도시근로자"]

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            tier1, tier2, tier3 = [], [], []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if all(kw in t for kw in CORE_KEYWORDS):
                    tier1.append(t)
                elif any(kw in t for kw in QUAL_KEYWORDS):
                    tier2.append(t)
                else:
                    tier3.append(t)

            combined = "\n\n".join(tier1 + tier2 + tier3)
            return clean_pdf_text(combined, max_chars)
    except Exception as e:
        return f"[PDF 파싱 오류: {e}]"


_TH = "background:#f5f5f5; border:1px solid #ddd; padding:8px; text-align:center;"
_TD = "border:1px solid #ddd; padding:8px; text-align:center;"
_TBL = "border-collapse:collapse; width:100%; text-align:center;"

INCOME_HEADERS_8COL = ["구분", "기준", "3인 이하", "4인", "5인", "6인", "7인", "8인"]
INCOME_HEADERS_7COL = ["구분", "기준", "3인 이하", "4인", "5인", "6인", "7인"]


def _rows_to_html(title: str, headers: list, rows: list) -> str:
    """표 데이터를 HTML로 변환한다."""
    lines = [f"<h3>{title}</h3>",
             f'<table style="{_TBL}"><thead><tr>']
    for h in headers:
        lines.append(f'  <th style="{_TH}">{h}</th>')
    lines.append("</tr></thead><tbody>")
    prev_first = ""
    for row in rows:
        lines.append("<tr>")
        for idx, cell in enumerate(row):
            val = (str(cell) if cell is not None else "").replace("\n", "<br>").strip()
            if idx == 0:
                if val:
                    prev_first = val
                else:
                    val = prev_first
            lines.append(f'  <td style="{_TD}">{val}</td>')
        lines.append("</tr>")
    lines.append("</tbody></table>")
    return "\n".join(lines)


def extract_qual_tables_as_html(data: bytes) -> str:
    """소득/자산 기준 표를 PDF에서 직접 추출해 HTML로 반환한다.

    핵심 기준: 가구원수별 금액이 여러 행(4행 이상)에 걸쳐 있는 표만 선택
    (배점구간 70%/80%/100%/110%/130%/140% 등 소득구간이 열거된 표)
    """
    CORE_KEYWORDS = ["월평균소득", "도시근로자"]

    try:
        import pdfplumber
        seen, html_parts = set(), []

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if not all(kw in text for kw in CORE_KEYWORDS):
                    continue

                for table in (page.extract_tables() or []):
                    if not table or len(table) < 4:  # 최소 4행 이상
                        continue

                    flat = " ".join(str(c) for r in table for c in r if c)

                    # 소득기준 표: 월평균소득 + 7자리 금액이 3개 이상 + 4행 이상
                    amount_cells = sum(
                        1 for r in table for c in r
                        if len(re.sub(r"[,\s]", "", str(c or ""))) >= 7
                        and re.sub(r"[,\s]", "", str(c or "")).isdigit()
                    )
                    if "월평균소득" not in flat or amount_cells < 3:
                        continue

                    # 중복 제거
                    key = flat[:80]
                    if key in seen:
                        continue
                    seen.add(key)

                    col_count = max(len(r) for r in table)
                    if col_count >= 8:
                        headers = INCOME_HEADERS_8COL
                    elif col_count >= 7:
                        headers = INCOME_HEADERS_7COL
                    else:
                        headers = ["구분", "기준"] + [f"col{i}" for i in range(col_count - 2)]

                    html_parts.append(_rows_to_html("소득 기준 (가구원수별 월평균소득)", headers, table))

        return "\n\n".join(html_parts)
    except Exception as e:
        return f"<!-- 표 추출 오류: {e} -->"


def extract_scoring_focused(data: bytes, max_chars: int = 5000) -> str:
    """소득 배점 기준 페이지 텍스트를 추출한다.

    배점/점수 키워드 + 월평균소득이 함께 있는 페이지 (소득 배점표가 있는 페이지).
    """
    SCORING_KW = ["배점", "점수", "가점"]
    INCOME_KW  = ["월평균소득"]

    try:
        import pdfplumber
        result = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if any(k in t for k in SCORING_KW) and any(k in t for k in INCOME_KW):
                    result.append(t)
        return clean_pdf_text("\n\n".join(result), max_chars)
    except Exception:
        return ""


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
