import os, sys, re, requests
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
    try:
        page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
    except Exception as e:
        print("goto 오류(무시):", e)
    print("현재 URL:", page.url)

    if "login" in page.url or "manage" not in page.url:
        print("세션 만료 -> 카카오 로그인 시도")
        try:
            page.goto("https://www.tistory.com/auth/login", timeout=20000, wait_until="domcontentloaded")
        except:
            pass
        page.wait_for_timeout(2000)
        page.locator("a.link_kakao_id").click()
        page.wait_for_timeout(3000)
        print("카카오 URL:", page.url)
        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(EMAIL)
            page.locator("input[name='password']").fill(PASSWORD)
            page.locator("button[type='submit']").click()
            page.wait_for_timeout(5000)
        print("로그인 후 URL:", page.url)
        try:
            page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
        except:
            pass
        page.wait_for_timeout(2000)
        print("최종 URL:", page.url)

    cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain","")}
    print("쿠키 수:", len(cookies))

    r = requests.get(BLOG_URL + "/manage/post/posts.json",
        params={"page":1,"countPerPage":30}, cookies=cookies,
        headers={"Referer":BLOG_URL}, timeout=15)
    print("posts.json: HTTP", r.status_code)
    posts = r.json().get("posts",[]) if r.status_code==200 else []
    for p in posts:
        if "신검단" in p.get("title","") and "금강펜테리움" in p.get("title",""):
            print("  찾음:", p["id"], "|", p["title"])

    ctx.close()
