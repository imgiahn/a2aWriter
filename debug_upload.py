"""첨부 버튼 드롭다운 클릭 + 업로드 API 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path

BLOG_URL = "https://llmenginehistory.tistory.com"
test_pdf = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))[0]
upload_reqs = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method in ("POST","PUT") and "kakao" not in req.url and "sentry" not in req.url:
            upload_reqs.append(f"{req.method} {req.url[:150]}")
    def on_resp(resp):
        if resp.request.method in ("POST","PUT") and "kakao" not in resp.url and "sentry" not in resp.url:
            try:
                upload_reqs.append(f"  RESP {resp.status}: {resp.text()[:300]}")
            except Exception:
                pass

    page.on("request", on_req)
    page.on("response", on_resp)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    page.goto(f"{BLOG_URL}/manage/post/24?returnURL={BLOG_URL}/manage/posts",
              timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=10000)
    page.wait_for_timeout(1000)

    # 첨부 버튼(div) 클릭
    attach_div = page.query_selector("div[title='첨부']")
    if attach_div:
        print("첨부 div 클릭...")
        attach_div.click()
        page.wait_for_timeout(1500)

        # 드롭다운 메뉴 확인
        menu_items = page.evaluate("""() => {
            const items = document.querySelectorAll('.mce-menu-item, .mce-listbox-menu li, [role=menuitem], .mce-panel .mce-menu li');
            return Array.from(items).map(el => ({
                text: el.innerText.trim(),
                cls: el.className.substring(0, 50)
            }));
        }""")
        print(f"드롭다운 메뉴 아이템 {len(menu_items)}개:")
        for item in menu_items:
            print(f"  '{item['text']}' [{item['cls']}]")

        # 파일 관련 메뉴 클릭
        file_menu = next((i for i in menu_items if '파일' in i['text'] or 'PDF' in i['text'] or 'file' in i['text'].lower()), None)
        if file_menu:
            print(f"\n'{file_menu['text']}' 클릭...")
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.locator(f"text={file_menu['text']}").first.click()
            fc = fc_info.value
            print("File chooser 열림!")
            fc.set_files(str(test_pdf))
            page.wait_for_timeout(5000)
        else:
            # 모든 메뉴 항목 클릭 시도
            print("파일 메뉴 못 찾음, 첫 항목 클릭...")
            if menu_items:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.locator(".mce-menu-item").first.click()
                try:
                    fc = fc_info.value
                    print("File chooser 열림!")
                    fc.set_files(str(test_pdf))
                    page.wait_for_timeout(5000)
                except Exception as e:
                    print("File chooser 없음:", str(e)[:60])
    else:
        print("첨부 div 없음")

    ctx.close()

print(f"\n캡처된 요청 {len(upload_reqs)}개:")
for r in upload_reqs:
    print(" ", r)
