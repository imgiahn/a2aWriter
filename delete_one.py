import os, sys, re, requests, json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BLOG_URL = "https://llmenginehistory.tistory.com"
EMAIL    = os.getenv("KAKAO_EMAIL", "")
PASSWORD = os.getenv("KAKAO_PASSWORD", "")

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage","--disable-gpu","--no-sandbox"]
    )
    page = ctx.new_page()

    # 로그인
    try:
        page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
    except: pass
    if "login" in page.url:
        try: page.goto("https://www.tistory.com/auth/login", timeout=20000, wait_until="domcontentloaded")
        except: pass
        page.wait_for_timeout(1000)
        page.locator("a.link_kakao_id").click()
        page.wait_for_timeout(3000)
        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(EMAIL)
            page.locator("input[name='password']").fill(PASSWORD)
            page.locator("button[type='submit']").click()
            page.wait_for_timeout(5000)
        try: page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
        except: pass
    print("로그인 URL:", page.url)

    # 포스트 목록 (apply_pdf_attachments 방식)
    posts = []
    for n in range(1, 5):
        page.goto(BLOG_URL + "/manage/posts?page=" + str(n), timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(2000)
        try: page.wait_for_selector("a.link_cont", timeout=8000)
        except: pass
        result = page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('a.link_cont').forEach(lk => {
                const li = lk.closest('li');
                const btn = li ? li.querySelector('a.btn_post') : null;
                if (!btn) return;
                const m = btn.getAttribute('href').match(/\/manage\/post\/(\d+)/);
                if (m) items.push({id: parseInt(m[1]),
                    title: (lk.getAttribute('title')||lk.textContent).trim()});
            });
            return items;
        }""")
        posts.extend(result)
        if not result or not page.query_selector("a[href*='page=" + str(n+1) + "']"):
            break

    print("포스트", len(posts), "개")

    # 삭제 대상 찾기
    target_id = None
    for p in posts:
        t = p.get("title", "")
        if "신검단" in t and "금강펜테리움" in t and "무순위" in t and "3차" not in t:
            target_id = p["id"]
            print("삭제 대상:", target_id, "|", t)
            break

    if not target_id:
        print("삭제 대상 못 찾음. 전체 목록:")
        for p in posts: print(" ", p["id"], p["title"])
        ctx.close(); sys.exit(1)

    # Playwright로 삭제 버튼 클릭
    page.goto(BLOG_URL + "/manage/posts", timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(1000)

    # 삭제: manage/post/{id} DELETE API
    cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain","")}
    r = requests.delete(
        BLOG_URL + "/manage/post/" + str(target_id) + ".json",
        cookies=cookies,
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": BLOG_URL + "/manage/posts",
            "Origin": BLOG_URL,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        timeout=15,
    )
    print("DELETE HTTP", r.status_code, r.text[:200])

    if r.status_code in (200, 204):
        print("삭제 완료!")
    else:
        # 페이지 네비게이션으로 삭제 시도
        print("API 삭제 실패 -> JS 클릭 방식 시도")
        page.goto(BLOG_URL + "/manage/post/" + str(target_id), timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(1000)
        print("편집 페이지 URL:", page.url)

    ctx.close()
