"""iframe body 직접 주입 방식 테스트"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import re, requests, time

BLOG_URL = "https://llmenginehistory.tistory.com"

draft = Path("articles/llmenginehistory/draft/20260606_001.html").read_text(encoding="utf-8")
m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", draft, re.DOTALL)
html  = m.group(2)
print("주입 HTML 앞80자:", html[:80])

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

    # 모든 iframe 확인
    frames_info = page.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        return Array.from(iframes).map((f, i) => ({
            idx: i, id: f.id, name: f.name, src: f.src.substring(0,80),
            hasBody: !!(f.contentDocument && f.contentDocument.body),
            bodyLen: f.contentDocument && f.contentDocument.body ? f.contentDocument.body.innerHTML.length : 0
        }));
    }""")
    print(f"iframe {len(frames_info)}개:")
    for fi in frames_info:
        print(f"  [{fi['idx']}] id={fi['id']} hasBody={fi['hasBody']} bodyLen={fi['bodyLen']}")

    # tinyMCE iframe body에 직접 주입
    result = page.evaluate("""(html) => {
        const ed = tinyMCE.activeEditor;
        if (!ed) return 'no editor';

        // 방법 1: iframe body 직접
        const iframe = ed.iframeElement || document.querySelector('iframe[id*=\"mce\"]');
        if (iframe && iframe.contentDocument && iframe.contentDocument.body) {
            iframe.contentDocument.body.innerHTML = html;
            // tinyMCE에 변경 알림
            ed.nodeChanged();
            ed.save();
            return 'iframe_direct:' + iframe.contentDocument.body.innerHTML.length;
        }

        // 방법 2: ed.dom
        if (ed.getBody) {
            ed.getBody().innerHTML = html;
            ed.nodeChanged();
            ed.save();
            return 'getBody:' + ed.getBody().innerHTML.length;
        }

        return 'failed';
    }""", html)
    print("주입 결과:", result)

    page.wait_for_timeout(500)

    # 주입 후 에디터 내용 확인
    after = page.evaluate("() => tinyMCE.activeEditor.getContent().substring(0, 100)")
    print("주입 후 에디터 앞100자:", after)

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

# 발행 후 포스트 내용 검증
time.sleep(3)
r = requests.get("https://llmenginehistory.tistory.com/24",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
m2 = re.search(r'class="tt_article_useless_p_margin[^"]*">(.*?)<div class="container_postbtn', r.text, re.DOTALL)
if m2:
    text = re.sub(r"<[^>]+>", " ", m2.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    print("발행 후 포스트 앞300자:", text[:300])
    # 수정됐는지 확인
    if "분양가" in text and "64A" in text:
        print("✅ 수정 확인됨! (분양가/타입 정보 포함)")
    else:
        print("❌ 아직 구버전")
else:
    print("본문 패턴 없음")
