"""
apply_thumbnails.py — 기존 발행 글에 AI 썸네일 일괄 적용

gpt-image-2로 각 공고 썸네일 생성 → content 첫 번째 이미지로 삽입 → og:image 자동 설정
"""

import re
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

load_dotenv()

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")

# 이미 처리한 포스트 (스킵)
SKIP_POST_IDS = {24}


def parse_task(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("notice_name", "region", "housing_category", "supply_type",
                    "has_pdf", "task_id"):
            if line.startswith(f"{key}:"):
                result[key] = line.split(":", 1)[1].strip()
    result["task_id"] = path.stem
    return result


def find_post_id(posts: list, notice_name: str) -> int:
    clean = re.sub(r"\([^)]*\)", "", notice_name)
    clean = re.sub(r"\[[^\]]*\]", "", clean)
    clean = re.sub(r"\s+", "", clean.strip())
    for length in [10, 8, 6, 5, 4]:
        kw = clean[:length]
        if not kw:
            continue
        for p in posts:
            if kw in re.sub(r"\s+", "", p["title"]):
                return p["id"]
    return 0


def get_post_html(task_id: str) -> str:
    """기존 발행 HTML 읽기 (published > preview > draft 순)."""
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            return re.sub(r"<!-- TITLE: .+? -->\n?", "",
                          p.read_text(encoding="utf-8"), flags=re.DOTALL)
    return ""


def apply_thumbnail(post_id: int, post_title: str, task: dict,
                    cookies: dict) -> bool:
    task_id   = task["task_id"]
    post_html = get_post_html(task_id)

    # 이미지 생성
    img_bytes = generate_thumbnail(task)
    if not img_bytes:
        return False

    # 업로드
    cdn_url = upload_thumbnail_to_tistory(img_bytes, BLOG_URL, cookies)
    if not cdn_url:
        return False

    # content 앞에 이미지 삽입
    img_html = (
        f'<figure style="margin:0 0 16px 0; text-align:center;">'
        f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
        f'alt="{task.get("notice_name", "")} 썸네일">'
        f'</figure>\n'
    )
    new_content = img_html + post_html

    slogan = re.sub(r"[^\w\s가-힣]", "", post_title)
    slogan = re.sub(r"\s+", "-", slogan.strip())
    payload = {
        "id": str(post_id), "title": post_title, "content": new_content,
        "slogan": slogan, "visibility": 20, "category": 0,
        "tag": "", "acceptComment": 1, "published": 0,
        "password": "", "uselessMarginForEntry": 1,
        "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
        "thumbnail": cdn_url, "type": "post", "attachments": [],
        "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
    }
    hdrs = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"{BLOG_URL}/manage/newpost/{post_id}?type=post",
        "Origin": BLOG_URL, "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }
    r = requests.put(f"{BLOG_URL}/manage/post/{post_id}.json",
                     json=payload, cookies=cookies, headers=hdrs, timeout=20)
    return r.status_code in (200, 201, 204)


def main():
    print("=" * 55)
    print("기존 발행 글 AI 썸네일 일괄 적용")
    print("=" * 55)

    # task 수집
    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem.startswith("test_"):
            continue
        targets.append(parse_task(tf))

    # 단일 Playwright 세션
    posts = []
    cookies = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()

        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            print("자동 로그인 중...")
            auto_login(page, BLOG_URL)
        print("✅ 로그인 확인\n")

        for page_num in range(1, 10):
            page.goto(f"{BLOG_URL}/manage/posts?page={page_num}",
                      timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            try:
                page.wait_for_selector("a.link_cont", timeout=8000)
            except Exception:
                pass
            result = page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('a.link_cont').forEach(lk => {
                    const container = lk.closest('li')
                        || lk.parentElement.parentElement.parentElement.parentElement;
                    const btn = container ? container.querySelector('a.btn_post') : null;
                    if (!btn) return;
                    const m = btn.getAttribute('href').match(/\\/manage\\/post\\/(\\d+)/);
                    if (m) items.push({
                        id: parseInt(m[1]),
                        title: (lk.getAttribute('title') || lk.textContent).trim()
                    });
                });
                return items;
            }""")
            posts.extend(result)
            if not result or not page.query_selector(f"a[href*='page={page_num + 1}']"):
                break

        cookies = {c["name"]: c["value"] for c in ctx.cookies()
                   if "tistory" in c.get("domain", "")}
        ctx.close()

    print(f"포스트 {len(posts)}개 목록:")
    for p in posts:
        print(f"  [{p['id']}] {p['title'][:45]}")

    print(f"\n쿠키 {len(cookies)}개 | 썸네일 적용 시작\n" + "=" * 55)

    ok = skip = 0
    for t in targets:
        notice_name = t.get("notice_name", "")
        task_id     = t["task_id"]

        post_id = find_post_id(posts, notice_name)
        if not post_id:
            print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:30]}")
            skip += 1
            continue

        if post_id in SKIP_POST_IDS:
            print(f"[{task_id}] ⏭️  스킵 (이미 처리): 포스트 {post_id}")
            skip += 1
            continue

        post_title = next((p["title"] for p in posts if p["id"] == post_id), notice_name)
        print(f"\n[{task_id}] 포스트 {post_id} — {notice_name[:30]}")

        if apply_thumbnail(post_id, post_title, t, cookies):
            print(f"  ✅ 완료")
            ok += 1
        else:
            print(f"  ❌ 실패")
            skip += 1

    print(f"\n✅ 완료 — 성공 {ok}개 / 실패·스킵 {skip}개")


if __name__ == "__main__":
    main()
