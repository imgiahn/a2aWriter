"""
LH 청약플러스 스크래퍼

사용:
  python tools/lh_scraper.py              # 서울+경기 공고 목록 출력 (분양+임대)
  python tools/lh_scraper.py --detail URL # 특정 공고 상세 텍스트 출력
"""

import sys
import json
import argparse
from typing import Optional, List
from playwright.sync_api import sync_playwright, Page

LH_MAIN_URL   = "https://apply.lh.or.kr/lhapply/main.do"
LH_SALE_URL   = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1027"  # 분양주택
LH_RENTAL_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026"  # 임대주택
LH_DETAIL_BASE = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do"

REGION_KEYWORDS = ["서울", "경기"]

# 목록 유형별 설정: (URL, mi값, housing_source, priority)
LIST_PAGES = [
    (LH_SALE_URL, "1027", "분양", "high"),    # 분양만 수집 (임대 mi=1026 제외)
]


def _make_browser(pw):
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    return browser, page


def _scrape_page(page: Page, list_url: str, mi: str, housing_source: str, priority: str) -> List[dict]:
    """목록 페이지 하나에서 서울/경기 공고를 수집한다."""
    page.goto(LH_MAIN_URL, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.goto(list_url, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(3000)

    rows = page.query_selector_all("tbody tr")
    print(f"  [{housing_source}] {len(rows)}행 발견", file=sys.stderr)

    results = []
    from datetime import date as _date
    today = _date.today()

    for row in rows:
        cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
        if len(cells) < 6:
            continue

        region = cells[3] if len(cells) > 3 else ""
        if not any(kw in region for kw in REGION_KEYWORDS):
            continue

        # 마감일 지난 공고 스킵
        deadline_str = cells[6] if len(cells) > 6 else ""
        if deadline_str:
            try:
                import re as _re
                m = _re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", deadline_str)
                if m:
                    dl = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if dl <= today:
                        continue
            except Exception:
                pass

        link_el = row.query_selector("a.wrtancInfoBtn")
        notice_name = ""
        notice_id   = ""
        if link_el:
            notice_name = link_el.inner_text().strip()
            notice_id   = link_el.get_attribute("data-id1") or ""
        else:
            notice_name = cells[2] if len(cells) > 2 else ""

        if not notice_name:
            continue

        detail_url = (
            f"{LH_DETAIL_BASE}?wrtancNo={notice_id}&mi={mi}"
            if notice_id else ""
        )

        results.append({
            "notice_id":      notice_id,
            "notice_name":    notice_name,
            "supply_type":    cells[1] if len(cells) > 1 else "",
            "region":         region,
            "notice_date":    cells[5] if len(cells) > 5 else "",
            "deadline":       cells[6] if len(cells) > 6 else "",
            "status":         cells[7] if len(cells) > 7 else "",
            "detail_url":     detail_url,
            "housing_source": housing_source,  # "분양" or "임대"
            "priority":       priority,
            "list_mi":        mi,
        })

    return results


def scrape() -> List[dict]:
    """분양(mi=1027) → 임대(mi=1026) 순으로 서울/경기 공고를 수집한다."""
    results = []

    with sync_playwright() as pw:
        browser, page = _make_browser(pw)
        try:
            for list_url, mi, housing_source, priority in LIST_PAGES:
                items = _scrape_page(page, list_url, mi, housing_source, priority)
                results.extend(items)
        finally:
            browser.close()

    return results


def _extract_page_text(page: Page) -> str:
    """현재 페이지(공고 상세)에서 본문 텍스트를 추출한다."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        for sel in [".popup_wrap", ".layer_wrap", ".view_wrap", ".detail_wrap",
                    ".bbs_view", ".cont_wrap", "#content .view", "main"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text[:6000]
        return page.inner_text("body").strip()[:6000]
    except Exception:
        try:
            return page.inner_text("body").strip()[:6000]
        except Exception:
            return ""


def _get_pdf_file_ids(page: Page) -> List[str]:
    """현재 페이지에서 PDF 파일 ID 목록을 추출한다."""
    import re as _re
    ids = []
    for a in page.query_selector_all("a[href*='fileDownLoad']"):
        href = a.get_attribute("href") or ""
        name = a.inner_text().strip().lower()
        if ".pdf" in name:
            m = _re.search(r"fileDownLoad\(['\"](\d+)['\"]\)", href)
            if m:
                ids.append(m.group(1))
    return ids


def _download_pdf_bytes(page: Page, file_id: str) -> bytes:
    """playwright로 PDF를 다운로드해 bytes를 반환한다."""
    import os, tempfile
    try:
        with page.expect_download(timeout=20000) as dl_info:
            page.evaluate(f"fileDownLoad('{file_id}')")
        download = dl_info.value
        tmp_path = tempfile.mktemp(suffix=".pdf")
        download.save_as(tmp_path)
        with open(tmp_path, "rb") as f:
            data = f.read()
        os.unlink(tmp_path)
        return data
    except Exception as e:
        print(f"  ⚠️  PDF 다운로드 실패 (fileId={file_id}): {e}", file=sys.stderr)
        return b""


def _download_pdf_text(page: Page, file_id: str) -> tuple:
    """playwright로 PDF를 다운로드해 (price_text, bytes)를 반환한다."""
    try:
        from tools.pdf_parser import extract_price_focused
    except ImportError:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        from tools.pdf_parser import extract_price_focused

    data = _download_pdf_bytes(page, file_id)
    if not data:
        return "", b""
    return extract_price_focused(data), data


def fetch_detail_by_notice_id(notice_id: str, mi: str = "1026") -> str:
    """목록 페이지에서 공고번호 항목을 클릭해 상세 텍스트를 추출한다 (PDF 미포함)."""
    result = fetch_detail_with_pdf(notice_id, mi)
    return result["text"]


def fetch_detail_with_pdf(notice_id: str, mi: str = "1026") -> dict:
    """상세 텍스트 + PDF 텍스트를 함께 반환한다.

    Returns:
        {"text": str, "pdf_text": str, "pdf_filename": str}
    """
    list_url = LH_SALE_URL if mi == "1027" else LH_RENTAL_URL

    with sync_playwright() as pw:
        browser, page = _make_browser(pw)
        try:
            page.goto(LH_MAIN_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.goto(list_url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(3000)

            link = page.query_selector(f'a.wrtancInfoBtn[data-id1="{notice_id}"]')
            if not link:
                return {"text": "", "pdf_text": "", "pdf_filename": ""}

            link.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            text = _extract_page_text(page)

            # PDF 탐지 & 다운로드
            pdf_file_ids = _get_pdf_file_ids(page)
            pdf_text     = ""
            pdf_filename = ""

            pdf_bytes = b""
            if pdf_file_ids:
                print(f"  📎 PDF {len(pdf_file_ids)}건 발견, 다운로드 중...", file=sys.stderr)
                # 공고문 PDF 우선 (첫 번째)
                pdf_text, pdf_bytes = _download_pdf_text(page, pdf_file_ids[0])

                # 파일명 추출
                for a in page.query_selector_all("a[href*='fileDownLoad']"):
                    name = a.inner_text().strip()
                    if ".pdf" in name.lower():
                        pdf_filename = name
                        break

            return {"text": text, "pdf_text": pdf_text, "pdf_filename": pdf_filename, "pdf_bytes": pdf_bytes}
        finally:
            browser.close()


def fetch_detail(url: str) -> str:
    """공고 상세 URL → 상세 텍스트 반환 (하위 호환)."""
    import re as _re
    notice_m = _re.search(r"wrtancNo=([^&]+)", url)
    mi_m     = _re.search(r"mi=(\d+)", url)
    if notice_m:
        mi = mi_m.group(1) if mi_m else "1026"
        return fetch_detail_by_notice_id(notice_m.group(1), mi)
    return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", metavar="URL", help="상세 페이지 텍스트 추출")
    args = parser.parse_args()

    if args.detail:
        print(fetch_detail(args.detail))
    else:
        print("LH 청약플러스 서울+경기 공고 수집 중 (분양+임대)...", file=sys.stderr)
        items = scrape()
        if not items:
            print("수집 결과 없음.")
        else:
            print(json.dumps(items, ensure_ascii=False, indent=2))
            sale_cnt   = sum(1 for i in items if i["housing_source"] == "분양")
            rental_cnt = sum(1 for i in items if i["housing_source"] == "임대")
            print(f"\n총 {len(items)}건 (분양 {sale_cnt}건 / 임대 {rental_cnt}건)", file=sys.stderr)
