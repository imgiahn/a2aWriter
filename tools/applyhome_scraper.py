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

LIST_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do"
TARGET_REGIONS = {"서울", "경기", "인천"}


def _make_browser(pw):
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = context.new_page()
    return browser, context, page


def _parse_rows(page: Page) -> list:
    """현재 페이지 테이블에서 공고 목록을 파싱한다."""
    rows = page.query_selector_all("table tbody tr")
    items = []
    for row in rows:
        pbno  = row.get_attribute("data-pbno") or ""
        hmno  = row.get_attribute("data-hmno") or ""
        honm  = row.get_attribute("data-honm") or ""
        if not pbno:
            continue
        cells = row.query_selector_all("td")
        if len(cells) < 9:
            continue

        region      = cells[0].inner_text().strip()
        house_secd  = cells[1].inner_text().strip()   # 민영 / 국민
        rent_secd   = cells[2].inner_text().strip()   # 분양주택 / 임대주택
        notice_date = cells[6].inner_text().strip()
        apply_range = cells[7].inner_text().strip()   # "2026-06-15 ~ 2026-06-17"
        result_date = cells[8].inner_text().strip()

        # 서울/경기/인천만
        if region not in TARGET_REGIONS:
            continue

        housing_source = "임대" if "임대" in rent_secd else "분양"
        priority       = "high" if housing_source == "분양" else "medium"

        # 청약 마감: apply_range에서 ~ 뒤 날짜
        deadline = ""
        if "~" in apply_range:
            deadline = apply_range.split("~")[-1].strip()

        items.append({
            "notice_id":      pbno,
            "notice_name":    honm,
            "supply_type":    f"{house_secd} {rent_secd}".strip(),
            "region":         region,
            "notice_date":    notice_date,
            "deadline":       deadline,
            "apply_range":    apply_range,
            "result_date":    result_date,
            "detail_url":     f"{LIST_URL}?pblancNo={pbno}",
            "housing_source": housing_source,
            "priority":       priority,
            "list_mi":        "applyhome",
        })
    return items


def scrape_notices(max_pages: int = 10) -> list:
    """서울/경기/인천 공고 목록을 수집한다."""
    results = []

    with sync_playwright() as pw:
        browser, context, page = _make_browser(pw)
        try:
            page.goto(LIST_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    # 페이지 이동
                    nav = page.query_selector(f"a[href='?pageIndex={page_num}']")
                    if not nav:
                        break
                    nav.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_timeout(1500)

                rows_found = _parse_rows(page)
                results.extend(rows_found)
                print(f"  [청약홈] {page_num}페이지: {len(rows_found)}건 (서울/경기/인천)", file=sys.stderr)

                # 다음 페이지 없으면 종료
                next_btn = page.query_selector(f"a[href='?pageIndex={page_num + 1}']")
                if not next_btn:
                    break

        finally:
            browser.close()

    return results


def fetch_detail_with_pdf(notice_id: str, **kwargs) -> dict:
    """공고 상세 텍스트 + PDF bytes를 반환한다.

    lh_scraper.py와 동일한 반환 형식:
      {"text": str, "pdf_text": str, "pdf_filename": str, "pdf_bytes": bytes}
    """
    try:
        from tools.pdf_parser import extract_price_focused, extract_scoring_focused
    except ImportError:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        from tools.pdf_parser import extract_price_focused, extract_scoring_focused

    with sync_playwright() as pw:
        browser, context, page = _make_browser(pw)
        try:
            page.goto(LIST_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            # 목록에서 해당 공고 행 찾기 (전체 페이지 순회)
            found = False
            for page_num in range(1, 15):
                if page_num > 1:
                    nav = page.query_selector(f"a[href='?pageIndex={page_num}']")
                    if not nav:
                        break
                    nav.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_timeout(1500)

                row = page.query_selector(f"tr[data-pbno='{notice_id}']")
                if row:
                    found = True
                    break

            if not found:
                return {"text": "", "pdf_text": "", "pdf_filename": "", "pdf_bytes": b""}

            # 공고명 링크 클릭 → 모달
            link = row.query_selector("a.txt_l_b")
            if not link:
                return {"text": "", "pdf_text": "", "pdf_filename": "", "pdf_bytes": b""}

            link.click()
            page.wait_for_timeout(3000)

            # iframe 접근
            iframe_el = page.query_selector("iframe#iframeDialog")
            if not iframe_el:
                return {"text": "", "pdf_text": "", "pdf_filename": "", "pdf_bytes": b""}

            iframe = iframe_el.content_frame()
            if not iframe:
                return {"text": "", "pdf_text": "", "pdf_filename": "", "pdf_bytes": b""}

            iframe.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(1000)

            # 본문 텍스트
            try:
                text = iframe.inner_text("body").strip()[:8000]
            except Exception:
                text = ""

            # PDF 링크 탐색
            pdf_link = iframe.query_selector("a[href*='getAtchmnfl']")
            pdf_text     = ""
            pdf_filename = ""
            pdf_bytes    = b""

            if pdf_link:
                pdf_href = pdf_link.get_attribute("href") or ""
                pdf_filename = f"applyhome_{notice_id}.pdf"
                print(f"  📎 PDF 발견, 다운로드 중...", file=sys.stderr)
                try:
                    import tempfile, os
                    with context.expect_page(timeout=15000) as new_page_info:
                        pdf_link.click(modifiers=["Alt"])  # Alt+Click → 다운로드 시도
                    new_p = new_page_info.value
                    new_p.close()
                except Exception:
                    pass

                # expect_download 방식
                try:
                    with page.expect_download(timeout=20000) as dl_info:
                        iframe.evaluate(f"window.location.href = '{pdf_href}'")
                    dl = dl_info.value
                    tmp_path = tempfile.mktemp(suffix=".pdf")
                    dl.save_as(tmp_path)
                    with open(tmp_path, "rb") as f:
                        pdf_bytes = f.read()
                    os.unlink(tmp_path)
                    if pdf_bytes:
                        pdf_text = extract_price_focused(pdf_bytes)
                except Exception as e:
                    print(f"  ⚠️  PDF 다운로드 실패: {e}", file=sys.stderr)

        finally:
            browser.close()

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
