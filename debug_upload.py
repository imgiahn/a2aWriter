"""파일 첨부 후 PUT attachments 형식 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import json

BLOG_URL = "https://llmenginehistory.tistory.com"
test_pdf = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))[0]

put_bodies = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method == "PUT" and "/manage/post/" in req.url and ".json" in req.url:
            try:
                body = json.loads(req.post_data or "{}")
                put_bodies.append(body)
            except Exception:
                pass

    page.on("request", on_req)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    # 포스트 23번 편집
    page.goto(f"{BLOG_URL}/manage/post/23?returnURL={BLOG_URL}/manage/posts",
              timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(1000)

    # 첨부 버튼 클릭 → 드롭다운에서 파일 선택
    attach_btn = page.query_selector("[title='첨부']")
    if not attach_btn:
        # 버튼이 툴바 내부에 있을 경우
        attach_btn = page.evaluate_handle("""() => {
            return Array.from(document.querySelectorAll('[title]'))
                .find(el => el.getAttribute('title') === '첨부');
        }""")

    print("첨부 버튼:", attach_btn)

    # tinyMCE 첨부 플러그인 직접 접근
    file_menu_items = page.evaluate("""() => {
        try {
            const ed = tinymce.activeEditor;
            const plugin = ed.plugins['fileUpload'];
            // fileUpload 플러그인의 내부 상태 확인
            return {
                keys: Object.keys(plugin || {}),
                uploadUrl: ed.settings.fileUpload ? ed.settings.fileUpload.upload_url : null
            };
        } catch(e) { return {err: e.message}; }
    }""")
    print("fileUpload 플러그인:", json.dumps(file_menu_items, ensure_ascii=False))

    # 완료 → 발행 (파일 없이 그냥 발행해서 기존 attachments 포맷 확인)
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    modal = page.locator(".ReactModal__Content.editor_layer")
    try:
        modal.wait_for(state="visible", timeout=5000)
        page.locator("#open20").check(timeout=3000)
        page.wait_for_timeout(500)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(3000)
    except Exception as e:
        print("모달:", str(e)[:60])

    ctx.close()

print(f"\n캡처된 PUT body {len(put_bodies)}개:")
for b in put_bodies:
    print("attachments:", b.get("attachments", "없음"))
    print("기타 필드:", [k for k in b.keys() if k != "content"])
