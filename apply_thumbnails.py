"""
apply_thumbnails.py — 기존 발행 글에 대표이미지 소급 적용

우선순위:
1. data/thumbnails/{task_id}.png 로컬 캐시 사용
2. Tistory 글 본문 <figure> 의 CDN URL에서 다운로드
3. 둘 다 없으면 AI로 새로 생성

실행: python apply_thumbnails.py
"""

import os
import re
import time
import tempfile
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from tools.thumbnail_gen import generate_thumbnail

load_dotenv()

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")
THUMB_DIR = Path(f"data/{BLOG}/thumbnails")


def parse_task(path: Path) -> dict:
    result = {"task_id": path.stem}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("notice_name", "region", "housing_category", "supply_type"):
            if line.startswith(f"{key}:"):
                result[key] = line.split(":", 1)[1].strip()
    return result


def get_published_title(task_id: str) -> str:
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            m = re.match(r"<!-- TITLE: (.+?) -->", p.read_text(encoding="utf-8"))
            return m.group(1).strip() if m else ""
    return ""


def find_post_id(posts: list, notice_name: str, task_id: str) -> int:
    pub_title = get_published_title(task_id)
    if pub_title:
        clean_pub = re.sub(r"^[🏠\s]+", "", pub_title).strip()
        for p in posts:
            if re.sub(r"^[🏠\s]+", "", p["title"]).strip() == clean_pub:
                return p["id"]
        for p in posts:
            if clean_pub[:15] and re.sub(r"^[🏠\s]+", "", p["title"]).strip()[:15] == clean_pub[:15]:
                return p["id"]
    clean = re.sub(r"\s+", "", re.sub(r"[\(\[].+?[\)\]]", "", notice_name).strip())
    for length in [10, 8, 6, 5, 4]:
        kw = clean[:length]
        if not kw:
            continue
        for p in posts:
            if kw in re.sub(r"\s+", "", p["title"]):
                return p["id"]
    return 0


def get_img_bytes(task_id: str, task: dict, post_id: int) -> bytes:
    """썸네일 bytes 반환. 캐시 → CDN → AI 생성 순."""
    # 1) 로컬 캐시
    cache = THUMB_DIR / f"{task_id}.png"
    if cache.exists():
        print(f"  💾 캐시 사용: {cache.name}")
        return cache.read_bytes()

    # 2) Tistory 글 본문 <figure> CDN URL에서 다운로드
    try:
        r = requests.get(f"{BLOG_URL}/{post_id}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        m = re.search(r'<figure[^>]*>\s*<img[^>]+src=["\']([^"\']+)["\']', r.text)
        if m:
            cdn_url = m.group(1)
            img_r = requests.get(cdn_url, timeout=20)
            if img_r.status_code == 200:
                img_bytes = img_r.content
                THUMB_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(img_bytes)
                print(f"  🌐 CDN에서 다운로드 후 캐시 저장")
                return img_bytes
    except Exception as e:
        print(f"  ⚠️  CDN 다운로드 실패: {e}")

    # 3) AI 새로 생성
    print(f"  🎨 AI 썸네일 생성 중...")
    img_bytes = generate_thumbnail(task)
    if img_bytes:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(img_bytes)
        print(f"  💾 생성 후 캐시 저장")
    return img_bytes


def set_representative_image(page, post_id: int, img_bytes: bytes) -> bool:
    """수정 페이지 열고 발행 모달에서 대표이미지 파일 업로드."""
    tmp_path = ""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(img_bytes)
        tmp.close()
        tmp_path = tmp.name

        page.goto(f"{BLOG_URL}/manage/post/{post_id}", timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.locator("button:has-text('완료'), button:has-text('발행')").first.click()
        page.wait_for_timeout(2000)
        page.locator(".ReactModal__Content.editor_layer").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(1000)

        # 이미 썸네일 있으면 삭제 버튼 클릭 → file input 복원
        delete_btn = page.locator(".box_thumb .ico_delete")
        if delete_btn.is_visible():
            delete_btn.click()
            page.wait_for_timeout(1000)

        page.locator(".box_thumb input[type='file']").set_input_files(tmp_path)
        page.wait_for_timeout(1500)
        page.locator("#open20").check(timeout=5000)
        page.wait_for_timeout(500)
        page.evaluate("document.getElementById('publish-btn').click()")
        page.wait_for_timeout(3000)
        return True
    except Exception as e:
        print(f"  ⚠️  실패: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def get_post_list(page) -> list:
    posts = []
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
                const li = lk.closest('li');
                const btn = li ? li.querySelector('a.btn_post') : null;
                if (!btn) return;
                const m = btn.getAttribute('href').match(/\\/manage\\/post\\/(\\d+)/);
                if (m) items.push({id: parseInt(m[1]),
                    title: (lk.getAttribute('title')||lk.textContent).trim()});
            });
            return items;
        }""")
        posts.extend(result)
        if not result or not page.query_selector(f"a[href*='page={page_num+1}']"):
            break
    return posts


def main():
    print("=" * 55)
    print("기존 발행 글 대표이미지 소급 적용")
    print("=" * 55)

    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem == ".gitkeep":
            continue
        targets.append(parse_task(tf))

    print(f"대상 {len(targets)}개\n")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = ctx.new_page()

        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            auto_login(page, BLOG_URL)
        print("✅ 로그인 확인\n")

        posts = get_post_list(page)
        print(f"포스트 {len(posts)}개:")
        for p in posts:
            print(f"  [{p['id']}] {p['title'][:50]}")
        print()

        ok = skip = 0
        for t in targets:
            task_id     = t["task_id"]
            notice_name = t.get("notice_name", "")
            post_id     = find_post_id(posts, notice_name, task_id)

            if not post_id:
                print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:35]}")
                skip += 1
                continue

            print(f"[{task_id}] 포스트 {post_id} — {notice_name[:35]}")
            img_bytes = get_img_bytes(task_id, t, post_id)
            if not img_bytes:
                print(f"  ⚠️  이미지 획득 실패")
                skip += 1
                continue

            if set_representative_image(page, post_id, img_bytes):
                print(f"  ✅ 대표이미지 설정 완료")
                ok += 1
            else:
                skip += 1
            time.sleep(2)

        ctx.close()

    print(f"\n완료 — 성공 {ok}개 / 실패·스킵 {skip}개")


if __name__ == "__main__":
    main()
