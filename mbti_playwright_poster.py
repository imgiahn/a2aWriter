import os
import re
import sys
import json
import time
from datetime import date
from itertools import combinations
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from openai import AzureOpenAI
from playwright.sync_api import sync_playwright, Page, BrowserContext
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ──────────────────────────────────────────────
BLOG_NAME     = "mbtireallove"
BLOG_URL      = f"https://{BLOG_NAME}.tistory.com"
POSTS_PER_DAY = 10
POSTS_PER_RUN = 1   # 1시간에 1개

COOKIES_FILE    = Path("tistory_cookies.json")
POSTED_LOG_FILE = Path("posted_combos.json")
DAILY_LOG_FILE  = Path("daily_log.json")

azure_client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    timeout        = 60,
    max_retries    = 1,
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

COMBO_PATTERN = re.compile(
    r"(INTJ|INTP|ENTJ|ENTP|INFJ|INFP|ENFJ|ENFP"
    r"|ISTJ|ISFJ|ESTJ|ESFJ|ISTP|ISFP|ESTP|ESFP)"
    r"\s+"
    r"(INTJ|INTP|ENTJ|ENTP|INFJ|INFP|ENFJ|ENFP"
    r"|ISTJ|ISFJ|ESTJ|ESFJ|ISTP|ISFP|ESTP|ESFP)"
)


# ── 로컬 로그 ──────────────────────────────────────────
def load_posted_combos() -> set[tuple]:
    if not POSTED_LOG_FILE.exists():
        print("⚠️  posted_combos.json 없음. 빈 상태로 시작합니다.")
        return set()
    data = json.loads(POSTED_LOG_FILE.read_text(encoding="utf-8"))
    return {tuple(sorted(c)) for c in data}

def save_posted_combos(posted: set[tuple]):
    POSTED_LOG_FILE.write_text(
        json.dumps([list(c) for c in posted], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def get_today_count() -> int:
    today = date.today().isoformat()
    if DAILY_LOG_FILE.exists():
        data = json.loads(DAILY_LOG_FILE.read_text(encoding="utf-8"))
        return data.get(today, 0)
    return 0

def increment_today_count():
    today = date.today().isoformat()
    data  = json.loads(DAILY_LOG_FILE.read_text(encoding="utf-8")) if DAILY_LOG_FILE.exists() else {}
    data[today] = data.get(today, 0) + 1
    DAILY_LOG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── 블로그 스크래핑 (초기 동기화) ──────────────────────
def scrape_posted_combos() -> set[tuple]:
    print("블로그 스크래핑으로 기존 포스트 동기화 중...")
    posted, page_num = set(), 1

    while True:
        resp = requests.get(BLOG_URL, params={"page": page_num}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        titles = [
            a.get_text()
            for a in soup.select(
                "a.article-title, .post-item h2 a, .list_content h3 a, "
                ".title a, .post-header h2 a"
            )
        ]
        if not titles:
            break

        for title in titles:
            for m in COMBO_PATTERN.findall(title):
                posted.add(tuple(sorted(m)))

        if not soup.select_one("a.link_next, .pagination a[rel=next], .paging a.next"):
            break
        page_num += 1
        time.sleep(0.5)

    save_posted_combos(posted)
    print(f"  → {len(posted)}개 조합 동기화 완료")
    return posted


# ── 쿠키 관리 ──────────────────────────────────────────
def save_cookies(context: BrowserContext):
    COOKIES_FILE.write_text(
        json.dumps(context.cookies(), ensure_ascii=False),
        encoding="utf-8",
    )
    print("  쿠키 저장 완료")

def load_cookies(context: BrowserContext):
    if COOKIES_FILE.exists():
        context.add_cookies(json.loads(COOKIES_FILE.read_text(encoding="utf-8")))

def is_logged_in(page: Page) -> bool:
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "/manage" in page.url and "login" not in page.url

def manual_login(page: Page):
    print("\n⚠️  로그인이 필요합니다.")
    print("   브라우저 창에서 티스토리에 로그인한 후 Enter를 눌러주세요...")
    page.goto("https://www.tistory.com/auth/login")
    input("   [로그인 완료 후 Enter] ")


# ── 글 포스팅 ──────────────────────────────────────────
def post_article(page: Page, title: str, content: str):
    page.goto(f"{BLOG_URL}/manage/newpost/", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)

    # 제목 입력
    title_loc = page.locator(
        "textarea[id*='title'], input[id*='title'], .editor-title-area textarea, "
        "#post-title-inp, .tf_subject"
    ).first
    title_loc.wait_for(timeout=10000)
    title_loc.fill(title)
    page.wait_for_timeout(500)

    # TinyMCE 로딩 대기
    page.wait_for_function(
        "typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null",
        timeout=10000,
    )
    page.wait_for_timeout(500)

    # TinyMCE에 HTML 주입 + 저장 동기화
    injected = page.evaluate(
        """(html) => {
            try {
                const ed = tinyMCE.activeEditor;
                if (!ed) return false;
                ed.focus();
                ed.setContent(html);
                ed.save();
                return true;
            } catch(e) {
                return false;
            }
        }""",
        content,
    )

    if not injected:
        # 기본모드▼ 드롭다운 → HTML 모드 선택
        page.locator("button:has-text('기본모드'), .button_mode").first.click()
        page.wait_for_timeout(500)
        page.locator("li:has-text('HTML'), button:has-text('HTML')").first.click()
        page.wait_for_timeout(1000)

        # CodeMirror 또는 textarea에 직접 입력
        done = page.evaluate(
            """(html) => {
                const cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) { cm.CodeMirror.setValue(html); return true; }
                return false;
            }""",
            content,
        )
        if not done:
            ta = page.locator("textarea.html-editor, #content, textarea[name='content']").first
            if ta.is_visible(timeout=3000):
                ta.fill(content)
            else:
                page.screenshot(path="debug_editor_fail.png")
                raise RuntimeError("에디터 내용 삽입 실패. debug_editor_fail.png 확인")

    page.wait_for_timeout(500)

    # 완료 버튼 (티스토리 신에디터)
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    # 발행 패널(ReactModal) 로딩 대기
    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)
    page.screenshot(path="debug_publish_panel.png")

    # 발행 패널(ReactModal) 로딩 대기
    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)

    # 공개 라디오 선택 (#open20)
    page.locator('#open20').check(timeout=5000)
    page.wait_for_timeout(800)

    # 저장 버튼 클릭 (#publish-btn)
    page.evaluate("document.getElementById('publish-btn').click()")
    page.wait_for_timeout(3000)


# ── AI 글 생성 ──────────────────────────────────────────
GUIDE_FILE = Path("writing_guide.md")

def load_guide() -> str:
    if GUIDE_FILE.exists():
        return GUIDE_FILE.read_text(encoding="utf-8")
    return ""

SYSTEM_PROMPT = (
    "당신은 MBTI 연애 심리 분석 전문가이자 블로거입니다.\n"
    "아래 작성 가이드를 반드시 따라 HTML 형식으로만 출력합니다.\n\n"
    f"{load_guide()}"
)

def build_prompt(mbti1: str, mbti2: str) -> str:
    return f"""{mbti1}과 {mbti2} 커플 궁합 분석 글을 작성 가이드에 맞춰 HTML로 작성해주세요.

맨 첫 줄에 반드시 부제목을 넣어주세요:
<!-- SUBTITLE: [부제목] -->
(예: "리더와 리더의 정면 충돌, 혹은 드림팀", "두 이상주의자의 깊은 교감")

이후 HTML 본문을 가이드의 섹션 순서대로 작성:
💡 커플 소개 → 💞 연애 초반 → 🔥 현실 연애 → ⚠️ 갈등 & 조율 → 💍 장기 궁합 → ✅ 꿀팁 4가지 → ✍️ 마무리

중요: 각 섹션은 3~5문장, 핵심만 임팩트 있게. 너무 길게 쓰지 말 것."""

def generate_content(mbti1: str, mbti2: str) -> tuple[str, str]:
    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_prompt(mbti1, mbti2)},
        ],
        temperature=0.8,
        max_completion_tokens=3000,
        timeout=60,
    )
    raw = resp.choices[0].message.content.strip()

    m        = re.search(r"<!--\s*SUBTITLE:\s*(.+?)\s*-->", raw)
    subtitle = m.group(1) if m else f"{mbti1}과 {mbti2}의 케미"
    content  = re.sub(r"<!--\s*SUBTITLE:\s*.+?\s*-->\n?", "", raw)
    title    = f"💘 {mbti1} {mbti2} 커플 궁합 분석 – {subtitle}"

    return title, content


