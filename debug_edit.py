"""티스토리 포스트 편집 단계별 디버깅"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import re

BLOG_URL = "https://llmenginehistory.tistory.com"

draft = Path("articles/llmenginehistory/draft/20260606_001.html").read_text(encoding="utf-8")
m     = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", draft, re.DOTALL)
title = m.group(1)
html  = m.group(2)
print("제목:", title)
print("HTML 길이:", len(html))

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)

    # 편집 페이지 접속
    edit_url = f"{BLOG_URL}/manage/post/24?returnURL={BLOG_URL}/manage/posts"
    print("편집 URL:", edit_url)
    page.goto(edit_url, timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(3000)
    print("현재 URL:", page.url)

    # tinyMCE 대기
    try:
        page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=12000)
        print("tinyMCE 로드됨")
    except Exception as e:
        print("tinyMCE 없음:", e)

    # 현재 에디터 내용 길이
    cur_len = page.evaluate("() => { try { return tinyMCE.activeEditor.getContent().length } catch(e) { return -1 } }")
    print("현재 에디터 내용 길이:", cur_len)

    # 내용 주입
    injected = page.evaluate(
        "(html) => { try { const ed=tinyMCE.activeEditor; ed.focus(); ed.setContent(html); ed.save(); return tinyMCE.activeEditor.getContent().length } catch(e) { return -1 } }",
        html
    )
    print("주입 후 에디터 내용 길이:", injected)

    # 완료 버튼
    btn = page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first
    print("완료 버튼 visible:", btn.is_visible(timeout=3000))
    btn.click()
    page.wait_for_timeout(3000)
    print("완료 버튼 클릭 후 URL:", page.url)

    # 모달 확인
    modal = page.locator(".ReactModal__Content.editor_layer")
    try:
        modal.wait_for(state="visible", timeout=5000)
        print("모달 나타남")
        print("모달 내용:", modal.inner_text()[:300])
        # 공개 라디오 체크
        radio = page.locator("#open20")
        if radio.count() > 0:
            radio.check(timeout=3000)
            print("공개 라디오 체크됨")
        page.wait_for_timeout(500)
        # publish-btn
        pub_btn = page.query_selector("#publish-btn")
        if pub_btn:
            print("publish-btn 있음:", pub_btn.inner_text())
            page.evaluate("document.getElementById('publish-btn').click()")
            page.wait_for_timeout(3000)
            print("publish-btn 클릭 후 URL:", page.url)
        else:
            print("publish-btn 없음 — 버튼 목록:", [b.inner_text()[:20] for b in page.query_selector_all("button")])
    except Exception as e:
        print("모달 없음:", str(e)[:100])
        print("페이지 버튼들:", [b.inner_text()[:20] for b in page.query_selector_all("button")[:10]])

    ctx.close()
