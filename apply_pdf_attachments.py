"""
apply_pdf_attachments.py — 기존 발행 글에 PDF 첨부파일 소급 업로드

실행: python apply_pdf_attachments.py
"""

import re
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login

load_dotenv()

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")


def parse_task(path: Path) -> dict:
    result = {"task_id": path.stem}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("notice_name", "pdf_path", "pdf_original_filename"):
            if line.startswith(f"{key}:"):
                result[key] = line.split(":", 1)[1].strip()
    return result


def get_pdf_filename(task: dict) -> str:
    pdf_path = task.get("pdf_path", "")
    if not pdf_path:
        return ""
    filename = task.get("pdf_original_filename", "").strip()
    if not filename:
        meta = Path(pdf_path).parent / "filename.txt"
        if meta.exists():
            filename = meta.read_text(encoding="utf-8").strip()
    if not filename:
        filename = "공고문.pdf"
    return filename


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


def upload_pdf(post_id: int, pdf_path: str, pdf_filename: str, cookies: dict) -> bool:
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"  ⚠️  PDF 파일 없음: {pdf_path}")
        return False
    url = f"{BLOG_URL}/manage/post/attach.json"
    headers = {
        "Referer": f"{BLOG_URL}/manage/newpost/{post_id}?type=post",
        "Origin": BLOG_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    files = {"file": (pdf_filename, pdf_file.read_bytes(), "application/pdf")}
    try:
        r = requests.post(url, files=files, cookies=cookies, headers=headers, timeout=60)
        if r.status_code == 200:
            size = r.json().get("size", 0)
            print(f"  📎 PDF 업로드 완료: {pdf_filename} ({size:,} bytes)")
            return True
        print(f"  ⚠️  업로드 실패: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ⚠️  업로드 오류: {e}")
    return False


def get_post_list(page) -> list:
    posts = []
    for n in range(1, 5):
        page.goto(f"{BLOG_URL}/manage/posts?page={n}", timeout=20000, wait_until="networkidle")
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
        if not result or not page.query_selector(f"a[href*='page={n+1}']"):
            break
    return posts


def main():
    print("=" * 55)
    print("기존 발행 글 PDF 첨부파일 소급 업로드")
    print("=" * 55)

    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem == ".gitkeep":
            continue
        t = parse_task(tf)
        if not t.get("pdf_path"):
            continue
        pdf_file = Path(t["pdf_path"])
        if not pdf_file.exists():
            continue
        targets.append(t)

    print(f"PDF 있는 발행 글: {len(targets)}개\n")

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
        print(f"포스트 {len(posts)}개 확인\n")

        cookies = {c["name"]: c["value"] for c in ctx.cookies()
                   if "tistory" in c.get("domain", "")}
        ctx.close()

    ok = skip = 0
    for t in targets:
        task_id = t["task_id"]
        notice_name = t.get("notice_name", "")
        pdf_path = t.get("pdf_path", "")
        pdf_filename = get_pdf_filename(t)

        post_id = find_post_id(posts, notice_name, task_id)
        if not post_id:
            print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:35]}")
            skip += 1
            continue

        print(f"[{task_id}] 포스트 {post_id} — {pdf_filename}")
        if upload_pdf(post_id, pdf_path, pdf_filename, cookies):
            ok += 1
        else:
            skip += 1
        time.sleep(1)

    print(f"\n완료 — 성공 {ok}개 / 실패·스킵 {skip}개")


if __name__ == "__main__":
    main()
