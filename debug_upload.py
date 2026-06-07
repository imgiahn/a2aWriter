"""티스토리 파일 업로드 API 엔드포인트 캡처"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
import json
from pathlib import Path

BLOG_URL = "https://llmenginehistory.tistory.com"

# 테스트용 PDF (실제 있는 것 사용)
test_pdfs = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))
if not test_pdfs:
    print("PDF 없음")
    exit(1)
test_pdf = test_pdfs[0]
print("테스트 PDF:", test_pdf)

upload_reqs = []

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method == "POST":
            url = req.url
            upload_reqs.append(f"POST {url[:150]}")

    page.on("request", on_req)

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    # 기존 포스트 편집 페이지 (신규보다 안정적)
    page.goto(f"{BLOG_URL}/manage/post/24?returnURL={BLOG_URL}/manage/posts",
              timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # tinyMCE 툴바에서 파일 업로드 버튼 탐색
    toolbar_info = page.evaluate("""() => {
        const btns = document.querySelectorAll('.mce-btn, .mce-toolbar button, [class*="mce"][class*="btn"]');
        return Array.from(btns).map(b => ({
            title: b.getAttribute('title') || b.getAttribute('aria-label') || '',
            cls: b.className.substring(0, 60)
        })).filter(b => b.title);
    }""")
    print(f"tinyMCE 툴바 버튼 {len(toolbar_info)}개:")
    for b in toolbar_info:
        print(f"  {b['title']}")

    # 파일 업로드 관련 전역 함수/객체 탐색
    file_api = page.evaluate("""() => {
        const keys = Object.keys(window).filter(k =>
            k.toLowerCase().includes('file') ||
            k.toLowerCase().includes('upload') ||
            k.toLowerCase().includes('attach')
        );
        return keys.slice(0, 20);
    }""")
    print("파일 관련 전역 변수:", file_api)

    # tinyMCE 플러그인 목록
    plugins = page.evaluate("""() => {
        try {
            return Object.keys(tinymce.activeEditor.plugins);
        } catch(e) { return []; }
    }""")
    print("tinyMCE 플러그인:", plugins)

    # fileUpload 플러그인 직접 실행 시도
    file_btn = page.evaluate("""() => {
        try {
            const ed = tinymce.activeEditor;
            const plugin = ed.plugins.fileUpload || ed.plugins['file-upload'];
            if (plugin) {
                return Object.keys(plugin);
            }
        } catch(e) {}
        return null;
    }""")
    print("fileUpload 플러그인 키:", file_btn)

    # file chooser 잡아서 PDF 업로드 시도
    with page.expect_file_chooser(timeout=5000) as fc_info:
        # tinyMCE 파일 버튼 클릭 시도
        result = page.evaluate("""() => {
            try {
                const ed = tinymce.activeEditor;
                ed.execCommand('mceFileUpload');
                return 'execCommand done';
            } catch(e) {
                return 'err: ' + e.message;
            }
        }""")
        print("execCommand 결과:", result)

    try:
        fc = fc_info.value
        print("File chooser 열림! 파일 설정 중...")
        fc.set_files(str(test_pdf))
        page.wait_for_timeout(5000)
    except Exception as e:
        print("File chooser 없음:", str(e)[:80])

    ctx.close()

print(f"\n캡처된 POST 요청 {len(upload_reqs)}개:")
for r in upload_reqs:
    print(" ", r)
