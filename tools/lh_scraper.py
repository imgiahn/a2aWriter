"""
LH 청약플러스 스크래퍼

사용:
  python tools/lh_scraper.py              # 서울+경기 공고 목록 출력
  python tools/lh_scraper.py --detail URL # 특정 공고 상세 텍스트 출력
"""

import sys
import json
import argparse
from typing import Optional, List
from playwright.sync_api import sync_playwright, Page

LH_MAIN_URL = "https://apply.lh.or.kr/lhapply/main.do"
LH_LIST_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026"
LH_DETAIL_BASE = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do"

TARGET_REGIONS = {"서울", "경기"}
# 지역 컬럼 텍스트 → 필터 매칭
REGION_KEYWORDS = ["서울", "경기"]


def _make_browser(pw):
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    return browser, page


def _load_list_page(page: Page):
    """메인 → 목록 순서로 이동해야 정상 로딩됨."""
    page.goto(LH_MAIN_URL, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.goto(LH_LIST_URL, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(3000)


def scrape() -> List[dict]:
    """서울/경기 공고 목록을 수집해 반환한다."""
    results = []

    with sync_playwright() as pw:
        browser, page = _make_browser(pw)
        try:
            _load_list_page(page)

            rows = page.query_selector_all("tbody tr")
            print(f"  총 {len(rows)}행 발견", file=sys.stderr)

            for row in rows:
                cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
                if len(cells) < 6:
                    continue

                region = cells[3] if len(cells) > 3 else ""
                if not any(kw in region for kw in REGION_KEYWORDS):
                    continue

                # 공고명 + 공고번호(data-id1) 추출
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
                    f"{LH_DETAIL_BASE}?wrtancNo={notice_id}&mi=1026"
                    if notice_id else ""
                )

                results.append({
                    "notice_id":   notice_id,
                    "notice_name": notice_name,
                    "supply_type": cells[1] if len(cells) > 1 else "",
                    "region":      region,
                    "notice_date": cells[5] if len(cells) > 5 else "",
                    "deadline":    cells[6] if len(cells) > 6 else "",
                    "status":      cells[7] if len(cells) > 7 else "",
                    "detail_url":  detail_url,
                })

        finally:
            browser.close()

    return results


def fetch_detail(url: str) -> str:
    """공고 상세 페이지 텍스트를 추출한다."""
    with sync_playwright() as pw:
        browser, page = _make_browser(pw)
        try:
            page.goto(LH_MAIN_URL, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.goto(url, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)

            for sel in [".view_wrap", ".detail_wrap", ".bbs_view", ".cont_wrap", "#content", "main"]:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if len(text) > 200:
                        return text[:6000]

            return page.inner_text("body").strip()[:6000]
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", metavar="URL", help="상세 페이지 텍스트 추출")
    args = parser.parse_args()

    if args.detail:
        print(fetch_detail(args.detail))
    else:
        print("LH 청약플러스 서울+경기 공고 수집 중...", file=sys.stderr)
        items = scrape()
        if not items:
            print("수집 결과 없음.")
        else:
            print(json.dumps(items, ensure_ascii=False, indent=2))
            print(f"\n총 {len(items)}건", file=sys.stderr)
