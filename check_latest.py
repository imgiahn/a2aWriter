from playwright.sync_api import sync_playwright
BLOG_URL = "https://llmenginehistory.tistory.com"
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()
    page.goto(BLOG_URL + "/manage/posts", timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(2000)
    result = page.evaluate("""() => {
        const items = [];
        document.querySelectorAll('a.link_cont').forEach(lk => {
            const li = lk.closest('li');
            const btn = li ? li.querySelector('a.btn_post') : null;
            if (!btn) return;
            const m = btn.getAttribute('href').match(/\/manage\/post\/(\d+)/);
            if (m) items.push({id: parseInt(m[1]), title: (lk.getAttribute('title')||lk.textContent).trim()});
        });
        return items.slice(0,5);
    }""")
    for p in result:
        print(p['id'], '|', p['title'])
    ctx.close()
