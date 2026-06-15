from playwright.sync_api import sync_playwright
BLOG_URL = "https://llmenginehistory.tistory.com"
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage","--disable-gpu","--no-sandbox"]
    )
    page = ctx.new_page()
    try:
        page.goto(BLOG_URL + "/manage/newpost/", timeout=20000, wait_until="networkidle")
    except: pass
    page.wait_for_timeout(3000)
    print("URL:", page.url)
    # 카테고리 버튼 JS 클릭
    page.evaluate("document.getElementById('category-btn').click()")
    page.wait_for_timeout(1500)
    # data-id 있는 요소 수집
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
    for item in items:
        print(f"{item['id']}: {item['text']}")
    ctx.close()
