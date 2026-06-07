"""tinyMCE 초기화 설정에서 upload_url 추출"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import json

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
            body = ""
            try:
                body = (req.post_data or "")[:200]
            except Exception:
                pass
            upload_reqs.append(f"{req.method} {req.url[:150]}\n  body={body}")
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

    # 신규 글 페이지 (에디터 초기화 설정 확인)
    page.goto(f"{BLOG_URL}/manage/newpost/", timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=10000)
    page.wait_for_timeout(1000)

    # tinyMCE 설정에서 fileUpload 설정 추출
    config = page.evaluate("""() => {
        try {
            const ed = tinymce.activeEditor;
            const fu = ed.settings.fileUpload || {};
            return {
                upload_url: fu.upload_url || null,
                upload_handler: typeof fu.upload_handler,
                max_size: fu.max_size,
                max_count: fu.max_count,
                all_settings_keys: Object.keys(ed.settings).filter(k =>
                    k.includes('upload') || k.includes('file') || k.includes('attach')
                )
            };
        } catch(e) { return {err: e.message}; }
    }""")
    print("fileUpload 설정:", json.dumps(config, ensure_ascii=False, indent=2))

    # upload_url이 있으면 직접 POST 테스트
    upload_url = config.get("upload_url")
    if upload_url:
        print(f"\nupload_url 발견: {upload_url}")

        # 실제 파일 업로드 시도 (Playwright 내부에서)
        result = page.evaluate(f"""async () => {{
            try {{
                const ed = tinymce.activeEditor;
                const url = "{upload_url}";
                const resp = await fetch(url, {{method:'GET'}});
                return 'GET ' + url + ' -> ' + resp.status;
            }} catch(e) {{ return 'err: ' + e.message; }}
        }}""")
        print("URL GET 테스트:", result)
    else:
        # 첨부 버튼 찾기 (신규 글 페이지)
        btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[title]'))
                .filter(el => el.getAttribute('title').includes('첨부'))
                .map(el => ({tag: el.tagName, title: el.getAttribute('title'), id: el.id, cls: el.className.substring(0,50)}));
        }""")
        print(f"\n첨부 버튼 {len(btns)}개:", btns)

        if btns:
            # 첫 번째 첨부 버튼 클릭
            print("첨부 버튼 클릭...")
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.evaluate("""() => {
                    const el = document.querySelector('[title*="첨부"]');
                    if (el) el.click();
                }""")
            try:
                fc = fc_info.value
                print("File chooser 열림! 파일 설정...")
                fc.set_files(str(test_pdf))
                page.wait_for_timeout(6000)
            except Exception as e:
                print("File chooser 없음:", str(e)[:60])

    ctx.close()

print(f"\n캡처된 POST/PUT 요청 {len(upload_reqs)}개:")
for r in upload_reqs:
    print(r)
