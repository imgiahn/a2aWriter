"""LH 사이트 API 엔드포인트 탐지용 디버그 스크립트"""
import re
import sys
import json as _json
from playwright.sync_api import sync_playwright

api_calls = []
api_responses = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()

    def on_request(req):
        if req.resource_type in ("xhr", "fetch") and "lh.or.kr" in req.url:
            api_calls.append({"url": req.url, "method": req.method, "post_data": req.post_data or ""})

    def on_response(resp):
        if "lh.or.kr" in resp.url and resp.request.resource_type in ("xhr", "fetch"):
            try:
                api_responses[resp.url] = resp.text()[:3000]
            except Exception:
                pass

    page.on("request", on_request)
    page.on("response", on_response)
    page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    # 메인 → 목록 순서로 이동
    page.goto("https://apply.lh.or.kr/lhapply/main.do", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2000)

    page.goto("https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(5000)

    out = {"api_responses": api_responses, "xhr_calls": api_calls}

    # 첫 행 HTML + 클릭 시도
    rows = page.query_selector_all("tbody tr")
    if rows:
        first_row = rows[0]
        out["first_row_html"] = first_row.inner_html()[:2000]
        out["first_row_cells"] = [c.inner_text().strip() for c in first_row.query_selector_all("td")]

        # 클릭 후 XHR 잡기
        click_xhrs = []
        def on_click_req(req):
            if req.resource_type in ("xhr", "fetch") and "lh.or.kr" in req.url:
                click_xhrs.append({"url": req.url, "method": req.method, "post_data": req.post_data or ""})
        page.on("request", on_click_req)

        click_responses = {}
        def on_click_resp(resp):
            if "lh.or.kr" in resp.url and resp.request.resource_type in ("xhr", "fetch"):
                try:
                    click_responses[resp.url] = resp.text()[:3000]
                except Exception:
                    pass
        page.on("response", on_click_resp)

        first_row.click()
        page.wait_for_timeout(3000)

        out["after_click_url"] = page.url
        out["click_xhrs"] = click_xhrs
        out["click_responses"] = click_responses

    # 전체 테이블 (상위 5개)
    out["table_sample"] = []
    for row in rows[:5]:
        out["table_sample"].append({
            "cells": [c.inner_text().strip() for c in row.query_selector_all("td")]
        })

    with open("tools/debug_result.json", "w", encoding="utf-8") as f:
        _json.dump(out, f, ensure_ascii=False, indent=2)

    sys.stdout.buffer.write(f"저장 완료: tools/debug_result.json\n".encode("utf-8"))
    sys.stdout.buffer.write(f"테이블 행: {len(rows)}개\n".encode("utf-8"))
    sys.stdout.buffer.write(f"XHR: {len(api_calls)}건\n".encode("utf-8"))

    browser.close()
