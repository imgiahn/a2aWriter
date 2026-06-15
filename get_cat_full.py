import os
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

    # 로그인
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

    print("URL:", page.url)

    # tinyMCE 로드 대기
    try:
        page.wait_for_function("typeof tinyMCE !== 'undefined'", timeout=10000)
    except: pass
    page.wait_for_timeout(2000)

    # 카테고리 버튼 클릭
    page.evaluate("document.getElementById('category-btn').click()")
    page.wait_for_timeout(1500)

    items = page.evaluate("""() => {
        const result = [];
        document.querySelectorAll('[data-id]').forEach(el => {
            const id = el.getAttribute('data-id');
            if (id && parseInt(id) > 0) {
                result.push({id: id, text: el.innerText.trim()});
            }
        });
        return result;
    }""")
    print(f"{len(items)}개 카테고리:")
    for item in items:
        print(f"  {item['id']}: {item['text']}")
    ctx.close()
