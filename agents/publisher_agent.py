"""
Publisher Agent

역할: 초안을 티스토리에 발행
입력: articles/draft/{task_id}.html + tasks/writing/{task_id}.md
출력: 티스토리 공개 발행

성공 시: tasks/writing/ → tasks/published/
실패 시: tasks/writing/ → tasks/failed/
"""

import os
import re
import sys
import shutil
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext

load_dotenv()

TASKS_WRITING   = Path("tasks/writing")
TASKS_PUBLISHED = Path("tasks/published")
TASKS_FAILED    = Path("tasks/failed")
ARTICLES_DRAFT  = Path("articles/draft")
ARTICLES_PUB    = Path("articles/published")
COOKIES_FILE    = Path("tistory_cookies.json")

BLOG_NAME = "mbtireallove"
BLOG_URL  = f"https://{BLOG_NAME}.tistory.com"


def get_next_task() -> Path | None:
    tasks = sorted(TASKS_WRITING.glob("*.md"))
    return tasks[0] if tasks else None


def read_draft(task_id: str) -> tuple[str, str]:
    """초안 HTML에서 제목과 본문을 분리한다."""
    draft = ARTICLES_DRAFT / f"{task_id}.html"
    content = draft.read_text(encoding="utf-8")
    m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", content, re.DOTALL)
    title = m.group(1) if m else task_id
    html  = m.group(2) if m else content
    return title, html


def load_cookies(context: BrowserContext):
    if COOKIES_FILE.exists():
        import json
        context.add_cookies(json.loads(COOKIES_FILE.read_text(encoding="utf-8")))


def save_cookies(context: BrowserContext):
    import json
    COOKIES_FILE.write_text(
        json.dumps(context.cookies(), ensure_ascii=False),
        encoding="utf-8",
    )


def is_logged_in(page: Page) -> bool:
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "/manage" in page.url and "login" not in page.url


def manual_login(page: Page):
    print("\n⚠️  로그인이 필요합니다.")
    print("   브라우저에서 로그인 후 Enter를 눌러주세요...")
    page.goto("https://www.tistory.com/auth/login")
    input("   [로그인 완료 후 Enter] ")


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

    # TinyMCE에 HTML 주입
    injected = page.evaluate(
        """(html) => {
            try {
                const ed = tinyMCE.activeEditor;
                if (!ed) return false;
                ed.focus(); ed.setContent(html); ed.save();
                return true;
            } catch(e) { return false; }
        }""",
        content,
    )

    if not injected:
        page.locator("button:has-text('기본모드'), .button_mode").first.click()
        page.wait_for_timeout(500)
        page.locator("li:has-text('HTML'), button:has-text('HTML')").first.click()
        page.wait_for_timeout(1000)
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
                raise RuntimeError("에디터 내용 삽입 실패")

    page.wait_for_timeout(500)

    # 완료 버튼 → 발행 패널 열기
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    # 발행 패널: 공개 선택 (#open20) → 저장 (#publish-btn)
    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)
    page.locator('#open20').check(timeout=5000)
    page.wait_for_timeout(800)
    page.evaluate("document.getElementById('publish-btn').click()")
    page.wait_for_timeout(3000)


def run():
    server_mode = not sys.stdout.isatty() or os.getenv("SERVER_MODE") == "1"

    print("=" * 50)
    print("Publisher Agent")
    print("=" * 50)

    task_file = get_next_task()
    if not task_file:
        print("발행할 Task 없음 (tasks/writing/ 가 비어있음)")
        return

    task_id = task_file.stem
    print(f"Task: {task_id}")

    title, html = read_draft(task_id)
    print(f"제목: {title}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page    = context.new_page()
        load_cookies(context)

        if not is_logged_in(page):
            browser.close()
            if server_mode:
                print("❌ 쿠키 만료. 로컬에서 tistory_cookies.json 갱신 후 재업로드하세요.")
                shutil.move(str(task_file), str(TASKS_FAILED / task_file.name))
                return
            COOKIES_FILE.unlink(missing_ok=True)
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page    = context.new_page()
            manual_login(page)
            save_cookies(context)

        try:
            post_article(page, title, html)
            # 성공 처리
            shutil.move(str(task_file), str(TASKS_PUBLISHED / task_file.name))
            draft = ARTICLES_DRAFT / f"{task_id}.html"
            shutil.copy(str(draft), str(ARTICLES_PUB / f"{task_id}.html"))
            print(f"✅ 발행 완료 → tasks/published/")
        except Exception as e:
            shutil.move(str(task_file), str(TASKS_FAILED / task_file.name))
            print(f"❌ 발행 실패: {e} → tasks/failed/")
        finally:
            browser.close()


if __name__ == "__main__":
    run()
