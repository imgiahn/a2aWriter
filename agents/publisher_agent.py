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
import time
import shutil
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext

load_dotenv()

TASKS_WRITING    = Path("tasks/writing")
TASKS_PUBLISHED  = Path("tasks/published")
TASKS_FAILED     = Path("tasks/failed")
ARTICLES_DRAFT   = Path("articles/draft")
ARTICLES_PUB     = Path("articles/published")
BROWSER_DATA_DIR = Path("browser_data")

BLOG_NAME = "mbtireallove"
BLOG_URL  = f"https://{BLOG_NAME}.tistory.com"


def get_next_task() -> Optional[Path]:
    tasks = sorted(TASKS_WRITING.glob("*.md"))
    return tasks[0] if tasks else None


def read_draft(task_id: str) -> tuple:
    draft   = ARTICLES_DRAFT / f"{task_id}.html"
    content = draft.read_text(encoding="utf-8")
    m       = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", content, re.DOTALL)
    title   = m.group(1) if m else task_id
    html    = m.group(2) if m else content
    return title, html


def is_logged_in(page: Page) -> bool:
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "/manage" in page.url and "login" not in page.url


def auto_login(page: Page) -> bool:
    """저장된 쿠키로 카카오 로그인 시도."""
    email    = os.getenv("KAKAO_EMAIL", "")
    password = os.getenv("KAKAO_PASSWORD", "")
    if not email or not password:
        print("  ⚠️  KAKAO_EMAIL / KAKAO_PASSWORD 환경변수가 없습니다.")
        return False

    try:
        page.goto("https://www.tistory.com/auth/login", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.locator("a.link_kakao_id").click()
        page.wait_for_load_state("networkidle", timeout=15000)

        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(email)
            page.locator("input[name='password']").fill(password)
            page.locator("button[type='submit']").click()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)

        page.goto(f"{BLOG_URL}/manage", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        success = "/manage" in page.url and "login" not in page.url
        print(f"  {'✅ 자동 로그인 성공' if success else '❌ 쿠키 만료 → 재인증 필요'}")
        return success

    except Exception as e:
        print(f"  ❌ 자동 로그인 오류: {e}")
        return False


def reauth(pw) -> Optional[BrowserContext]:
    """쿠키 만료 시 headless 재인증. 폰 카카오 앱 승인 필요."""
    email    = os.getenv("KAKAO_EMAIL", "")
    password = os.getenv("KAKAO_PASSWORD", "")

    if BROWSER_DATA_DIR.exists():
        shutil.rmtree(BROWSER_DATA_DIR)
    BROWSER_DATA_DIR.mkdir()

    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        headless=True,
    )
    page = context.new_page()

    try:
        page.goto("https://www.tistory.com/auth/login", timeout=15000)
        page.wait_for_load_state("networkidle")
        page.locator("a.link_kakao_id").click()
        page.wait_for_load_state("networkidle")

        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(email)
            page.locator("input[name='password']").fill(password)
            page.locator("button[type='submit']").click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

        if "tistory.com" in page.url and "kakao" not in page.url:
            print("  ✅ 재인증 성공 (폰 승인 불필요)")
        else:
            print("  📱 카카오 앱에서 [로그인 승인]을 눌러주세요. (최대 3분 대기)")
            deadline = time.time() + 180
            approved = False
            while time.time() < deadline:
                if "tistory.com" in page.url and "kakao" not in page.url:
                    approved = True
                    break
                for btn_text in ["확인", "계속", "동의", "허용"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.is_visible():
                        btn.click()
                        break
                page.wait_for_timeout(3000)

            if not approved:
                print("  ❌ 재인증 시간 초과")
                context.close()
                return None

        page.goto(f"{BLOG_URL}/manage", timeout=15000)
        page.wait_for_load_state("networkidle")
        if "/manage" in page.url and "login" not in page.url:
            print("  ✅ 재인증 완료 — 쿠키 저장됨")
            return context

        context.close()
        return None

    except Exception as e:
        print(f"  ❌ 재인증 오류: {e}")
        context.close()
        return None


def post_article(page: Page, title: str, content: str):
    page.goto(f"{BLOG_URL}/manage/newpost/", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)

    title_loc = page.locator(
        "textarea[id*='title'], input[id*='title'], .editor-title-area textarea, "
        "#post-title-inp, .tf_subject"
    ).first
    title_loc.wait_for(timeout=10000)
    title_loc.fill(title)
    page.wait_for_timeout(500)

    page.wait_for_function(
        "typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null",
        timeout=10000,
    )
    page.wait_for_timeout(500)

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
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)
    page.locator('#open20').check(timeout=5000)
    page.wait_for_timeout(800)
    page.evaluate("document.getElementById('publish-btn').click()")
    page.wait_for_timeout(3000)


def run():
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

    BROWSER_DATA_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
        )
        page = context.new_page()

        if not is_logged_in(page):
            print("  로그인 필요 → 자동 로그인 시도...")
            if not auto_login(page):
                # 쿠키 만료 → 재인증
                print("  재인증 시작...")
                context.close()
                context = reauth(pw)
                if not context:
                    print("❌ 재인증 실패.")
                    shutil.move(str(task_file), str(TASKS_FAILED / task_file.name))
                    return
                page = context.new_page()
                if not is_logged_in(page):
                    print("❌ 로그인 실패.")
                    context.close()
                    shutil.move(str(task_file), str(TASKS_FAILED / task_file.name))
                    return

        try:
            post_article(page, title, html)
            shutil.move(str(task_file), str(TASKS_PUBLISHED / task_file.name))
            draft = ARTICLES_DRAFT / f"{task_id}.html"
            shutil.copy(str(draft), str(ARTICLES_PUB / f"{task_id}.html"))
            print(f"✅ 발행 완료 → tasks/published/")
        except Exception as e:
            shutil.move(str(task_file), str(TASKS_FAILED / task_file.name))
            print(f"❌ 발행 실패: {e} → tasks/failed/")
        finally:
            context.close()


if __name__ == "__main__":
    run()
