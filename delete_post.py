"""
1단계: 20260606_008 (신검단중앙역 금강펜테리움 센트럴파크 무순위(사후)) 티스토리 삭제
2단계: 에버그린 Task 생성 후 writer + publisher 시범 실행
"""
import re, json, requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BLOG_URL = "https://llmenginehistory.tistory.com"
TARGET_TITLE = "신검단중앙역 금강펜테리움 센트럴파크 무순위(사후) 신청 조건"

def get_posts(cookies):
    """전체 포스트 목록 가져오기"""
    posts = []
    page = 1
    while True:
        r = requests.get(
            f"{BLOG_URL}/manage/post/posts.json",
            params={"page": page, "countPerPage": 30},
            cookies=cookies,
            headers={"Referer": BLOG_URL},
            timeout=15,
        )
        if r.status_code != 200:
            break
        data = r.json()
        items = data.get("posts", [])
        if not items:
            break
        posts.extend(items)
        if len(items) < 30:
            break
        page += 1
    return posts

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage", "--disable-gpu"]
    )
    page = ctx.new_page()
    page.goto(f"{BLOG_URL}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    
    if "login" in page.url:
        print("❌ 로그인 세션 만료")
        ctx.close()
        exit(1)
    
    print("✅ 로그인 확인")
    cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain", "")}
    
    # 포스트 목록 조회
    posts = get_posts(cookies)
    print(f"포스트 {len(posts)}개 확인")
    
    # 삭제 대상 찾기
    target_id = None
    for p in posts:
        title_clean = re.sub(r"^[🏠\s]+", "", p.get("title", "")).strip()
        if "신검단" in title_clean and "3차" not in title_clean and "금강펜테리움" in title_clean and "무순위" in title_clean:
            target_id = p["id"]
            print(f"삭제 대상: post_id={target_id}, 제목={p['title']}")
            break
    
    if not target_id:
        # 번호로 찾기
        for p in posts:
            if "신검단중앙역 금강펜테리움" in p.get("title", "") and "무순위" in p.get("title", ""):
                target_id = p["id"]
                print(f"삭제 대상: post_id={target_id}, 제목={p['title']}")
                break
    
    if not target_id:
        print("⚠️  삭제 대상 포스트 못 찾음. 전체 목록:")
        for p in posts:
            print(f"  {p['id']}: {p['title']}")
        ctx.close()
        exit(1)
    
    # 삭제 실행
    del_r = requests.delete(
        f"{BLOG_URL}/manage/post/{target_id}.json",
        cookies=cookies,
        headers={
            "Referer": f"{BLOG_URL}/manage/post/",
            "Origin": BLOG_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=15,
    )
    print(f"삭제 응답: HTTP {del_r.status_code}")
    if del_r.status_code in (200, 204):
        print(f"✅ 삭제 완료: post_id={target_id}")
    else:
        print(f"❌ 삭제 실패: {del_r.text[:200]}")
    
    ctx.close()
