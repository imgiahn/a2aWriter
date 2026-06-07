"""tinyMCE selection.setContent + execCommand 방식 테스트"""
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

    page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
    page.wait_for_timeout(1000)

    # 방법 A: selection.select(body) + selection.setContent
    result_a = page.evaluate("""(html) => {
        const ed = tinyMCE.activeEditor;
        try {
            ed.selection.select(ed.getBody(), true);
            ed.selection.setContent(html);
            ed.save();
            return 'A:' + ed.getContent().length;
        } catch(e) { return 'A_err:' + e.message; }
    }""", html)
    print("방법 A:", result_a)

    after_a = page.evaluate("() => tinyMCE.activeEditor.getContent().substring(0, 120)")
    print("A 후 내용 앞120:", after_a)
    changed = "분양가" in after_a or "64A" in after_a or "2026.06.08" in after_a
    print("내용 변경됨:", changed)

    if not changed:
        # 방법 B: unnamed textarea (2206자) React native setter
        result_b = page.evaluate("""(html) => {
            const tas = Array.from(document.querySelectorAll('textarea'));
            const ta = tas.find(t => !t.id && t.value.length > 100);
            if (!ta) return 'B: textarea not found';
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
            setter.call(ta, html);
            ta.dispatchEvent(new Event('input', {bubbles: true}));
            ta.dispatchEvent(new Event('change', {bubbles: true}));
            return 'B:' + ta.value.length;
        }""", html)
        print("방법 B:", result_b)

    # 완료 → 발행
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(3000)

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

time.sleep(3)
r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
m2 = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn', r.text, re.DOTALL)
if m2:
    text = re.sub(r"<[^>]+>", " ", m2.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    if "분양가" in text or "64A" in text:
        print("✅ 수정 확인됨! 앞300:", text[:300])
    else:
        print("❌ 아직 구버전:", text[:200])
