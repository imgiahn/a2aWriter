"""
Publisher Tool — 티스토리 자동 발행 (dlarldks.tistory.com)
기존 publisher_agent.py 기반, claude2용으로 리팩토링
"""

import os
import re
import time
import shutil
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

BLOG_NAME = "dlarldks"
BLOG_URL = f"https://{BLOG_NAME}.tistory.com"
BROWSER_DATA_DIR = Path(__file__).parent.parent / "browser_data"


def is_logged_in(page: Page) -> bool:
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "/manage" in page.url and "login" not in page.url


def auto_login(page: Page) -> bool:
    email = os.getenv("KAKAO_EMAIL", "")
    password = os.getenv("KAKAO_PASSWORD", "")
    if not email or not password:
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
        print(f"  {'✅ 로그인 성공' if success else '❌ 쿠키 만료'}")
        return success

    except Exception as e:
        print(f"  ❌ 로그인 오류: {e}")
        return False


def reauth(pw) -> Optional[BrowserContext]:
    email = os.getenv("KAKAO_EMAIL", "")
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
            print("  ✅ 재인증 성공")
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
            print("  ✅ 재인증 완료")
            return context

        context.close()
        return None

    except Exception as e:
        print(f"  ❌ 재인증 오류: {e}")
        context.close()
        return None


def post_article(page: Page, title: str, content: str, tags: list = None):
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

    # 태그 입력
    if tags:
        try:
            tag_input = page.locator("input.tags-input, input[placeholder*='태그']").first
            if tag_input.is_visible(timeout=3000):
                for tag in tags[:5]:
                    tag_input.fill(tag)
                    tag_input.press("Enter")
                    page.wait_for_timeout(300)
        except Exception:
            pass

    page.wait_for_timeout(500)
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)
    page.locator('#open20').check(timeout=5000)
    page.wait_for_timeout(800)
    page.evaluate("document.getElementById('publish-btn').click()")
    page.wait_for_timeout(3000)


def publish(title: str, content: str, tags: list = None) -> dict:
    """티스토리에 글 발행. 성공 시 {'success': True} 반환."""
    BROWSER_DATA_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
        )
        page = context.new_page()

        try:
            if not is_logged_in(page):
                print("  로그인 필요 → 자동 로그인 시도...")
                if not auto_login(page):
                    context.close()
                    context = reauth(pw)
                    if not context:
                        return {"success": False, "error": "재인증 실패"}
                    page = context.new_page()
                    if not is_logged_in(page):
                        context.close()
                        return {"success": False, "error": "로그인 실패"}

            post_article(page, title, content, tags)
            print(f"  ✅ 발행 완료: {title}")
            return {"success": True}

        except Exception as e:
            print(f"  ❌ 발행 실패: {e}")
            return {"success": False, "error": str(e)}

        finally:
            context.close()
