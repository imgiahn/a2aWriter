"""원래 발행 시 PUT body 전체 캡처 (truncation 없이)"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
import json

BLOG_URL = "https://llmenginehistory.tistory.com"

captured_body = {}

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_request(req):
        if req.method == "PUT" and "/manage/post/" in req.url and ".json" in req.url:
            try:
                body = req.post_data or ""
                captured_body["raw"] = body
                captured_body["url"] = req.url
            except Exception as e:
                captured_body["err"] = str(e)

    page.on("request", on_request)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    # 포스트 23번(화성동탄2, 이미 정상인 것)으로 테스트 — 내용 바꾸지 않고 그냥 발행
    page.goto(f"{BLOG_URL}/manage/post/23?returnURL={BLOG_URL}/manage/posts",
              timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(500)

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
        print("모달:", str(e)[:60])

    ctx.close()

if "raw" in captured_body:
    try:
        body = json.loads(captured_body["raw"])
        print("PUT URL:", captured_body["url"])
        print("PUT 필드 목록:", list(body.keys()))
        # content 제외하고 나머지 필드 출력
        for k, v in body.items():
            if k != "content":
                print(f"  {k}: {v}")
    except Exception as e:
        print("파싱 오류:", e)
        print("raw 앞500자:", captured_body["raw"][:500])
else:
    print("PUT 캡처 실패:", captured_body)
