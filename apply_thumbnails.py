"""
apply_thumbnails.py — 기존 발행 글에 대표이미지 소급 적용

발행 모달 .box_thumb input[type=file]에 파일 업로드 방식 (PUT thumbnail 필드 방식 X)
실행: python apply_thumbnails.py
"""

import os
import re
import sys
import time
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from tools.thumbnail_gen import generate_thumbnail

load_dotenv()

BLOG     = "llmenginehistory"
BLOG_URL = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")


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
    # 1) published HTML 제목으로 정확 매칭
    pub_title = get_published_title(task_id)
    if pub_title:
        clean_pub = re.sub(r"^[🏠\s]+", "", pub_title).strip()
        for p in posts:
            if re.sub(r"^[🏠\s]+", "", p["title"]).strip() == clean_pub:
                return p["id"]
        for p in posts:
            if clean_pub[:15] and re.sub(r"^[🏠\s]+", "", p["title"]).strip()[:15] == clean_pub[:15]:
                return p["id"]

    # 2) notice_name 키워드 폴백
    clean = re.sub(r"\s+", "", re.sub(r"[\(\[].+?[\)\]]", "", notice_name).strip())
    for length in [10, 8, 6, 5, 4]:
        kw = clean[:length]
        if not kw:
            continue
        for p in posts:
            if kw in re.sub(r"\s+", "", p["title"]):
                return p["id"]
    return 0


def set_representative_image(page, post_id: int, img_bytes: bytes) -> bool:
    """수정 페이지 열고 발행 모달에서 대표이미지 파일 업로드."""
    tmp_path = ""
    try:
        # 임시 파일 저장
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(img_bytes)
        tmp.close()
        tmp_path = tmp.name

        # 수정 페이지 이동
        page.goto(f"{BLOG_URL}/manage/post/{post_id}", timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 완료 버튼 → 발행 모달 열기
        page.locator("button:has-text('완료'), button:has-text('발행')").first.click()
        page.wait_for_timeout(2000)

        modal = page.locator(".ReactModal__Content.editor_layer")
        modal.wait_for(state="visible", timeout=8000)

        # 대표이미지 파일 업로드
        page.locator(".box_thumb input[type='file']").set_input_files(tmp_path)
        page.wait_for_timeout(1500)

        # 공개 확인
        page.locator("#open20").check(timeout=5000)
        page.wait_for_timeout(500)

        # 저장
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
    return posts


def main():
    print("=" * 55)
    print("기존 발행 글 대표이미지 소급 적용 (모달 파일 업로드)")
    print("=" * 55)

    # 오늘 새로 발행된 글은 이미 대표이미지 있으므로 스킵
    skip_ids = {"20260606_008"}

    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem in skip_ids or tf.stem.startswith("test_") or tf.stem == ".gitkeep":
            continue
        targets.append(parse_task(tf))

    print(f"대상 {len(targets)}개\n")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = ctx.new_page()

        # 로그인 확인
        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            print("자동 로그인 중...")
            auto_login(page, BLOG_URL)
        print("✅ 로그인 확인\n")

        # 포스트 목록 수집
        posts = get_post_list(page)
        print(f"포스트 {len(posts)}개:")
        for p in posts:
            print(f"  [{p['id']}] {p['title'][:50]}")
        print()

        ok = skip = 0
        for t in targets:
            task_id = t["task_id"]
            notice_name = t.get("notice_name", "")

            post_id = find_post_id(posts, notice_name, task_id)
            if not post_id:
                print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:35]}")
                skip += 1
                continue

            print(f"[{task_id}] 포스트 {post_id} — {notice_name[:35]}")
            print(f"  🎨 썸네일 생성 중...")
            img_bytes = generate_thumbnail(t)
            if not img_bytes:
                print(f"  ⚠️  썸네일 생성 실패")
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
