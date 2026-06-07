"""
repair_posts.py — 빈 껍데기로 발행된 청약홈 공고 글 재수집 & 티스토리 수정

대상: 20260606_001 ~ 20260606_007 (오피스텔/APT잔여세대 — 잘못된 API 엔드포인트로 데이터 공백)
흐름: 상세 API 재수집 → GPT 필드 추출 → task .md 업데이트 → writer --dry-run → 티스토리 수정
티스토리 수정: 쿠키 추출 → PUT /manage/post/{id}.json 직접 호출
"""

import os
import re
import sys
import time
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")
DRAFT_DIR = Path(f"articles/{BLOG}/preview")
PUB_DIR   = Path(f"articles/{BLOG}/published")

# 수정 대상: (task_id, notice_id, list_type, house_secd)
TARGETS = [
    ("20260606_001", "2026950052", "오피스텔/도시형", "02"),  # 풍무역 푸르지오 시티 (미수정)
]


# ─── 1. 상세 데이터 재수집 ───────────────────────────────────────────

def fetch_and_extract(notice_id: str, list_type: str, house_secd: str, supply_type: str) -> dict:
    from tools.applyhome_scraper import fetch_detail_with_pdf
    from agents.planner_agent import extract_notice_fields, _save_pdf_to_disk

    print(f"    상세 API 호출 [{list_type}] ...")
    detail      = fetch_detail_with_pdf(notice_id, list_type=list_type, house_secd=house_secd)
    detail_text = detail["text"]
    pdf_text    = detail.get("pdf_text", "")
    pdf_bytes   = detail.get("pdf_bytes", b"")

    if not detail_text:
        print(f"    ⚠️  상세 텍스트 없음")
        return {}

    print(f"    텍스트 {len(detail_text)}자", end="")
    if pdf_text:
        print(f" / PDF {len(pdf_text)}자", end="")
    print()

    _save_pdf_to_disk(notice_id, pdf_bytes)
    combined = detail_text + ("\n\n=== PDF ===\n" + pdf_text if pdf_text else "")
    fields   = extract_notice_fields(combined, supply_type)
    fields["_has_pdf"]  = bool(pdf_text)
    fields["_pdf_path"] = f"data/{BLOG}/notices/{notice_id}/original.pdf" if pdf_bytes else ""
    return fields


# ─── 2. task .md 파일 frontmatter 업데이트 ──────────────────────────

def update_task_file(task_id: str, fields: dict):
    path = TASKS_DIR / f"{task_id}.md"
    text = path.read_text(encoding="utf-8")

    FIELD_MAP = [
        ("total_units",           fields.get("total_units", "")),
        ("notice_phase",          fields.get("notice_phase", "")),
        ("apply_start",           fields.get("apply_start", "")),
        ("apply_end",             fields.get("apply_end", "")),
        ("result_date",           fields.get("result_date", "")),
        ("contract_start",        fields.get("contract_start", "")),
        ("contract_end",          fields.get("contract_end", "")),
        ("move_in",               fields.get("move_in", "")),
        ("supply_target",         fields.get("supply_target", "")),
        ("deposit",               fields.get("deposit", "")),
        ("monthly_rent",          fields.get("monthly_rent", "")),
        ("jeonse_amount",         fields.get("jeonse_amount", "")),
        ("house_types",           fields.get("house_types", "")),
        ("supply_units",          fields.get("supply_units", "")),
        ("sale_price",            fields.get("sale_price", "")),
        ("contract_amount",       fields.get("contract_amount", "")),
        ("interim_payment",       fields.get("interim_payment", "")),
        ("balance_payment",       fields.get("balance_payment", "")),
        ("first_supply",          fields.get("first_supply", "")),
        ("conversion",            fields.get("conversion", "")),
        ("location_detail",       fields.get("location_detail", "")),
        ("supply_this_time",      fields.get("supply_this_time", "")),
        ("restriction_rewin",     fields.get("restriction_rewin", "")),
        ("restriction_resale",    fields.get("restriction_resale", "")),
        ("obligation_residence",  fields.get("obligation_residence", "")),
        ("has_pdf",               "true" if fields.get("_has_pdf") else "false"),
        ("pdf_path",              fields.get("_pdf_path", "")),
    ]

    def replace_field(t, key, val):
        val = str(val).replace("\n", " ")
        return re.sub(rf"^{key}:.*$", f"{key}: {val}", t, flags=re.MULTILINE)

    for key, val in FIELD_MAP:
        text = replace_field(text, key, val)

    qual = fields.get("qualifications", "")
    if qual:
        qual_block = "qualifications: |\n  " + qual.replace("\n", "\n  ")
        text = re.sub(r"qualifications: \|.*?(?=\ncreated_by:)", qual_block + "\n",
                      text, flags=re.DOTALL)

    path.write_text(text, encoding="utf-8")
    print(f"    ✅ task 업데이트 완료: {task_id}.md")


