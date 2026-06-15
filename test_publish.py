"""
1. 카카오 자동 로그인으로 세션 갱신
2. 20260606_008 (신검단 무순위) 삭제
3. 에버그린 Task 생성 → writer → publisher 시범 발행
"""
import re, sys, os, json, requests, shutil
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BLOG_URL = "https://llmenginehistory.tistory.com"
EMAIL    = os.getenv("KAKAO_EMAIL", "")
PASSWORD = os.getenv("KAKAO_PASSWORD", "")

def auto_login_server(ctx):
    page = ctx.new_page()
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    if "/manage" in page.url and "login" not in page.url:
        print("✅ 기존 세션 유효")
        return page
    print("  세션 만료 → 카카오 자동 로그인 시도...")
    page.goto("https://www.tistory.com/auth/login", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    page.locator("a.link_kakao_id").click()
    page.wait_for_load_state("networkidle", timeout=15000)
    if "accounts.kakao.com" in page.url:
        page.locator("input[name='loginId']").fill(EMAIL)
        page.locator("input[name='password']").fill(PASSWORD)
        page.locator("button[type='submit']").click()
        page.wait_for_load_state("networkidle", timeout=15000)
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    if "/manage" in page.url and "login" not in page.url:
        print("✅ 로그인 성공")
    else:
        print(f"❌ 로그인 실패: {page.url}")
        sys.exit(1)
    return page

def get_posts(cookies):
    posts = []
    for pg in range(1, 5):
        r = requests.get(
            f"{BLOG_URL}/manage/post/posts.json",
            params={"page": pg, "countPerPage": 30},
            cookies=cookies, headers={"Referer": BLOG_URL}, timeout=15,
        )
        if r.status_code != 200: break
        items = r.json().get("posts", [])
        posts.extend(items)
        if len(items) < 30: break
    return posts

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage", "--disable-gpu"]
    )
    page = auto_login_server(ctx)
    cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain", "")}

    # ── 1. 20260606_008 삭제 ─────────────────────────────
    print("\n[1단계] 20260606_008 삭제 중...")
    posts = get_posts(cookies)
    print(f"  포스트 {len(posts)}개 확인")
    
    target_id = None
    for p in posts:
        t = p.get("title", "")
        if "신검단" in t and "금강펜테리움" in t and "무순위" in t and "(3차)" not in t:
            target_id = p["id"]
            print(f"  삭제 대상: post_id={target_id} | {t}")
            break
    
    if not target_id:
        print("  ⚠️  삭제 대상 못 찾음 — 전체 목록 확인:")
        for p in posts: print(f"    {p['id']}: {p['title']}")
        ctx.close(); sys.exit(1)
    
    r = requests.delete(
        f"{BLOG_URL}/manage/post/{target_id}.json",
        cookies=cookies,
        headers={"Referer": f"{BLOG_URL}/manage/post/", "Origin": BLOG_URL, "X-Requested-With": "XMLHttpRequest"},
        timeout=15,
    )
    if r.status_code in (200, 204):
        print(f"  ✅ 삭제 완료 (post_id={target_id})")
        # 로컬 task 파일도 정리
        task_f = Path("blogs/llmenginehistory/tasks/published/20260606_008.md")
        if task_f.exists():
            task_f.rename(task_f.parent / "20260606_008_deleted.md")
    else:
        print(f"  ❌ 삭제 실패: HTTP {r.status_code} {r.text[:100]}")

    ctx.close()

print("\n세션 갱신 완료. writer + publisher는 별도 실행합니다.")
