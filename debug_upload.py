"""티스토리 파일 업로드 API 탐색"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
import json

BLOG_URL = "https://llmenginehistory.tistory.com"
upload_reqs = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        url = req.url
        if any(k in url for k in ["upload", "attach", "file", "cdn", "storage"]):
            body = ""
            try:
                body = (req.post_data or "")[:100]
            except Exception:
                pass
            upload_reqs.append(f"{req.method} {url[:120]} | {body}")

    page.on("request", on_req)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    page.goto(f"{BLOG_URL}/manage/newpost/", timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # file input 확인
    inputs = page.query_selector_all("input[type='file']")
    print(f"file input {len(inputs)}개:")
    for inp in inputs:
        print(f"  id={inp.get_attribute('id')} name={inp.get_attribute('name')} accept={inp.get_attribute('accept')}")

    # 모든 link/button 중 파일 관련
    all_btns = page.evaluate("""() => {
        const res = [];
        document.querySelectorAll('button,a,[class*="file"],[class*="attach"],[class*="upload"]').forEach(el => {
            const cls = el.className || '';
            const txt = el.innerText || '';
            if (cls.includes('file') || cls.includes('attach') || cls.includes('upload')
                || txt.includes('파일') || txt.includes('첨부')) {
                res.push({tag: el.tagName, cls: cls.substring(0,50), txt: txt.substring(0,20)});
            }
        });
        return res;
    }""")
    print(f"\n파일 관련 요소 {len(all_btns)}개:")
    for b in all_btns[:10]:
        print(f"  {b}")

    ctx.close()

print(f"\n캡처된 upload 요청 {len(upload_reqs)}개:")
for r in upload_reqs:
    print(" ", r)
