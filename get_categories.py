from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir='browser_data', headless=True,
        args=['--disable-dev-shm-usage','--disable-gpu']
    )
    page = ctx.new_page()
    page.goto('https://llmenginehistory.tistory.com/manage/newpost/', timeout=20000)
    page.wait_for_load_state('networkidle', timeout=15000)
    page.wait_for_timeout(2000)
    page.evaluate("document.getElementById('category-btn').click()")
    page.wait_for_timeout(1500)
    items = page.query_selector_all('[data-id]')
    for item in items:
        did = item.get_attribute('data-id')
        text = item.inner_text().strip()
        if did and did.isdigit() and int(did) > 0:
            print(f'{did}: {repr(text)}')
    ctx.close()