# ─── 3. writer --dry-run 으로 HTML 재생성 ───────────────────────────

def regenerate_html(task_id: str) -> bool:
    task_path = TASKS_DIR / f"{task_id}.md"
    result = subprocess.run(
        [sys.executable, "agents/writer_agent.py",
         "--blog", BLOG,
         "--task", str(task_path),
         "--dry-run"],
        capture_output=True, text=True
    )
    print(result.stdout.strip()[-500:] if result.stdout else "(출력 없음)")
    if result.returncode != 0:
        print(f"    ⚠️  writer 오류: {result.stderr[-300:]}")
        return False
    return (DRAFT_DIR / f"{task_id}.html").exists()


# ─── 4. Tistory 쿠키 추출 ──────────────────────────────────────────

def get_tistory_cookies() -> dict:
    """Playwright browser_data에서 Tistory 쿠키를 추출한다."""
    from playwright.sync_api import sync_playwright
    from agents.publisher_agent import auto_login

    cookies = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()
        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            print("  세션 만료 → 자동 로그인...")
            auto_login(page, BLOG_URL)
            page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")

        for c in ctx.cookies():
            if "tistory" in c.get("domain", ""):
                cookies[c["name"]] = c["value"]
        ctx.close()

    print(f"  쿠키 {len(cookies)}개 추출")
    return cookies


# ─── 5. PUT API로 티스토리 포스트 수정 ─────────────────────────────

def find_post_id_by_title(cookies: dict, title_keyword: str) -> str:
    """manage/posts 페이지 파싱으로 포스트 ID 찾기."""
    from playwright.sync_api import sync_playwright
    from agents.publisher_agent import auto_login

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()
        page.goto(f"{BLOG_URL}/manage/posts", timeout=20000, wait_until="networkidle")
        if "login" in page.url:
            auto_login(page, BLOG_URL)
            page.goto(f"{BLOG_URL}/manage/posts", timeout=20000, wait_until="networkidle")

        post_id = page.evaluate(f"""() => {{
            const keyword = {json.dumps(title_keyword[:15])};
            let found = null;
            document.querySelectorAll('a.link_cont').forEach(lk => {{
                const t = lk.getAttribute('title') || lk.textContent;
                if (t.includes(keyword)) {{
                    const container = lk.closest('li') || lk.parentElement.parentElement.parentElement.parentElement;
                    const btn = container ? container.querySelector('a.btn_post') : null;
                    if (btn) {{
                        const m = btn.getAttribute('href').match(/\\/manage\\/post\\/(\\d+)/);
                        if (m) found = m[1];
                    }}
                }}
            }});
            return found;
        }}""")
        ctx.close()
    return post_id or ""


