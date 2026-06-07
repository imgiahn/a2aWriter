"""티스토리 첨부 버튼 클릭 → 업로드 API 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path

BLOG_URL = "https://llmenginehistory.tistory.com"

test_pdf = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))[0]
print("테스트 PDF:", test_pdf, "크기:", test_pdf.stat().st_size)

upload_reqs = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method == "POST":
            body = ""
            try:
                body = (req.post_data or "")[:80]
            except Exception:
                pass
            upload_reqs.append(f"POST {req.url[:120]} | body={body}")

    def on_resp(resp):
        if resp.request.method == "POST" and resp.status in (200, 201):
            try:
                body = resp.text()[:200]
                upload_reqs.append(f"  RESP {resp.status}: {body}")
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

    # "첨부" 버튼 클릭 (title="첨부")
    attach_btn = page.query_selector("button[title='첨부']")
    if attach_btn:
        print("첨부 버튼 발견, 클릭...")
        with page.expect_file_chooser(timeout=5000) as fc_info:
            attach_btn.click()
        fc = fc_info.value
        print("File chooser 열림! accept:", fc.is_multiple())
        fc.set_files(str(test_pdf))
        page.wait_for_timeout(5000)
        print("파일 설정 완료")
    else:
        print("첨부 버튼 없음")
        # tistory-attacher 플러그인 직접 호출 시도
        result = page.evaluate("""() => {
            try {
                const ed = tinymce.activeEditor;
                const plugin = ed.plugins['tistory-attacher'];
                return plugin ? Object.getOwnPropertyNames(plugin.__proto__) : 'no plugin';
            } catch(e) { return 'err: ' + e.message; }
        }""")
        print("tistory-attacher 메서드:", result)

    ctx.close()

print(f"\n캡처된 POST 요청:")
for r in upload_reqs:
    print(" ", r)