# ── 메인 ──────────────────────────────────────────────
def run():
    print("=" * 50)
    print("MBTI 궁합 자동 포스터 (Playwright)")
    print("=" * 50)

    posted     = load_posted_combos()
    all_combos = {tuple(sorted(c)) for c in combinations(MBTI_TYPES, 2)}
    remain     = list(all_combos - posted)

    today_count = get_today_count()
    quota_left  = POSTS_PER_DAY - today_count

    print(f"전체 조합    : 120개")
    print(f"이미 올린 것 : {len(posted)}개")
    print(f"남은 것      : {len(remain)}개")
    print(f"오늘 올린 것 : {today_count}개  (남은 쿼터: {quota_left}개)")

    if not remain:
        print("✅ 모든 조합 완료!")
        return
    if quota_left <= 0:
        print("오늘 일일 제한(10개) 도달. 내일 다시 실행됩니다.")
        return

    to_post = remain[:min(POSTS_PER_RUN, quota_left)]
    server_mode = not sys.stdout.isatty() or os.getenv("SERVER_MODE") == "1"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page    = context.new_page()

        load_cookies(context)

        if not is_logged_in(page):
            browser.close()
            if server_mode:
                print("❌ 쿠키가 만료되었습니다.")
                print("   로컬에서 스크립트를 실행해 tistory_cookies.json을 갱신한 후")
                print("   scp로 서버에 재업로드하세요.")
                print("   scp -i giahn.pem tistory_cookies.json ec2-user@13.61.144.167:~/mbti/")
                return
            print("쿠키 만료 또는 없음 → 재로그인")
            COOKIES_FILE.unlink(missing_ok=True)
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page    = context.new_page()
            manual_login(page)
            save_cookies(context)

        for i, (mbti1, mbti2) in enumerate(to_post, 1):
            print(f"\n[{i}/{len(to_post)}] {mbti1} x {mbti2} 생성 중...")
            try:
                title, content = generate_content(mbti1, mbti2)
                print(f"  제목: {title}")
                post_article(page, title, content)
                print(f"  ✅ 포스팅 완료")
                posted.add(tuple(sorted((mbti1, mbti2))))
                save_posted_combos(posted)
                increment_today_count()
            except Exception as e:
                print(f"  ❌ 오류: {e}")


        browser.close()

    print(f"\n완료! 오늘 총 {get_today_count()}개 업로드됨")


if __name__ == "__main__":
    run()
