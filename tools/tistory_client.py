"""
tools/tistory_client.py — 티스토리 API 클라이언트

신규 발행·수정·삭제·로그인 등 모든 티스토리 연동을 이 모듈 하나에서 처리한다.
자세한 구현 노하우와 주의사항은 tools/tistory_client.md 참고.
"""

import re
import json
import time
from pathlib import Path
from typing import Optional


class TistoryClient:
    """티스토리 블로그 CRUD 클라이언트.

    사용 예:
        client = TistoryClient("https://myblog.tistory.com")
        client.login()
        post_id = client.publish_new("제목", "<p>내용</p>")
        client.update_post(post_id, "새 제목", "<p>새 내용</p>")
    """

    def __init__(self, blog_url: str, browser_data_dir: str = "browser_data"):
        self.blog_url      = blog_url.rstrip("/")
        self.browser_data  = Path(browser_data_dir)
        self._cookies: dict = {}

    # ──────────────────────────────────────────────
    # 로그인 / 세션
    # ──────────────────────────────────────────────

    def login(self) -> bool:
        """Playwright persistent context로 티스토리 로그인.

        browser_data/ 에 쿠키가 살아있으면 재사용.
        만료됐으면 kakao 자동 로그인 시도.
        """
        from playwright.sync_api import sync_playwright
        import os

        email    = os.getenv("KAKAO_EMAIL", "")
        password = os.getenv("KAKAO_PASSWORD", "")

        with sync_playwright() as pw:
            ctx = self._make_context(pw)
            page = ctx.new_page()
            page.goto(f"{self.blog_url}/manage", timeout=15000, wait_until="networkidle")

            if "/manage" in page.url and "login" not in page.url:
                self._cookies = self._extract_cookies(ctx)
                ctx.close()
                return True

            # 세션 만료 → kakao 자동 로그인
            try:
                page.goto("https://www.tistory.com/auth/login", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
                page.locator("a.link_kakao_id").click()
                page.wait_for_load_state("networkidle", timeout=15000)

                if "accounts.kakao.com" in page.url:
                    page.locator("input[name='loginId']").fill(email)
                    page.locator("input[name='password']").fill(password)
                    page.locator("button[type='submit']").click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_timeout(2000)

                page.goto(f"{self.blog_url}/manage", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
                ok = "/manage" in page.url and "login" not in page.url
            except Exception as e:
                print(f"  ❌ 로그인 오류: {e}")
                ok = False

            if ok:
                self._cookies = self._extract_cookies(ctx)
            ctx.close()
            return ok

    def ensure_login(self) -> bool:
        """쿠키 없으면 login() 자동 호출."""
        if not self._cookies:
            return self.login()
        return True

    # ──────────────────────────────────────────────
    # 신규 발행
    # ──────────────────────────────────────────────

    def publish_new(self, title: str, html: str) -> Optional[int]:
        """새 포스트를 공개 발행하고 포스트 ID를 반환한다.

        tinyMCE setContent은 빈 에디터(신규 글)에서만 정상 동작.
        발행 후 URL에서 post_id 추출 (반환값 없으면 None).
        """
        from playwright.sync_api import sync_playwright

        post_id = None
        with sync_playwright() as pw:
            ctx = self._make_context(pw)
            page = ctx.new_page()

            if not self._check_session(page):
                ctx.close()
                return None

            page.goto(f"{self.blog_url}/manage/newpost/", timeout=20000, wait_until="networkidle")
            page.wait_for_timeout(2000)

            # 제목
            title_loc = page.locator(
                "textarea[id*='title'], input[id*='title'], .editor-title-area textarea, "
                "#post-title-inp, .tf_subject"
            ).first
            title_loc.wait_for(timeout=10000)
            title_loc.fill(title)

            # 내용 (tinyMCE — 신규만 작동)
            page.wait_for_function(
                "typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null",
                timeout=10000,
            )
            page.wait_for_timeout(500)
            page.evaluate(
                "(html) => { const ed=tinyMCE.activeEditor; ed.focus(); ed.setContent(html); ed.save(); }",
                html,
            )

            # 완료 → 발행 모달
            page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
            page.wait_for_timeout(2000)

            modal = page.locator(".ReactModal__Content.editor_layer")
            modal.wait_for(state="visible", timeout=8000)
            page.locator("#open20").check(timeout=5000)
            page.wait_for_timeout(800)
            page.evaluate("document.getElementById('publish-btn').click()")
            page.wait_for_timeout(3000)

            # 발행 후 URL에서 post_id 추출
            m = re.search(r"/(\d+)$", page.url)
            if m:
                post_id = int(m.group(1))

            ctx.close()
        return post_id

    # ──────────────────────────────────────────────
    # 기존 포스트 수정
    # ──────────────────────────────────────────────

    def update_post(self, post_id: int, title: str, html: str) -> bool:
        """기존 포스트를 PUT API로 수정한다.

        tinyMCE setContent은 기존 포스트 편집 시 React 상태를 갱신하지 못해 무용지물.
        PUT /manage/post/{id}.json 직접 호출이 유일하게 확실한 방법.
        visibility:20 반드시 포함 (누락 시 비공개 전환됨).
        """
        import requests as _req

        if not self.ensure_login():
            return False

        slogan = re.sub(r"[^\w\s가-힣]", "", title)
        slogan = re.sub(r"\s+", "-", slogan.strip())

        payload = {
            "id":                    str(post_id),
            "title":                 title,
            "content":               html,
            "slogan":                slogan,
            "visibility":            20,      # 20=공개, 0=비공개 — 반드시 명시
            "category":              0,
            "tag":                   "",
            "acceptComment":         1,
            "published":             0,       # 0=기존 발행 시각 유지
            "password":              "",
            "uselessMarginForEntry": 1,
            "daumLike":              None,
            "cclCommercial":         0,
            "cclDerive":             0,
            "thumbnail":             None,
            "type":                  "post",
            "attachments":           [],
            "recaptchaValue":        "",
            "draftSequence":         None,
            "totalWritingTimeMs":    5000,
        }

        url = f"{self.blog_url}/manage/post/{post_id}.json"
        headers = {
            "Content-Type":    "application/json;charset=UTF-8",
            "Referer":         f"{self.blog_url}/manage/newpost/{post_id}?type=post",
            "Origin":          self.blog_url,
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        resp = _req.put(url, json=payload, cookies=self._cookies, headers=headers, timeout=20)
        return resp.status_code in (200, 201, 204)

    # ──────────────────────────────────────────────
    # 포스트 탐색
    # ──────────────────────────────────────────────

    def find_post_id(self, title_keyword: str) -> Optional[int]:
        """manage/posts 목록에서 제목 키워드로 포스트 ID를 찾는다.

        a.link_cont(제목) → closest li → a.btn_post(수정버튼) → href에서 ID 추출.
        """
        from playwright.sync_api import sync_playwright

        kw = title_keyword[:15]
        found_id = None

        with sync_playwright() as pw:
            ctx = self._make_context(pw)
            page = ctx.new_page()

            for page_num in range(1, 6):
                page.goto(f"{self.blog_url}/manage/posts?page={page_num}",
                          timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                result = page.evaluate(f"""() => {{
                    const kw = {json.dumps(kw)};
                    for (const lk of document.querySelectorAll('a.link_cont')) {{
                        const t = lk.getAttribute('title') || lk.textContent;
                        if (t.includes(kw)) {{
                            const container = lk.closest('li')
                                || lk.parentElement.parentElement.parentElement.parentElement;
                            const btn = container
                                ? container.querySelector('a.btn_post')
                                : null;
                            if (btn) {{
                                const m = btn.getAttribute('href').match(/\\/manage\\/post\\/(\\d+)/);
                                if (m) return parseInt(m[1]);
                            }}
                        }}
                    }}
                    return null;
                }}""")

                if result:
                    found_id = result
                    break

                if not page.query_selector(f"a[href*='page={page_num + 1}']"):
                    break

            ctx.close()
        return found_id

    def list_posts(self) -> list:
        """manage/posts의 포스트 목록을 [{id, title}] 형태로 반환한다."""
        from playwright.sync_api import sync_playwright

        posts = []
        with sync_playwright() as pw:
            ctx = self._make_context(pw)
            page = ctx.new_page()

            for page_num in range(1, 20):
                page.goto(f"{self.blog_url}/manage/posts?page={page_num}",
                          timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)

                result = page.evaluate("""() => {
                    const items = [];
                    document.querySelectorAll('a.link_cont').forEach(lk => {
                        const container = lk.closest('li')
                            || lk.parentElement.parentElement.parentElement.parentElement;
                        const btn = container
                            ? container.querySelector('a.btn_post') : null;
                        if (!btn) return;
                        const m = btn.getAttribute('href').match(/\\/manage\\/post\\/(\\d+)/);
                        if (m) items.push({
                            id: parseInt(m[1]),
                            title: lk.getAttribute('title') || lk.textContent.trim()
                        });
                    });
                    return items;
                }""")
                posts.extend(result)

                if not page.query_selector(f"a[href*='page={page_num + 1}']"):
                    break

            ctx.close()
        return posts

    # ──────────────────────────────────────────────
    # 파일 업로드
    # ──────────────────────────────────────────────

    def upload_file(self, file_path: str, original_filename: str) -> Optional[dict]:
        """PDF 등 파일을 티스토리에 업로드하고 첨부파일 정보를 반환한다.

        엔드포인트: POST /manage/post/attach.json (multipart/form-data)
        반환값: {"name": str, "url": str, "key": str, "filename": str, "size": int}
        """
        import requests as _req
        from pathlib import Path as _Path

        if not self.ensure_login():
            return None

        file_bytes = _Path(file_path).read_bytes()
        url     = f"{self.blog_url}/manage/post/attach.json"
        headers = {
            "Referer":          f"{self.blog_url}/manage/newpost/",
            "Origin":           self.blog_url,
            "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        files = {"file": (original_filename, file_bytes, "application/pdf")}

        resp = _req.post(url, files=files, cookies=self._cookies, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        return None

    # ──────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────

    def _make_context(self, pw):
        self.browser_data.mkdir(exist_ok=True)
        return pw.chromium.launch_persistent_context(
            user_data_dir=str(self.browser_data),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )

    def _check_session(self, page) -> bool:
        page.goto(f"{self.blog_url}/manage", timeout=15000, wait_until="networkidle")
        return "/manage" in page.url and "login" not in page.url

    def _extract_cookies(self, ctx) -> dict:
        return {
            c["name"]: c["value"]
            for c in ctx.cookies()
            if "tistory" in c.get("domain", "")
        }
