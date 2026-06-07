"""티스토리 포스트 목록 확인"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login

BLOG_URL = "https://llmenginehistory.tistory.com"

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()
    page.goto(f"{BLOG_URL}/manage/posts", timeout=20000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)
        page.goto(f"{BLOG_URL}/manage/posts", timeout=20000, wait_until="networkidle")

    result = page.evaluate("""() => {
        const items = [];
        document.querySelectorAll('a.link_cont').forEach(lk => {
            const container = lk.closest('li') || lk.parentElement.parentElement.parentElement.parentElement;
            const editBtn = container ? container.querySelector('a.btn_post') : null;
            const href = editBtn ? editBtn.getAttribute('href') : '';
            const m = href.match(/\\/manage\\/post\\/(\\d+)/);
            const pid = m ? m[1] : '?';
            const title = (lk.getAttribute('title') || lk.textContent).substring(0, 50);
            items.push(pid + ' | ' + title);
        });
        return items;
    }""")
    print(f"포스트 {len(result)}개:")
    for r in result:
        print(" ", r)
    ctx.close()
