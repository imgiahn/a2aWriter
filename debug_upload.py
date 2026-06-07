"""tinyMCE 첨부 드롭다운 클릭 → 파일 업로드 → PUT attachments 형식 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import json

BLOG_URL = "https://llmenginehistory.tistory.com"
test_pdf  = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))[0]
put_bodies = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method == "PUT" and "/manage/post/" in req.url:
            try:
                put_bodies.append(json.loads(req.post_data or "{}"))
            except Exception:
                pass

    page.on("request", on_req)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    page.goto(f"{BLOG_URL}/manage/newpost/", timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(1000)

    # 방법: tinyMCE 플러그인의 uploadForFile 직접 호출
    # → 파일 업로드 후 에디터에 어떤 HTML이 삽입되는지 확인
    upload_result = page.evaluate("""async (pdfUrl) => {
        try {
            const ed = tinymce.activeEditor;
            const plugin = ed.plugins.fileUpload;

            // Blob으로 파일 생성 후 업로드
            const resp = await fetch(pdfUrl);
            const blob = await resp.blob();
            const file = new File([blob], 'test.pdf', {type: 'application/pdf'});

            return new Promise((resolve) => {
                plugin.uploadForFile({
                    file: file,
                    filename: 'test_attach.pdf',
                    callback: function(result) {
                        resolve(result);
                    }
                });
            });
        } catch(e) {
            return {error: e.message};
        }
    }""", f"{BLOG_URL}/manage")

    print("upload_result:", json.dumps(upload_result, ensure_ascii=False, indent=2)[:500])

    # 에디터 HTML 확인
    editor_html = page.evaluate("() => tinymce.activeEditor.getContent()")
    print("\n에디터 HTML (업로드 후):", editor_html[:500])

    ctx.close()

print(f"\nPUT body {len(put_bodies)}개")
