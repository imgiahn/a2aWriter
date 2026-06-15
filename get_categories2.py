from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir='browser_data', headless=True,
        args=['--disable-dev-shm-usage','--disable-gpu']
    )
    page = ctx.new_page()
    # 카테고리 관리 페이지로 직접 접근
    page.goto('https://llmenginehistory.tistory.com/manage/category', timeout=20000)
    page.wait_for_load_state('networkidle', timeout=15000)
    print("URL:", page.url)
    print("Title:", page.title())
    content = page.content()
    # data-id 있는 요소 추출
    import re
    matches = re.findall(r'data-id=["\'](\d+)["\'][^>]*>([^<]+)<', content)
    for did, text in matches:
        print(f'{did}: {text.strip()}')
    ctx.close()
