"""
LH 청약플러스 스크래퍼

사용:
  python tools/lh_scraper.py          # 서울+경기 공고 목록 출력
  python tools/lh_scraper.py --detail [URL]  # 특정 공고 상세 내용 출력
"""

import sys
import json
import argparse
from typing import Optional, List, Tuple
from playwright.sync_api import sync_playwright, Page

LH_LIST_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do"
TARGET_REGIONS = {"서울", "경기"}

# 지역 코드 (LH 사이트 select 옵션값)
REGION_CODES = {
    "서울": "11",
    "경기": "41",
}


def _wait_for_list(page: Page, timeout: int = 15000):
    """공고 목록 테이블이 로딩될 때까지 대기."""
    try:
        page.wait_for_selector("table tbody tr, .list_wrap li, .no_data", timeout=timeout)
    except Exception:
        pass


def fetch_list(region_code: str, page: Page) -> list[dict]:
    """지역 코드로 공고 목록 한 페이지 수집."""
    url = f"{LH_LIST_URL}?tab=lh&searchType=1&region={region_code}"
    page.goto(url, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    _wait_for_list(page)

    results = []

    # 방법 1: 테이블 행 파싱
    rows = page.query_selector_all("table.tbl_st tbody tr, table tbody tr")
    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) < 3:
            continue

        texts = [c.inner_text().strip() for c in cells]

        # 링크 추출 (공고명 또는 단지명)
        link_el = row.query_selector("a")
        href = ""
        if link_el:
            href = link_el.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = "https://apply.lh.or.kr" + href

        results.append({
            "raw_cells": texts,
            "detail_url": href,
        })

    # 방법 2: 리스트 형태 (테이블 없을 경우)
    if not results:
        items = page.query_selector_all(".list_wrap li, .apply_list li, ul.list li")
        for item in items:
            text = item.inner_text().strip()
            link_el = item.query_selector("a")
            href = ""
            if link_el:
                href = link_el.get_attribute("href") or ""
                if href and not href.startswith("http"):
                    href = "https://apply.lh.or.kr" + href
            if text:
                results.append({"raw_cells": [text], "detail_url": href})

    return results


def parse_announcement(raw: dict) -> Optional[dict]:
    """raw_cells에서 공고 정보를 구조화한다."""
    cells = raw.get("raw_cells", [])
    detail_url = raw.get("detail_url", "")

    if not cells or not detail_url:
        return None

    # LH 공고 목록 컬럼 순서 추정:
    # [지역] [공고명] [공고번호] [공급유형] [공고일] ...
    # 실제 순서는 사이트마다 다를 수 있어 유연하게 처리
    result = {
        "raw": cells,
        "detail_url": detail_url,
        "notice_name": "",
        "notice_id": "",
        "supply_type": "",
        "region": "",
        "notice_date": "",
    }

    # 공고번호 패턴: LH로 시작하거나 숫자-숫자 패턴
    import re
    for cell in cells:
        if re.match(r"LH\d+|^\d{4}-\d+", cell):
            result["notice_id"] = cell
        elif re.match(r"\d{4}\.\d{2}\.\d{2}|\d{4}-\d{2}-\d{2}", cell):
            result["notice_date"] = cell
        elif cell in ("국민임대", "행복주택", "영구임대", "분양전환", "분양주택", "공공분양", "장기전세"):
            result["supply_type"] = cell
        elif cell in TARGET_REGIONS or any(r in cell for r in TARGET_REGIONS):
            result["region"] = cell

    # 공고명: 가장 긴 텍스트 or 링크 텍스트
    name_candidates = [c for c in cells if len(c) > 5 and c not in (
        result["notice_id"], result["notice_date"], result["supply_type"], result["region"]
    )]
    if name_candidates:
        result["notice_name"] = max(name_candidates, key=len)

    return result


def fetch_detail(url: str, page: Page) -> str:
    """공고 상세 페이지 전체 텍스트를 추출한다."""
    page.goto(url, timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # 본문 영역 우선 추출
    for selector in [".view_wrap", ".detail_wrap", ".cont_wrap", "#content", "main", "body"]:
        el = page.query_selector(selector)
        if el:
            text = el.inner_text()
            if len(text) > 200:
                return text.strip()

    return page.inner_text("body").strip()


def scrape(regions=None, max_per_region: int = 20) -> List[dict]:
    """서울+경기 공고 목록을 수집하고 구조화된 결과를 반환한다."""
    regions = regions or list(REGION_CODES.items())
    announcements = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        for region_name, region_code in regions:
            print(f"  [{region_name}] 수집 중...", file=sys.stderr)
            try:
                raw_list = fetch_list(region_code, page)
                print(f"    → {len(raw_list)}행 발견", file=sys.stderr)

                count = 0
                for raw in raw_list:
                    if count >= max_per_region:
                        break
                    parsed = parse_announcement(raw)
                    if not parsed:
                        continue
                    parsed["region"] = parsed["region"] or region_name
                    announcements.append(parsed)
                    count += 1

            except Exception as e:
                print(f"    ⚠️  오류: {e}", file=sys.stderr)

        browser.close()

    return announcements


# ── 디버그/테스트용 진입점 ─────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", metavar="URL", help="상세 페이지 텍스트 추출")
    parser.add_argument("--raw",    action="store_true", help="raw_cells 포함 출력")
    args = parser.parse_args()

    if args.detail:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            text = fetch_detail(args.detail, page)
            browser.close()
        print(text[:3000])
    else:
        print("LH 청약플러스 서울+경기 공고 수집 중...", file=sys.stderr)
        results = scrape()
        if not results:
            print("수집 결과 없음. 사이트 구조가 예상과 다를 수 있습니다.")
            print("raw HTML 확인을 위해 headless=False로 바꿔 실행해보세요.")
        else:
            for item in results:
                if not args.raw:
                    item.pop("raw", None)
            print(json.dumps(results, ensure_ascii=False, indent=2))
