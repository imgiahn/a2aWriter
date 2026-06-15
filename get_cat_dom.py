import os, re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
load_dotenv()
BLOG_URL = "https://llmenginehistory.tistory.com"
EMAIL    = os.getenv("KAKAO_EMAIL", "")
PASSWORD = os.getenv("KAKAO_PASSWORD", "")

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage","--disable-gpu","--no-sandbox"]
    )
    page = ctx.new_page()
    try:
        page.goto(BLOG_URL + "/manage/newpost/", timeout=20000, wait_until="domcontentloaded")
    except: pass
    if "login" in page.url:
        try: page.goto("https://www.tistory.com/auth/login", timeout=20000, wait_until="domcontentloaded")
        except: pass
        page.wait_for_timeout(1000)
        page.locator("a.link_kakao_id").click()
        page.wait_for_timeout(3000)
        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(EMAIL)
            page.locator("input[name='password']").fill(PASSWORD)
            page.locator("button[type='submit']").click()
            page.wait_for_timeout(5000)
        try: page.goto(BLOG_URL + "/manage/newpost/", timeout=20000, wait_until="domcontentloaded")
        except: pass
        page.wait_for_timeout(3000)

    try: page.wait_for_function("typeof tinyMCE !== 'undefined'", timeout=10000)
    except: pass
    page.wait_for_timeout(2000)

    page.evaluate("document.getElementById('category-btn').click()")
    page.wait_for_timeout(1500)

    # category-list 영역 HTML 덤프
    html = page.evaluate("""() => {
        const el = document.getElementById('category-list');
        return el ? el.outerHTML.substring(0, 3000) : 'category-list not found';
    }""")
    print(html)
    ctx.close()
