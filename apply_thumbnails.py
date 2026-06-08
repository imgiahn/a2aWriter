"""
apply_thumbnails.py — 기존 발행 글에 대표이미지 소급 적용

1단계: 모달 파일업로드 → 대표이미지 설정 (이것만 작동)
2단계: PUT → <figure> 본문 삽입 (모달 재발행이 본문을 덮으므로 모달 후에 PUT)

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
from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

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


def get_local_html(task_id: str) -> str:
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            return re.sub(r"<!-- TITLE: .+? -->\n?", "",
                          p.read_text(encoding="utf-8"), flags=re.DOTALL)
    return ""


def get_published_title(task_id: str) -> str:
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            m = re.match(r"<!-- TITLE: (.+?) -->", p.read_text(encoding="utf-8"))
            return m.group(1).strip() if m else ""
    return ""


def update_local_html_with_figure(task_id: str, figure_html: str):
    """로컬 HTML 앞에 <figure> 삽입 (apply_pdf_attachments 연계용)."""
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            content = p.read_text(encoding="utf-8")
            title_m = re.match(r"(<!-- TITLE: .+? -->\n?)", content)
            if title_m:
                rest = content[len(title_m.group(0)):]
                rest = re.sub(r"^<figure[^>]*>.*?</figure>\n?", "", rest.lstrip(), flags=re.DOTALL)
                p.write_text(title_m.group(0) + figure_html + rest, encoding="utf-8")
            return


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


def get_img_bytes(task_id: str, task: dict) -> bytes:
    cache = THUMB_DIR / f"{task_id}.png"
    if cache.exists():
        print(f"  💾 캐시 사용: {cache.name}")
        return cache.read_bytes()
    print(f"  🎨 AI 썸네일 생성 중...")
    img_bytes = generate_thumbnail(task)
    if img_bytes:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(img_bytes)
        print(f"  💾 생성 후 캐시 저장")
    return img_bytes


def set_thumbnail_via_modal(page, post_id: int, img_bytes: bytes) -> bool:
    """모달 파일업로드로 대표이미지 설정 (에디터 재발행 발생)."""
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
        print(f"  ⚠️  모달 실패: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def put_figure_to_body(post_id: int, post_title: str, task_id: str,
                       cdn_url: str, cookies: dict) -> bool:
    """모달 재발행 후 <figure> 본문 복구 (PUT)."""
    body = get_local_html(task_id)
    if not body:
        return False

    body = re.sub(r"^<figure[^>]*>.*?</figure>\n?", "", body.lstrip(), flags=re.DOTALL)
    figure_html = (
        f'<figure style="margin:0 0 16px 0; text-align:center;">'
        f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
        f'alt="썸네일">'
        f'</figure>\n'
    )
    new_body = figure_html + body

    slogan = re.sub(r"\s+", "-", re.sub(r"[^\w\s가-힣]", "", post_title).strip())
    payload = {
        "id": str(post_id), "title": post_title, "content": new_body,
        "slogan": slogan, "visibility": 20, "category": 0,
        "tag": "", "acceptComment": 1, "published": 0,
        "password": "", "uselessMarginForEntry": 1,
        "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
        "type": "post", "attachments": [],
        "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
    }
    hdrs = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"{BLOG_URL}/manage/newpost/{post_id}?type=post",
        "Origin": BLOG_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    r = requests.put(f"{BLOG_URL}/manage/post/{post_id}.json",
                     json=payload, cookies=cookies, headers=hdrs, timeout=20)
    if r.status_code in (200, 201, 204):
        update_local_html_with_figure(task_id, figure_html)
        return True
    print(f"  ⚠️  PUT 실패: HTTP {r.status_code}")
    return False


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

        cookies = {c["name"]: c["value"] for c in ctx.cookies()
                   if "tistory" in c.get("domain", "")}

        ok = skip = 0
        for t in targets:
            task_id     = t["task_id"]
            notice_name = t.get("notice_name", "")
            post_id     = find_post_id(posts, notice_name, task_id)

            if not post_id:
                print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:35]}")
                skip += 1
                continue

            post_title = next((p["title"] for p in posts if p["id"] == post_id), "")
            print(f"[{task_id}] 포스트 {post_id} — {notice_name[:35]}")

            img_bytes = get_img_bytes(task_id, t)
            if not img_bytes:
                print(f"  ⚠️  이미지 획득 실패")
                skip += 1
                continue

            # 1단계: 모달로 대표이미지 설정
            modal_ok = set_thumbnail_via_modal(page, post_id, img_bytes)
            if not modal_ok:
                skip += 1
                time.sleep(2)
                continue
            print(f"  ✅ 대표이미지 설정 완료")

            # 2단계: PUT으로 <figure> 본문 복구 (모달 재발행이 덮은 후)
            cdn_url = upload_thumbnail_to_tistory(img_bytes, BLOG_URL, cookies)
            if cdn_url:
                if put_figure_to_body(post_id, post_title, task_id, cdn_url, cookies):
                    print(f"  ✅ <figure> 본문 복구 완료")
                else:
                    print(f"  ⚠️  <figure> PUT 실패 (대표이미지는 설정됨)")
            else:
                print(f"  ⚠️  CDN 업로드 실패 (대표이미지는 설정됨)")

            ok += 1
            time.sleep(2)

        ctx.close()

    print(f"\n완료 — 성공 {ok}개 / 실패·스킵 {skip}개")


if __name__ == "__main__":
    main()
