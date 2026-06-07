"""
repair_posts.py — 빈 껍데기로 발행된 청약홈 공고 글 재수집 & 티스토리 수정

대상: 20260606_001 ~ 20260606_007 (오피스텔/APT잔여세대 — 잘못된 API 엔드포인트로 데이터 공백)
흐름: 상세 API 재수집 → GPT 필드 추출 → task .md 업데이트 → writer --dry-run → 티스토리 수정
"""

import os
import re
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")
DRAFT_DIR = Path(f"articles/{BLOG}/draft")
PUB_DIR   = Path(f"articles/{BLOG}/published")

# 수정 대상: (task_id, notice_id, list_type, house_secd)
TARGETS = [
    ("20260606_001", "2026950052", "오피스텔/도시형", "02"),  # 풍무역 푸르지오 시티
    ("20260606_002", "2026910138", "APT잔여세대",     ""),   # 청계 노르웨이숲(9차)
    ("20260606_003", "2026940110", "APT잔여세대",     ""),   # 화곡더리브스카이(3차)
    ("20260606_004", "2026940112", "APT잔여세대",     ""),   # 더샵 분당센트로(2차)
    ("20260606_005", "2026910130", "APT잔여세대",     ""),   # 경기광주역 롯데캐슬
    ("20260606_006", "2026910146", "APT잔여세대",     ""),   # 동탄 그웬 160
    ("20260606_007", "2026930020", "APT잔여세대",     ""),   # 신검단중앙역 금강펜테리움
]


# ─── 1. 상세 데이터 재수집 ───────────────────────────────────────────

def fetch_and_extract(notice_id: str, list_type: str, house_secd: str, supply_type: str) -> dict:
    from tools.applyhome_scraper import fetch_detail_with_pdf
    from agents.planner_agent import extract_notice_fields, _save_pdf_to_disk
    from tools.pdf_parser import extract_price_focused

    print(f"    상세 API 호출 [{list_type}] ...")
    detail     = fetch_detail_with_pdf(notice_id, list_type=list_type, house_secd=house_secd)
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

    # qualifications 다중줄 처리
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
    draft = DRAFT_DIR / f"{task_id}.html"
    return draft.exists()


# ─── 4. 티스토리 포스트 수정 ────────────────────────────────────────

def find_post_edit_url(page, title: str) -> str:
    """manage/posts 목록에서 제목으로 포스트 편집 URL 찾기."""
    for page_num in range(1, 6):
        url = f"{BLOG_URL}/manage/posts?page={page_num}"
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        # 제목 링크 탐색
        rows = page.query_selector_all("table tbody tr, .post-list li, .list_post tr")
        for row in rows:
            row_text = row.inner_text()
            if title[:15] in row_text:
                edit_link = row.query_selector("a[href*='/manage/post/edit/'], a:has-text('수정')")
                if edit_link:
                    href = edit_link.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            href = BLOG_URL + href
                        return href
        # 다음 페이지 없으면 종료
        if not page.query_selector(f"a[href*='page={page_num+1}']"):
            break
    return ""


def update_tistory_post(page, title: str, html: str) -> bool:
    edit_url = find_post_edit_url(page, title)
    if not edit_url:
        print(f"    ⚠️  포스트 편집 URL 못 찾음: {title[:20]}")
        return False

    print(f"    편집 URL: {edit_url}")
    page.goto(edit_url, timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(2000)

    # tinyMCE로 내용 교체
    page.wait_for_function(
        "typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null",
        timeout=10000,
    )
    injected = page.evaluate(
        """(html) => {
            try {
                const ed = tinyMCE.activeEditor;
                if (!ed) return false;
                ed.focus(); ed.setContent(html); ed.save();
                return true;
            } catch(e) { return false; }
        }""",
        html,
    )
    if not injected:
        print(f"    ⚠️  tinyMCE 삽입 실패, HTML 모드 시도")
        page.locator("li:has-text('HTML'), button:has-text('HTML')").first.click()
        page.wait_for_timeout(1000)
        done = page.evaluate(
            """(html) => {
                const cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) { cm.CodeMirror.setValue(html); return true; }
                return false;
            }""",
            html,
        )
        if not done:
            return False

    page.wait_for_timeout(500)

    # 완료 → 발행 버튼
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    modal = page.locator('.ReactModal__Content.editor_layer')
    try:
        modal.wait_for(state='visible', timeout=8000)
        page.locator('#open20').check(timeout=5000)
        page.wait_for_timeout(800)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(3000)
    except Exception:
        # 모달 없으면 이미 저장됨
        page.locator("button:has-text('저장'), button:has-text('완료')").first.click(timeout=5000)
        page.wait_for_timeout(2000)

    return True


def read_draft_html(task_id: str):
    draft = DRAFT_DIR / f"{task_id}.html"
    content = draft.read_text(encoding="utf-8")
    m = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", content, re.DOTALL)
    title = m.group(1) if m else task_id
    html  = m.group(2) if m else content
    return title, html


# ─── 메인 ────────────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright
    import shutil

    BROWSER_DATA_DIR = Path("browser_data")

    print("=" * 55)
    print("Repair — 빈 껍데기 공고 글 재수집 & 티스토리 수정")
    print("=" * 55)

    # ── Step 1 & 2: 상세 수집 → task 업데이트 ──
    task_supply = {}
    for task_id, notice_id, list_type, house_secd in TARGETS:
        task_path   = TASKS_DIR / f"{task_id}.md"
        supply_type = ""
        for line in task_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("supply_type:"):
                supply_type = line.split(":", 1)[1].strip()
                break
        task_supply[task_id] = supply_type

        print(f"\n[{task_id}] {notice_id} / {list_type}")
        try:
            fields = fetch_and_extract(notice_id, list_type, house_secd, supply_type)
            if fields:
                update_task_file(task_id, fields)
            else:
                print(f"    ⚠️  필드 추출 실패, 스킵")
        except Exception as e:
            print(f"    ❌ 수집 오류: {e}")

    # ── Step 3: HTML 재생성 ──
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

    # ── Step 4: 티스토리 수정 ──
    print("\n" + "=" * 55)
    print("티스토리 포스트 수정")
    print("=" * 55)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = context.new_page()

        # 로그인 확인
        page.goto(f"{BLOG_URL}/manage", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        if "login" in page.url or "/manage" not in page.url:
            print("❌ 로그인 세션 만료. setup_browser.py를 먼저 실행하세요.")
            context.close()
            return

        print("✅ 로그인 세션 확인")

        for task_id in success_ids:
            title, html = read_draft_html(task_id)
            print(f"\n[{task_id}] {title[:40]}")
            try:
                ok = update_tistory_post(page, title, html)
                if ok:
                    # published HTML 갱신
                    shutil.copy(
                        str(DRAFT_DIR / f"{task_id}.html"),
                        str(PUB_DIR   / f"{task_id}.html"),
                    )
                    print(f"    ✅ 티스토리 수정 완료")
                else:
                    print(f"    ❌ 수정 실패")
            except Exception as e:
                print(f"    ❌ 오류: {e}")

        context.close()

    print("\n✅ repair 완료")


if __name__ == "__main__":
    main()
