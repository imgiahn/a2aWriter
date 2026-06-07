"""티스토리 편집 디버깅 v2 — 내용 변경 여부 직접 확인"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import re

BLOG_URL = "https://llmenginehistory.tistory.com"

draft = Path("articles/llmenginehistory/draft/20260606_001.html").read_text(encoding="utf-8")
m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", draft, re.DOTALL)
html  = m.group(2)
print("주입할 HTML 앞50자:", html[:50])
print("HTML 길이:", len(html))

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

    # 주입 전 내용 앞 100자 확인
    before = page.evaluate("() => tinyMCE.activeEditor.getContent().substring(0, 100)")
    print("주입 전 내용 앞100자:", before)

    # 내용 주입
    page.evaluate(
        "(html) => { const ed=tinyMCE.activeEditor; ed.focus(); ed.setContent(html); ed.save(); }",
        html
    )
    page.wait_for_timeout(500)

    # 주입 후 내용 앞 100자 확인
    after = page.evaluate("() => tinyMCE.activeEditor.getContent().substring(0, 100)")
    print("주입 후 내용 앞100자:", after)

    if before == after:
        print("❌ 내용 변경 안됨 — HTML 모드로 시도")
        # HTML 모드 전환
        page.locator("button:has-text('기본모드'), .button_mode").first.click()
        page.wait_for_timeout(500)
        page.locator("li:has-text('HTML'), button:has-text('HTML')").first.click()
        page.wait_for_timeout(1500)

        done = page.evaluate("""(html) => {
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {
                cm.CodeMirror.setValue(html);
                console.log('CodeMirror 설정됨');
                return 'codemirror';
            }
            const ta = document.querySelector('textarea#content, textarea.html-editor');
            if (ta) { ta.value = html; return 'textarea'; }
            return null;
        }""", html)
        print("HTML 모드 결과:", done)
    else:
        print("✅ 내용 변경됨")

    # 완료 버튼
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(3000)

    # 모달
    modal = page.locator(".ReactModal__Content.editor_layer")
    try:
        modal.wait_for(state="visible", timeout=5000)
        radio = page.locator("#open20")
        if radio.count() > 0:
            radio.check(timeout=3000)
        page.wait_for_timeout(500)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(4000)
        print("발행 완료. URL:", page.url)
    except Exception as e:
        print("모달 없음:", str(e)[:80])

    ctx.close()

# 발행 후 포스트 내용 확인
import requests, time
time.sleep(2)
r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
for kw in ["table", "분양가", "청약접수", "오피스텔"]:
    if kw in r.text:
        idx = r.text.index(kw)
        chunk = re.sub(r"<[^>]+>", " ", r.text[max(0,idx-50):idx+200])
        print(f"[{kw}] {re.sub(chr(10)+chr(32)+'+', ' ', chunk)[:150]}")
        break
else:
    print("본문 키워드 없음 — HTML 길이:", len(r.text))
