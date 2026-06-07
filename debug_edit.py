"""발행 시 네트워크 요청 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import re, json

BLOG_URL = "https://llmenginehistory.tistory.com"

draft = Path("articles/llmenginehistory/draft/20260606_001.html").read_text(encoding="utf-8")
m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", draft, re.DOTALL)
html  = m.group(2)

api_calls = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_request(req):
        url = req.url
        if any(k in url for k in ["save", "publish", "post", "write", "edit", "entry"]):
            if req.method in ("POST", "PUT", "PATCH"):
                body = ""
                try:
                    body = req.post_data or ""
                except:
                    pass
                api_calls.append({"method": req.method, "url": url, "body": body[:300]})

    page.on("request", on_request)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    edit_url = f"{BLOG_URL}/manage/post/24?returnURL={BLOG_URL}/manage/posts"
    page.goto(edit_url, timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)

    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(1000)

    # 완료 → 발행 (내용 수정 없이 그냥 눌러서 어떤 API 호출되는지 확인)
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(3000)

    modal = page.locator(".ReactModal__Content.editor_layer")
    try:
        modal.wait_for(state="visible", timeout=5000)
        page.locator("#open20").check(timeout=3000)
        page.wait_for_timeout(500)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(4000)
    except Exception as e:
        print("모달 없음:", str(e)[:60])

    ctx.close()

print(f"\n캡처된 API 호출 {len(api_calls)}개:")
for c in api_calls:
    print(f"\n  {c['method']} {c['url']}")
    if c["body"]:
        print(f"  body: {c['body'][:400]}")
