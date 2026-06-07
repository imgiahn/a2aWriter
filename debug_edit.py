"""textarea 직접 수정 + 스크린샷으로 에디터 상태 확인"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import re, requests, time

BLOG_URL = "https://llmenginehistory.tistory.com"

draft = Path("articles/llmenginehistory/draft/20260606_001.html").read_text(encoding="utf-8")
m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", draft, re.DOTALL)
html  = m.group(2)

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    edit_url = f"{BLOG_URL}/manage/post/24?returnURL={BLOG_URL}/manage/posts"
    page.goto(edit_url, timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # 스크린샷
    page.screenshot(path="/tmp/editor_state.png")
    print("스크린샷 저장됨")

    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(1000)

    # tinyMCE 연결 textarea + 모든 텍스트 영역 확인
    info = page.evaluate("""(html) => {
        const ed = tinyMCE.activeEditor;
        const results = {};

        // tinyMCE가 연결된 textarea
        const targetId = ed ? ed.id : null;
        results.editorId = targetId;
        results.editorElType = targetId ? (document.getElementById(targetId) ? document.getElementById(targetId).tagName : 'notfound') : 'none';

        // 모든 textarea
        const tas = Array.from(document.querySelectorAll('textarea'));
        results.textareas = tas.map(ta => ({
            id: ta.id, name: ta.name, len: ta.value.length
        }));

        // textarea에 직접 설정 시도
        const ta = document.getElementById(targetId);
        if (ta) {
            ta.value = html;
            // React/Vue 상태 업데이트 트리거
            const evt = new Event('input', {bubbles: true});
            ta.dispatchEvent(evt);
            results.taSet = ta.value.length;
        }

        // tinyMCE에도 알림
        if (ed) {
            ed.setContent(html);
            ed.save();
            results.edContent = ed.getContent().length;
        }

        return results;
    }""", html)
    print("tinyMCE 에디터 ID:", info.get("editorId"))
    print("연결 element 타입:", info.get("editorElType"))
    print("Textarea들:", info.get("textareas"))
    print("textarea 설정 결과:", info.get("taSet"))
    print("tinyMCE getContent 길이:", info.get("edContent"))

    page.wait_for_timeout(500)

    # 완료 → 발행
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(3000)
    page.screenshot(path="/tmp/after_complete.png")

    modal = page.locator(".ReactModal__Content.editor_layer")
    try:
        modal.wait_for(state="visible", timeout=5000)
        page.locator("#open20").check(timeout=3000)
        page.wait_for_timeout(500)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(4000)
        print("발행 완료")
    except Exception as e:
        print("모달 없음:", str(e)[:60])

    ctx.close()

# 검증
time.sleep(3)
r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
m2 = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn', r.text, re.DOTALL)
if m2:
    text = re.sub(r"<[^>]+>", " ", m2.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    if "분양가" in text and "64A" in text:
        print("✅ 수정 확인됨!")
    else:
        print("❌ 아직 구버전:", text[:200])