def put_post_content(cookies: dict, post_id: str, title: str, html: str) -> bool:
    """PUT /manage/post/{id}.json 으로 내용 직접 업데이트.

    필수 payload 구조 (Tistory 발행 시 실제 전송 필드 기준):
      visibility: 20 (공개), published: 0 (기존 발행 시각 유지), 등
    """
    import requests as _req
    import re as _re

    url = f"{BLOG_URL}/manage/post/{post_id}.json"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"{BLOG_URL}/manage/newpost/{post_id}?type=post",
        "Origin": BLOG_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }

    # 슬로건: 제목에서 특수문자 제거, 공백→하이픈
    slogan = _re.sub(r"[^\w\s가-힣]", "", title)
    slogan = _re.sub(r"\s+", "-", slogan.strip())

    payload = {
        "id":                   post_id,
        "title":                title,
        "content":              html,
        "slogan":               slogan,
        "visibility":           20,      # 20 = 공개
        "category":             0,
        "tag":                  "",
        "acceptComment":        1,
        "published":            0,       # 0 = 기존 발행 시각 유지
        "password":             "",
        "uselessMarginForEntry": 1,
        "daumLike":             None,
        "cclCommercial":        0,
        "cclDerive":            0,
        "thumbnail":            None,
        "type":                 "post",
        "attachments":          [],
        "recaptchaValue":       "",
        "draftSequence":        None,
        "totalWritingTimeMs":   5000,
    }

    resp = _req.put(url, json=payload, cookies=cookies, headers=headers, timeout=20)
    print(f"    PUT {url} → {resp.status_code}")
    if resp.status_code not in (200, 201, 204):
        print(f"    응답: {resp.text[:300]}")
        return False
    return True


def read_draft_html(task_id: str):
    draft = DRAFT_DIR / f"{task_id}.html"
    content = draft.read_text(encoding="utf-8")
    m = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", content, re.DOTALL)
    title = m.group(1) if m else task_id
    html  = m.group(2) if m else content
    return title, html


# ─── 메인 ────────────────────────────────────────────────────────────

def main(tistory_only: bool = False):
    import shutil

    print("=" * 55)
    print("Repair — 빈 껍데기 공고 글 재수집 & 티스토리 수정")
    print("=" * 55)

    if tistory_only:
        success_ids = [t[0] for t in TARGETS if (DRAFT_DIR / f"{t[0]}.html").exists()]
        print(f"--tistory-only: draft HTML {len(success_ids)}개 확인됨")
    else:
        for task_id, notice_id, list_type, house_secd in TARGETS:
            task_path   = TASKS_DIR / f"{task_id}.md"
            supply_type = ""
            for line in task_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("supply_type:"):
                    supply_type = line.split(":", 1)[1].strip()
                    break

            print(f"\n[{task_id}] {notice_id} / {list_type}")
            try:
                fields = fetch_and_extract(notice_id, list_type, house_secd, supply_type)
                if fields:
                    update_task_file(task_id, fields)
                else:
                    print(f"    ⚠️  필드 추출 실패, 스킵")
            except Exception as e:
                print(f"    ❌ 수집 오류: {e}")

        print("\n" + "=" * 55)
        print("HTML 재생성 (writer --dry-run)")
        print("=" * 55)
        success_ids = []
        for task_id, *_ in TARGETS:
            print(f"\n[{task_id}]")
            if regenerate_html(task_id):
                success_ids.append(task_id)
                print(f"    ✅ draft 생성 완료")
            else:
                print(f"    ❌ HTML 생성 실패")

        if not success_ids:
            print("❌ 재생성된 HTML 없음. 종료.")
            return

    # ── 쿠키 추출 ──
    print("\n" + "=" * 55)
    print("티스토리 쿠키 추출")
    print("=" * 55)
    cookies = get_tistory_cookies()
    if not cookies:
        print("❌ 쿠키 추출 실패")
        return

    # ── PUT API로 직접 수정 ──
    print("\n" + "=" * 55)
    print("티스토리 PUT API 직접 수정")
    print("=" * 55)

    for task_id in success_ids:
        title, html = read_draft_html(task_id)
        print(f"\n[{task_id}] {title[:40]}")

        # 포스트 ID 찾기
        post_id = find_post_id_by_title(cookies, title)
        if not post_id:
            print(f"    ⚠️  포스트 ID 못 찾음")
            continue

        print(f"    포스트 ID: {post_id}")
        try:
            ok = put_post_content(cookies, post_id, title, html)
            if ok:
                shutil.copy(
                    str(DRAFT_DIR / f"{task_id}.html"),
                    str(PUB_DIR   / f"{task_id}.html"),
                )
                print(f"    ✅ 수정 완료")
            else:
                print(f"    ❌ PUT 실패")
        except Exception as e:
            print(f"    ❌ 오류: {e}")

    print("\n✅ repair 완료")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tistory-only", action="store_true")
    args = ap.parse_args()
    main(tistory_only=args.tistory_only)
