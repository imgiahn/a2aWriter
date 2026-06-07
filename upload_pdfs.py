"""
upload_pdfs.py — 기존 발행 글에 원본 PDF 일괄 첨부

발행된 task 파일 중 has_pdf:true인 것을 모두 읽어
Tistory 해당 포스트에 PDF를 원본 파일명으로 업로드한다.
"""

import re
import json
import requests
from pathlib import Path

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")

# ─── 쿠키 추출 ──────────────────────────────────────

def get_cookies() -> dict:
    from playwright.sync_api import sync_playwright
    from agents.publisher_agent import auto_login

    cookies = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()
        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            auto_login(page, BLOG_URL)
        for c in ctx.cookies():
            if "tistory" in c.get("domain", ""):
                cookies[c["name"]] = c["value"]
        ctx.close()
    print(f"쿠키 {len(cookies)}개 추출")
    return cookies


# ─── manage/posts 전체 목록 ────────────────────────

def get_all_posts(cookies: dict) -> list:
    """manage/posts를 파싱해 [{id, title}] 반환."""
    from playwright.sync_api import sync_playwright
    from agents.publisher_agent import auto_login

    posts = []
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()

        for page_num in range(1, 20):
            page.goto(f"{BLOG_URL}/manage/posts?page={page_num}",
                      timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

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

            if not page.query_selector(f"a[href*='page={page_num + 1}']"):
                break

        ctx.close()
    print(f"포스트 {len(posts)}개 목록 수집")
    return posts


# ─── PDF 업로드 ────────────────────────────────────

def upload_pdf(post_id: int, pdf_path: str, filename: str, cookies: dict) -> bool:
    url = f"{BLOG_URL}/manage/post/attach.json"
    headers = {
        "Referer":          f"{BLOG_URL}/manage/newpost/",
        "Origin":           BLOG_URL,
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
    }
    pdf_bytes = Path(pdf_path).read_bytes()
    files = {"file": (filename, pdf_bytes, "application/pdf")}
    resp = requests.post(url, files=files, cookies=cookies, headers=headers, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        print(f"    ✅ {filename} ({data.get('size', 0):,} bytes)")
        return True
    print(f"    ❌ HTTP {resp.status_code}: {resp.text[:100]}")
    return False


# ─── task 파일 파싱 ────────────────────────────────

def parse_task(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("notice_name", "has_pdf", "pdf_path", "pdf_original_filename"):
            if line.startswith(f"{key}:"):
                result[key] = line.split(":", 1)[1].strip()
    return result


# ─── 제목 → 포스트 ID 매핑 ─────────────────────────

def find_post_id(posts: list, notice_name: str) -> int:
    """notice_name의 앞 10자로 포스트 목록에서 찾는다."""
    keyword = notice_name[:10].replace(" ", "")
    for p in posts:
        title_clean = p["title"].replace(" ", "")
        if keyword in title_clean:
            return p["id"]
    return 0


# ─── 메인 ──────────────────────────────────────────

def main():
    print("=" * 55)
    print("기존 발행 글 PDF 첨부 업로드")
    print("=" * 55)

    cookies = get_cookies()
    posts   = get_all_posts(cookies)

    # 포스트 목록 출력
    print("\nTistory 포스트 목록:")
    for p in posts:
        print(f"  [{p['id']}] {p['title'][:45]}")

    # task 파일 순회
    task_files = sorted(TASKS_DIR.glob("*.md"))
    targets = []
    for tf in task_files:
        if tf.stem.startswith("test_"):
            continue
        t = parse_task(tf)
        if t.get("has_pdf") != "true":
            continue
        if not t.get("pdf_path"):
            continue
        if not Path(t["pdf_path"]).exists():
            continue
        targets.append((tf.stem, t))

    print(f"\nPDF 있는 task {len(targets)}개")

    ok_count  = 0
    skip_count = 0
    for task_id, t in targets:
        notice_name = t.get("notice_name", "")
        pdf_path    = t.get("pdf_path", "")
        pdf_orig    = t.get("pdf_original_filename", "")

        # 파일명 결정: 저장된 원본명 우선, 없으면 notice_name 사용
        if pdf_orig:
            filename = pdf_orig
        else:
            # 파일명에 쓸 수 없는 문자 제거
            safe = re.sub(r'[\\/:"*?<>|]', '', notice_name)
            filename = f"{safe} 입주자모집공고.pdf"

        # 포스트 ID 찾기
        post_id = find_post_id(posts, notice_name)
        if not post_id:
            print(f"\n[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:30]}")
            skip_count += 1
            continue

        print(f"\n[{task_id}] 포스트 {post_id} | {notice_name[:30]}")
        print(f"  파일명: {filename}")
        if upload_pdf(post_id, pdf_path, filename, cookies):
            ok_count += 1
        else:
            skip_count += 1

    print(f"\n✅ 완료 — 성공 {ok_count}개 / 실패·스킵 {skip_count}개")


if __name__ == "__main__":
    main()
