"""
청약홈(applyhome.co.kr) 서울/경기 공고 수집 스크래퍼

lh_scraper.py와 동일한 인터페이스:
  scrape_notices()                  → 공고 목록 리스트
  fetch_detail_with_pdf(notice_id)  → {text, pdf_text, pdf_filename, pdf_bytes}
"""

import sys
import io
from pathlib import Path
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

BASE_URL   = "https://www.applyhome.co.kr"
# 수집 대상 목록 페이지 (APT 분양 / 오피스텔·도시형 / APT 잔여세대)
LIST_PAGES = [
    f"{BASE_URL}/ai/aia/selectAPTLttotPblancListView.do",
    f"{BASE_URL}/ai/aia/selectOtherLttotPblancListView.do",
    f"{BASE_URL}/ai/aia/selectAPTRemndrLttotPblancListView.do",
]
TARGET_REGIONS = ["서울", "경기", "인천"]


def _this_month_param() -> str:
    """현재 연월 파라미터 반환 (예: 2026년 06월)."""
    from datetime import date
    d = date.today()
    return f"{d.year}년 {d.month:02d}월"


def _make_browser(pw):
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = context.new_page()
    return browser, context, page


def _parse_rows(page: Page, region: str, apt_only: bool = False, list_type: str = "APT분양") -> list:
    """현재 페이지 테이블에서 공고 목록을 파싱한다.

    apt_only=True: APT 분양 페이지 → 민영만 수집 (국민/공공은 LH에서 처리)
    청약기간 셀은 ~ 기호로 동적 탐색 (페이지별 열 구조가 다름)
    list_type: "APT분양" | "오피스텔/도시형" | "APT잔여세대" — 상세 API 라우팅용
    """
    from datetime import date as _date
    import re as _re
    today = _date.today()

    rows = page.query_selector_all("table tbody tr")
    items = []
    for row in rows:
        pbno   = row.get_attribute("data-pbno") or ""
        honm   = row.get_attribute("data-honm") or ""
        hsecd  = row.get_attribute("data-hsecd") or ""
        if not pbno:
            continue
        cells = row.query_selector_all("td")
        if len(cells) < 6:
            continue

        cell_texts = [c.inner_text().strip() for c in cells]

        # APT 분양 페이지: 민영만 수집
        if apt_only and cell_texts[1] != "민영":
            continue

        # 청약기간 셀 동적 탐색 (~ 포함 셀)
        apply_range = ""
        apply_idx   = -1
        for i, t in enumerate(cell_texts):
            if "~" in t and _re.search(r"\d{4}-\d{2}-\d{2}", t):
                apply_range = t
                apply_idx   = i
                break

        if not apply_range:
            continue

        notice_date = cell_texts[apply_idx - 1] if apply_idx > 0 else ""
        result_date = cell_texts[apply_idx + 1] if apply_idx + 1 < len(cell_texts) else ""
        house_secd  = cell_texts[1]
        supply_type = house_secd

        # 마감일 지난 공고 스킵
        try:
            end_str = apply_range.split("~")[-1].strip()
            m = _re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", end_str)
            if m:
                dl = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if dl <= today:
                    continue
        except Exception:
            pass

        housing_source = "임대" if any(k in supply_type for k in ("임대", "민간임대")) else "분양"
        priority       = "high" if housing_source == "분양" else "medium"
        deadline       = apply_range.split("~")[-1].strip()

        items.append({
            "notice_id":      pbno,
            "notice_name":    honm,
            "supply_type":    supply_type,
            "region":         region,
            "notice_date":    notice_date,
            "deadline":       deadline,
            "apply_range":    apply_range,
            "result_date":    result_date,
            "detail_url":     f"{LIST_PAGES[0]}?pblancNo={pbno}",
            "housing_source": housing_source,
            "priority":       priority,
            "list_mi":        "applyhome",
            "list_type":      list_type,
            "house_secd":     hsecd,
        })
    return items


def scrape_notices(max_pages: int = 5) -> list:
    """서울/경기/인천 민영 공고를 3개 목록 페이지에서 수집한다."""
    from urllib.parse import quote
    results  = []
    seen_ids = set()

    with sync_playwright() as pw:
        browser, context, page = _make_browser(pw)
        try:
            begin_pd = quote(_this_month_param())
            for list_url in LIST_PAGES:
                apt_only = "APTLttotPblanc" in list_url  # APT 분양 페이지만 민영 필터
                label    = ("APT분양" if "APTLttot" in list_url
                            else "오피스텔/도시형" if "Other" in list_url
                            else "APT잔여세대")

                for region in TARGET_REGIONS:
                    url = f"{list_url}?suplyAreaCode={region}&beginPd={begin_pd}"
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)

                    for page_num in range(1, max_pages + 1):
                        if page_num > 1:
                            nav = page.query_selector(f"a[href='?pageIndex={page_num}']")
                            if not nav:
                                break
                            page.evaluate("el => el.click()", nav)
                            page.wait_for_timeout(2000)
                            try:
                                page.wait_for_selector("table tbody tr", timeout=8000)
                            except Exception:
                                pass

                        try:
                            rows_found = _parse_rows(page, region, apt_only=apt_only, list_type=label)
                        except Exception:
                            rows_found = []
                        new_rows   = [r for r in rows_found if r["notice_id"] not in seen_ids]
                        seen_ids.update(r["notice_id"] for r in new_rows)
                        results.extend(new_rows)
                        if new_rows:
                            print(f"  [청약홈/{label}/{region}] {page_num}p: {len(new_rows)}건", file=sys.stderr)

                        if not page.query_selector(f"a[href='?pageIndex={page_num + 1}']"):
                            break
        finally:
            browser.close()

    return results


