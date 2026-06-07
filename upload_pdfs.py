"""
upload_pdfs.py — 기존 발행 글에 원본 PDF 일괄 첨부

발행된 task 파일 중 has_pdf:true인 것을 모두 읽어
Tistory 해당 포스트에 PDF를 원본 파일명으로 업로드한다.
단일 Playwright 세션으로 쿠키 추출 + 포스트 목록 수집 + PDF 업로드 처리.
"""

import re
import requests
from pathlib import Path

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")


def parse_task(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("notice_name", "has_pdf", "pdf_path", "pdf_original_filename"):
            if line.startswith(f"{key}:"):
                result[key] = line.split(":", 1)[1].strip()
    return result


def find_post_id(posts: list, notice_name: str) -> int:
    # 괄호/대괄호 내용 제거 후 다양한 길이로 시도
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


def upload_and_attach(post_id: int, pdf_path: str, filename: str,
                      post_title: str, cookies: dict) -> bool:
    """PDF 업로드 → CDN URL 획득 → 포스트 내용 앞에 다운로드 링크 삽입 → PUT."""
    # 1. 파일 업로드
    attach_url = f"{BLOG_URL}/manage/post/attach.json"
    hdrs = {
        "Referer":          f"{BLOG_URL}/manage/newpost/",
        "Origin":           BLOG_URL,
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
    }
    pdf_bytes = Path(pdf_path).read_bytes()
    resp = requests.post(attach_url,
                         files={"file": (filename, pdf_bytes, "application/pdf")},
                         cookies=cookies, headers=hdrs, timeout=60)
    if resp.status_code != 200:
        print(f"    ❌ 업로드 실패 HTTP {resp.status_code}")
        return False

    data     = resp.json()
    cdn_url  = data.get("url", "")
    size_kb  = data.get("size", 0) // 1024
    print(f"    📎 업로드 완료: {filename} ({size_kb:,} KB)")
    print(f"    🔗 CDN URL: {cdn_url[:80]}...")

    # 2. 다운로드 링크 HTML 생성
    link_html = (
        f'<div style="margin:12px 0;padding:12px 16px;background:#f8f9fa;'
        f'border-left:4px solid #0066cc;border-radius:4px;">'
        f'📄 원문 공고 PDF: '
        f'<a href="{cdn_url}" target="_blank" rel="noopener">{filename}</a>'
        f'&nbsp;<span style="color:#888;font-size:0.85em;">({size_kb:,} KB)</span>'
        f'</div>\n'
    )

    # 3. 현재 포스트 내용 가져오기 (preview HTML 사용)
    task_id   = None
    post_html = None
    preview_dir = Path(f"articles/{BLOG}/preview")
    draft_dir   = Path(f"articles/{BLOG}/draft")
    pub_dir     = Path(f"articles/{BLOG}/published")

    # notice_name 키워드로 대응 파일 탐색
    title_kw = re.sub(r"\s+", "", post_title[:8])
    for d in [preview_dir, draft_dir, pub_dir]:
        for f in sorted(d.glob("*.html"), reverse=True):
            content = f.read_text(encoding="utf-8")
            if title_kw in re.sub(r"\s+", "", content[:500]):
                post_html = re.sub(r"<!-- TITLE: .+? -->\n?", "", content, flags=re.DOTALL)
                task_id   = f.stem
                break
        if post_html:
            break

    if not post_html:
        print(f"    ⚠️  포스트 HTML 못 찾음, 링크만 추가")
        post_html = ""

    new_content = link_html + post_html

    # 4. PUT으로 포스트 업데이트
    slogan = re.sub(r"[^\w\s가-힣]", "", post_title)
    slogan = re.sub(r"\s+", "-", slogan.strip())
    payload = {
        "id":                    str(post_id),
        "title":                 post_title,
        "content":               new_content,
        "slogan":                slogan,
        "visibility":            20,
        "category":              0,
        "tag":                   "",
        "acceptComment":         1,
        "published":             0,
        "password":              "",
        "uselessMarginForEntry": 1,
        "daumLike":              None,
        "cclCommercial":         0,
        "cclDerive":             0,
        "thumbnail":             None,
        "type":                  "post",
        "attachments":           [{"name": filename, "url": cdn_url,
                                   "key": data.get("key", ""), "size": data.get("size", 0)}],
        "recaptchaValue":        "",
        "draftSequence":         None,
        "totalWritingTimeMs":    5000,
    }
    put_hdrs = {
        "Content-Type":    "application/json;charset=UTF-8",
        "Referer":         f"{BLOG_URL}/manage/newpost/{post_id}?type=post",
        "Origin":          BLOG_URL,
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
    }
    put_resp = requests.put(f"{BLOG_URL}/manage/post/{post_id}.json",
                            json=payload, cookies=cookies, headers=put_hdrs, timeout=20)
    print(f"    PUT → {put_resp.status_code}")
    return put_resp.status_code in (200, 201, 204)


def main():
    from playwright.sync_api import sync_playwright
    from agents.publisher_agent import auto_login

    print("=" * 55)
    print("기존 발행 글 PDF 첨부 업로드")
    print("=" * 55)

    # PDF 있는 task 미리 수집
    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem.startswith("test_"):
            continue
        t = parse_task(tf)
        if t.get("has_pdf") != "true" or not t.get("pdf_path"):
            continue
        if not Path(t["pdf_path"]).exists():
            print(f"  ⚠️  PDF 없음 (서버에만 있을 수 있음): {t['pdf_path']}")
            continue
        targets.append((tf.stem, t))

    print(f"PDF 있는 task {len(targets)}개\n")

    # 단일 Playwright 세션으로 처리
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = ctx.new_page()

        # 로그인
        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            print("세션 만료 → 자동 로그인...")
            auto_login(page, BLOG_URL)
        print("✅ 로그인 확인\n")

        # 포스트 목록 수집
        posts = []
        for page_num in range(1, 10):
            page.goto(f"{BLOG_URL}/manage/posts?page={page_num}",
                      timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            # 포스트 목록 렌더링 대기
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

        print(f"포스트 {len(posts)}개 목록 수집:")
        for p in posts:
            print(f"  [{p['id']}] {p['title'][:50]}")

        # 쿠키 추출
        cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain", "")}
        ctx.close()

    print(f"\n쿠키 {len(cookies)}개 | 업로드 시작\n" + "=" * 55)

    ok, skip = 0, 0
    for task_id, t in targets:
        notice_name = t.get("notice_name", "")
        pdf_path    = t.get("pdf_path", "")
        pdf_orig    = t.get("pdf_original_filename", "")

        safe_name = re.sub(r'[/\\:*?<>|"]+', '', notice_name)
        suffix = "" if any(k in notice_name for k in ("공고", "모집", "안내")) else " 입주자모집공고"
        filename = pdf_orig if pdf_orig else f"{safe_name}{suffix}.pdf"

        post_id = find_post_id(posts, notice_name)
        if not post_id:
            print(f"[{task_id}] ⚠️  포스트 못 찾음: {notice_name[:30]}")
            skip += 1
            continue

        post_title = next((p["title"] for p in posts if p["id"] == post_id), notice_name)
        print(f"[{task_id}] 포스트 {post_id} — {notice_name[:30]}")
        print(f"  파일명: {filename}")
        if upload_and_attach(post_id, pdf_path, filename, post_title, cookies):
            ok += 1
        else:
            skip += 1

    print(f"\n✅ 완료 — 성공 {ok}개 / 실패·스킵 {skip}개")


if __name__ == "__main__":
    main()
