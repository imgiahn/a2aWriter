"""tinyMCE 내부에서 첨부 버튼 탐색 + 업로드 API 캡처"""
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
        if req.method == "POST" and "kakao" not in req.url and "sentry" not in req.url:
            upload_reqs.append(f"POST {req.url[:150]}")
    def on_resp(resp):
        if resp.request.method == "POST" and "kakao" not in resp.url and "sentry" not in resp.url:
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

    # tinyMCE 모든 버튼 탐색 (JavaScript 내부)
    btn_info = page.evaluate("""() => {
        const btns = document.querySelectorAll('[title],[aria-label]');
        return Array.from(btns)
            .filter(el => {
                const t = el.getAttribute('title') || el.getAttribute('aria-label') || '';
                return t.includes('첨부') || t.includes('파일') || t.includes('attach') || t.includes('file');
            })
            .map(el => ({
                tag: el.tagName,
                title: el.getAttribute('title') || el.getAttribute('aria-label'),
                cls: el.className.substring(0, 60),
                id: el.id
            }));
    }""")
    print(f"첨부/파일 관련 요소 {len(btn_info)}개:")
    for b in btn_info:
        print(f"  {b}")

    # tinyMCE 버튼 컨트롤로 직접 클릭
    click_result = page.evaluate("""() => {
        try {
            const ed = tinymce.activeEditor;
            // 컨트롤 목록에서 파일 버튼 찾기
            const controls = ed.theme.panel ? ed.theme.panel.find('button') : [];
            const fileBtn = controls.filter(c => {
                const t = c.tooltip && c.tooltip() || c.settings && c.settings.tooltip || '';
                return t.includes('첨부') || t.includes('파일');
            });
            if (fileBtn.length > 0) {
                fileBtn[0].fire('click');
                return 'clicked: ' + (fileBtn[0].tooltip ? fileBtn[0].tooltip() : 'btn');
            }
            return 'not found. controls=' + controls.length;
        } catch(e) { return 'err: ' + e.message; }
    }""")
    print("버튼 클릭 결과:", click_result)

    # file chooser 대기
    try:
        with page.expect_file_chooser(timeout=4000) as fc_info:
            pass
        fc = fc_info.value
        print("File chooser 열림!")
        fc.set_files(str(test_pdf))
        page.wait_for_timeout(5000)
    except Exception as e:
        print("File chooser 없음:", str(e)[:60])

    # 대안: tistory-attacher 직접 호출
    attacher_result = page.evaluate("""() => {
        try {
            const ed = tinymce.activeEditor;
            // tistory-attacher 플러그인의 openDialog 등 시도
            const a = ed.plugins['tistory-attacher'];
            const methods = [];
            for (let key in a) methods.push(key);
            return 'attacher methods: ' + methods.join(', ');
        } catch(e) { return 'err: ' + e.message; }
    }""")
    print("attacher:", attacher_result)

    ctx.close()

print(f"\n캡처된 POST 요청 {len(upload_reqs)}개:")
for r in upload_reqs:
    print(" ", r)