def fetch_detail_with_pdf(notice_id: str, list_type: str = "APT분양", house_secd: str = "", **kwargs) -> dict:
    """공고 상세 텍스트 + PDF bytes를 반환한다.

    list_type에 따라 올바른 API 엔드포인트를 사용한다:
      - "APT분양":      selectAPTLttotPblancDetail.do        (AIA01M01)
      - "오피스텔/도시형": selectPRMOLttotPblancDetailView.do  (AIA02M01, houseSecd 필요)
      - "APT잔여세대":   selectAPTRemndrLttotPblancDetailView.do (AIA03M01)

    lh_scraper.py와 동일한 반환 형식:
      {"text": str, "pdf_text": str, "pdf_filename": str, "pdf_bytes": bytes}
    """
    import re as _re
    try:
        import requests as _req
        from tools.pdf_parser import extract_price_focused
    except ImportError:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        import requests as _req
        from tools.pdf_parser import extract_price_focused

    if list_type == "오피스텔/도시형":
        DETAIL_API = f"{BASE_URL}/ai/aia/selectPRMOLttotPblancDetailView.do"
        REFERER    = f"{BASE_URL}/ai/aia/selectOtherLttotPblancListView.do"
        payload    = f"houseManageNo={notice_id}&pblancNo={notice_id}&houseSecd={house_secd}&gvPgmId=AIA02M01"
    elif list_type == "APT잔여세대":
        DETAIL_API = f"{BASE_URL}/ai/aia/selectAPTRemndrLttotPblancDetailView.do"
        REFERER    = f"{BASE_URL}/ai/aia/selectAPTRemndrLttotPblancListView.do"
        payload    = f"houseManageNo={notice_id}&pblancNo={notice_id}&gvPgmId=AIA03M01"
    else:  # APT분양 (기본값)
        DETAIL_API = f"{BASE_URL}/ai/aia/selectAPTLttotPblancDetail.do"
        REFERER    = f"{BASE_URL}/ai/aia/selectAPTLttotPblancListView.do"
        payload    = f"houseManageNo={notice_id}&pblancNo={notice_id}&gvPgmId=AIA01M01"

    HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer":      REFERER,
        "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        resp = _req.post(DETAIL_API, data=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    ⚠️  상세 API 호출 실패: {e}", file=sys.stderr)
        return {"text": "", "pdf_text": "", "pdf_filename": "", "pdf_bytes": b""}

    # HTML에서 텍스트 추출
    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()[:8000]

    # PDF 링크 탐색 (getAtchmnfl.do?...)
    pdf_text     = ""
    pdf_filename = ""
    pdf_bytes    = b""

    pdf_m = _re.search(r'href="(https://static\.applyhome\.co\.kr[^"]*getAtchmnfl[^"]*)"', html)
    if pdf_m:
        pdf_url      = pdf_m.group(1)
        pdf_filename = f"applyhome_{notice_id}.pdf"
        print(f"  📎 PDF 발견, 다운로드 중...", file=sys.stderr)
        try:
            pdf_resp  = _req.get(pdf_url, headers=HEADERS, timeout=30)
            pdf_bytes = pdf_resp.content
            if pdf_bytes:
                pdf_text = extract_price_focused(pdf_bytes)
                print(f"    📄 PDF {len(pdf_text)}자", file=sys.stderr)
        except Exception as e:
            print(f"    ⚠️  PDF 다운로드 실패: {e}", file=sys.stderr)

    return {
        "text":         text,
        "pdf_text":     pdf_text,
        "pdf_filename": pdf_filename,
        "pdf_bytes":    pdf_bytes,
    }


if __name__ == "__main__":
    print("=== 청약홈 서울/경기 공고 수집 테스트 ===")
    notices = scrape_notices(max_pages=3)
    print(f"\n총 {len(notices)}건 수집")
    for n in notices:
        print(f"  [{n['region']}] {n['notice_name'][:40]} ({n['deadline']})")
