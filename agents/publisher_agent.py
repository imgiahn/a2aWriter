"""
Publisher Agent

역할: 초안을 티스토리에 발행
입력: articles/{blog}/draft/{task_id}.html + blogs/{blog}/tasks/writing/{task_id}.md
출력: 티스토리 공개 발행

실행: python agents/publisher_agent.py --blog mbtireallove
      SERVER_MODE=1 python agents/publisher_agent.py --blog mbtireallove
"""

import os
import re
import sys
import time
import shutil
import argparse
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext

load_dotenv()

BROWSER_DATA_DIR = Path("browser_data")


def get_paths(blog: str) -> dict:
    base = Path(f"blogs/{blog}")
    return {
        "tasks_writing":   base / "tasks/writing",
        "tasks_published": base / "tasks/published",
        "tasks_failed":    base / "tasks/failed",
        "articles_draft":  Path(f"articles/{blog}/draft"),
        "articles_pub":    Path(f"articles/{blog}/published"),
        "articles_summary": Path(f"articles/{blog}/summary"),
    }


def load_config(blog: str) -> dict:
    config_path = Path(f"blogs/{blog}/config.md")
    config = {}
    if config_path.exists():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            if ": " in line and not line.startswith("#") and not line.startswith("---"):
                k, v = line.split(": ", 1)
                config[k.strip()] = v.strip()
    return config


def get_next_task(tasks_writing: Path) -> Optional[Path]:
    tasks = sorted(tasks_writing.glob("*.md"))
    return tasks[0] if tasks else None


def read_draft(task_id: str, articles_draft: Path) -> tuple:
    """(title, html, tags) 반환."""
    draft   = articles_draft / f"{task_id}.html"
    content = draft.read_text(encoding="utf-8")
    m = re.match(r"<!-- TITLE: (.+?) -->\n?", content)
    title = m.group(1).strip() if m else task_id
    rest  = re.sub(r"<!-- TITLE: .+? -->\n?", "", content, count=1)
    tags_m = re.search(r"<!-- TAGS: (.+?) -->", rest)
    tags   = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else []
    html   = re.sub(r"<!-- TAGS: .+? -->\n?", "", rest, count=1)
    return title, html, tags


# 발행 전 필수 검증 키워드 (제목에 2개 이상)
_TITLE_KEYWORDS = ["분양가", "청약일정", "안전마진", "전매제한", "거주의무",
                   "무순위", "특별공급", "신혼희망타운", "공공분양"]


def _validate_pre_publish(title: str, html: str, tags: list, category_id: int) -> list:
    """발행 전 필수 조건 검증. 실패 사유 목록 반환 (빈 리스트 = 통과)."""
    issues = []
    kw_count = sum(1 for k in _TITLE_KEYWORDS if k in title)
    if kw_count < 2:
        issues.append(f"제목 키워드 부족 ({kw_count}개/2개 필요): {title}")
    if not category_id:
        issues.append("카테고리 미설정 (카테고리 없음 발행 금지)")
    if len(tags) < 8:
        issues.append(f"태그 부족 ({len(tags)}개/8개 필요)")
    if "결론 먼저 보기" not in html:
        issues.append("'결론 먼저 보기' 섹션 없음")
    if "안전마진" not in html:
        issues.append("안전마진 섹션 없음")
    if "청약 일정" not in html:
        issues.append("청약 일정 섹션 없음")
    text_only = re.sub(r"<[^>]+>", "", html)
    if len(text_only) < 1500:
        issues.append(f"본문 너무 짧음 ({len(text_only)}자/1500자 필요)")
    return issues


def is_logged_in(page: Page, blog_url: str) -> bool:
    page.goto(f"{blog_url}/manage", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)
    return "/manage" in page.url and "login" not in page.url


def auto_login(page: Page, blog_url: str) -> bool:
    email    = os.getenv("KAKAO_EMAIL", "")
    password = os.getenv("KAKAO_PASSWORD", "")
    if not email or not password:
        print("  ⚠️  KAKAO_EMAIL / KAKAO_PASSWORD 환경변수가 없습니다.")
        return False

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

        page.goto(f"{blog_url}/manage", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        success = "/manage" in page.url and "login" not in page.url
        print(f"  {'✅ 자동 로그인 성공' if success else '❌ 쿠키 만료 → 재인증 필요'}")
        return success

    except Exception as e:
        print(f"  ❌ 자동 로그인 오류: {e}")
        return False


def save_summary(task_id: str, html: str, articles_summary: Path):
    articles_summary.mkdir(parents=True, exist_ok=True)
    text = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    preview = text[:500] + ("..." if len(text) > 500 else "")
    (articles_summary / f"{task_id}.txt").write_text(preview, encoding="utf-8")


def reauth(pw, blog_url: str) -> Optional[BrowserContext]:
    email    = os.getenv("KAKAO_EMAIL", "")
    password = os.getenv("KAKAO_PASSWORD", "")

    if BROWSER_DATA_DIR.exists():
        shutil.rmtree(BROWSER_DATA_DIR)
    BROWSER_DATA_DIR.mkdir()

    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        headless=True,
    )
    page = context.new_page()

    try:
        page.goto("https://www.tistory.com/auth/login", timeout=15000)
        page.wait_for_load_state("networkidle")
        page.locator("a.link_kakao_id").click()
        page.wait_for_load_state("networkidle")

        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(email)
            page.locator("input[name='password']").fill(password)
            page.locator("button[type='submit']").click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

        if "tistory.com" in page.url and "kakao" not in page.url:
            print("  ✅ 재인증 성공 (폰 승인 불필요)")
        else:
            print("  📱 카카오 앱에서 [로그인 승인]을 눌러주세요. (최대 3분 대기)")
            deadline = time.time() + 180
            approved = False
            while time.time() < deadline:
                if "tistory.com" in page.url and "kakao" not in page.url:
                    approved = True
                    break
                for btn_text in ["확인", "계속", "동의", "허용"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.is_visible():
                        btn.click()
                        break
                page.wait_for_timeout(3000)

            if not approved:
                print("  ❌ 재인증 시간 초과")
                context.close()
                return None

        page.goto(f"{blog_url}/manage", timeout=15000)
        page.wait_for_load_state("networkidle")
        if "/manage" in page.url and "login" not in page.url:
            print("  ✅ 재인증 완료 — 쿠키 저장됨")
            return context

        context.close()
        return None

    except Exception as e:
        print(f"  ❌ 재인증 오류: {e}")
        context.close()
        return None


CATEGORY_LH          = 1311445   # LH 청약 플러스 (부모)
CATEGORY_APPLYHOME   = 1311446   # 청약 Home (부모)

# ── 서브카테고리 ID (티스토리 관리자에서 생성 후 ID 입력 필요) ──────────────────
# 티스토리 관리자 → 카테고리 → 하위 카테고리 생성 → 글쓰기 에디터에서 ID 확인
# python get_category_ids.py 로 자동 조회 가능 (세션 갱신 후)
CATEGORY_APPLYHOME_SALE      = 0   # 청약 Home / 민영분양
CATEGORY_APPLYHOME_UNSOLD    = 0   # 청약 Home / 무순위·줍줍
CATEGORY_LH_PUBLIC           = 0   # LH 청약 플러스 / 공공분양
CATEGORY_LH_NEWLYWED         = 0   # LH 청약 플러스 / 신혼희망타운
CATEGORY_ANALYSIS_MARGIN     = 0   # 분석 / 안전마진
CATEGORY_ANALYSIS_SCHEDULE   = 0   # 분석 / 청약 일정


def get_category_id(supply_type: str, detail_url: str, housing_source: str) -> int:
    """공급유형·소스 → 티스토리 서브카테고리 ID 반환. 0이면 미설정(발행 차단)."""
    is_applyhome = "applyhome.co.kr" in (detail_url or "")
    is_lh        = not is_applyhome

    # 무순위/줍줍/잔여세대 → 무순위·줍줍
    if any(k in supply_type for k in ["무순위", "사후", "잔여", "줍줍"]):
        return CATEGORY_APPLYHOME_UNSOLD

    # 신혼희망타운
    if "신혼희망타운" in supply_type:
        return CATEGORY_LH_NEWLYWED if is_lh else CATEGORY_APPLYHOME_SALE

    # LH 공공분양
    if is_lh and any(k in supply_type for k in ["공공분양", "분양주택", "분양"]):
        return CATEGORY_LH_PUBLIC

    # 청약홈 민영분양
    if is_applyhome:
        return CATEGORY_APPLYHOME_SALE

    # LH 기타 → 공공분양으로
    if is_lh:
        return CATEGORY_LH_PUBLIC

    return 0


def post_article(page: Page, blog_url: str, title: str, content: str,
                 thumbnail_file: str = "", category_id: int = 0, tags: list = None):
    page.goto(f"{blog_url}/manage/newpost/", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)

    title_loc = page.locator(
        "textarea[id*='title'], input[id*='title'], .editor-title-area textarea, "
        "#post-title-inp, .tf_subject"
    ).first
    title_loc.wait_for(timeout=10000)
    title_loc.fill(title)
    page.wait_for_timeout(500)

    page.wait_for_function(
        "typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null",
        timeout=10000,
    )
    page.wait_for_timeout(500)

    injected = page.evaluate(
        """(html) => {
            try {
                const ed = tinyMCE.activeEditor;
                if (!ed) return false;
                ed.focus(); ed.setContent(html); ed.save();
                return true;
            } catch(e) { return false; }
        }""",
        content,
    )

    if not injected:
        page.locator("button:has-text('기본모드'), .button_mode").first.click()
        page.wait_for_timeout(500)
        page.locator("li:has-text('HTML'), button:has-text('HTML')").first.click()
        page.wait_for_timeout(1000)
        done = page.evaluate(
            """(html) => {
                const cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) { cm.CodeMirror.setValue(html); return true; }
                return false;
            }""",
            content,
        )
        if not done:
            ta = page.locator("textarea.html-editor, #content, textarea[name='content']").first
            if ta.is_visible(timeout=3000):
                ta.fill(content)
            else:
                raise RuntimeError("에디터 내용 삽입 실패")

    page.wait_for_timeout(500)
    page.locator("button:has-text('완료'), button:has-text('발행'), .btn_publish").first.click()
    page.wait_for_timeout(2000)

    modal = page.locator('.ReactModal__Content.editor_layer')
    modal.wait_for(state='visible', timeout=8000)
    page.locator('#open20').check(timeout=5000)
    page.wait_for_timeout(800)

    # 카테고리 설정 — JS 직접 클릭 (Playwright actionability 체크 우회)
    if category_id:
        try:
            page.evaluate("document.getElementById('category-btn').click()")
            page.wait_for_timeout(1000)
            page.locator(f"[data-id='{category_id}']").first.click(timeout=5000, force=True)
            page.wait_for_timeout(500)
            print(f"  🗂️  카테고리 설정 완료 (id={category_id})")
        except Exception as e:
            print(f"  ⚠️  카테고리 설정 실패: {e}")

    # 대표이미지 설정 — .box_thumb input[type=file]에 파일 직접 업로드
    if thumbnail_file:
        try:
            file_input = page.locator(".box_thumb input[type='file']")
            file_input.set_input_files(thumbnail_file)
            page.wait_for_timeout(1500)
            print(f"  🖼️  대표이미지 업로드 완료")
        except Exception as e:
            print(f"  ⚠️  대표이미지 업로드 실패: {e}")

    page.evaluate("document.getElementById('publish-btn').click()")
    page.wait_for_timeout(3000)

    # 발행 후 URL에서 post_id 추출
    # Tistory 에디터는 발행 후 URL이 여러 패턴으로 나타남:
    #   /manage/newpost/123?type=post  → path에 숫자
    #   /manage/newpost/?postId=123    → 쿼리파라미터에 숫자
    def _extract_post_id(url: str):
        url_clean = url.split("?")[0]
        m = re.search(r"/(\d+)$", url_clean)
        if m:
            return int(m.group(1))
        m = re.search(r"[?&]postId=(\d+)", url)
        if m:
            return int(m.group(1))
        return None

    url = page.url
    print(f"  🔍 발행 후 URL: {url}")
    post_id = _extract_post_id(url)
    if not post_id:
        page.wait_for_timeout(2000)
        url = page.url
        print(f"  🔍 발행 후 URL(재시도): {url}")
        post_id = _extract_post_id(url)
    return post_id


def _generate_and_set_thumbnail(blog_url: str, context, task_path: Path, post_id: int, title: str):
    """썸네일 이미지 생성 → 티스토리 업로드 → 포스트 내용 첫 번째 이미지로 삽입.

    Tistory는 content 첫 번째 <img>를 og:image/썸네일로 자동 사용.
    thumbnail 필드에도 동시 설정.
    """
    import requests as _req, re as _re
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

    # task 파일에서 필드 읽기
    task = {}
    task_id = task_path.stem
    if task_path.exists():
        for line in task_path.read_text(encoding="utf-8").splitlines():
            for key in ("notice_name", "region", "housing_category", "supply_type"):
                if line.startswith(f"{key}:"):
                    task[key] = line.split(":", 1)[1].strip()

    # 현재 포스트 HTML 읽기 (published > draft 순서로 탐색)
    blog = task_path.parts[-4]  # blogs/{blog}/tasks/published
    post_html = ""
    for folder in ("published", "draft", "preview"):
        html_path = Path(f"articles/{blog}/{folder}/{task_id}.html")
        if html_path.exists():
            post_html = _re.sub(r"<!-- TITLE: .+? -->\n?", "",
                                html_path.read_text(encoding="utf-8"), flags=_re.DOTALL)
            break

    print(f"  🎨 썸네일 생성 중...")
    img_bytes = generate_thumbnail(task)
    if not img_bytes:
        return

    cookies = {c["name"]: c["value"] for c in context.cookies() if "tistory" in c.get("domain", "")}
    cdn_url = upload_thumbnail_to_tistory(img_bytes, blog_url, cookies)
    if not cdn_url:
        return

    # 이미지를 포스트 내용 맨 앞에 삽입
    img_html = (
        f'<figure style="margin:0 0 16px 0; text-align:center;">'
        f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
        f'alt="{task.get("notice_name", "")} 썸네일">'
        f'</figure>\n'
    )
    new_content = img_html + post_html

    slogan = _re.sub(r"[^\w\s가-힣]", "", title)
    slogan = _re.sub(r"\s+", "-", slogan.strip())
    payload = {
        "id": str(post_id), "title": title, "content": new_content,
        "slogan": slogan, "visibility": 20, "category": 0,
        "tag": "", "acceptComment": 1, "published": 0,
        "password": "", "uselessMarginForEntry": 1,
        "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
        "thumbnail": cdn_url, "type": "post", "attachments": [],
        "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
    }
    hdrs = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"{blog_url}/manage/newpost/{post_id}?type=post",
        "Origin": blog_url,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = _req.put(f"{blog_url}/manage/post/{post_id}.json",
                    json=payload, cookies=cookies, headers=hdrs, timeout=20)
    if resp.status_code in (200, 201, 204):
        print(f"  ✅ 썸네일 이미지 삽입 완료 (첫 번째 이미지 → og:image 자동 설정)")
    else:
        print(f"  ⚠️  썸네일 PUT 실패: HTTP {resp.status_code}")


def _upload_pdf_attachment(page, blog_url: str, context, published_task_path: Path,
                           post_id: int = 0, post_title: str = "", post_html: str = "",
                           tags: list = None):
    """발행된 task의 PDF를 티스토리에 업로드하고 본문 끝에 다운로드 링크를 삽입한다."""
    import requests as _req, re as _re

    task_path = published_task_path
    if not task_path.exists():
        return

    task_text = task_path.read_text(encoding="utf-8")
    pdf_path = ""
    pdf_original_filename = ""
    for line in task_text.splitlines():
        if line.startswith("pdf_path:"):
            pdf_path = line.split(":", 1)[1].strip()
        elif line.startswith("pdf_original_filename:"):
            pdf_original_filename = line.split(":", 1)[1].strip()

    if not pdf_path:
        return

    from pathlib import Path as _Path
    pdf_file = _Path(pdf_path)
    if not pdf_file.exists():
        return

    if not pdf_original_filename:
        filename_meta = pdf_file.parent / "filename.txt"
        if filename_meta.exists():
            pdf_original_filename = filename_meta.read_text(encoding="utf-8").strip()
    if not pdf_original_filename:
        pdf_original_filename = "공고문.pdf"

    cookies = {c["name"]: c["value"] for c in context.cookies() if "tistory" in c.get("domain", "")}

    upload_url = f"{blog_url}/manage/post/attach.json"
    headers = {
        "Referer":          f"{blog_url}/manage/newpost/{post_id}" if post_id else f"{blog_url}/manage/newpost/",
        "Origin":           blog_url,
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    files = {"file": (pdf_original_filename, pdf_file.read_bytes(), "application/pdf")}

    try:
        resp = _req.post(upload_url, files=files, cookies=cookies, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  ⚠️  PDF 업로드 실패: {resp.status_code}")
            return
        data = resp.json()
        cdn_url = data.get("url", "")
        print(f"  📎 PDF 업로드 완료: {pdf_original_filename} ({data.get('size', 0):,} bytes)")

        # 본문 맨 위(썸네일 figure 바로 다음)에 다운로드 링크 삽입
        if not cdn_url or not post_id or not post_html:
            return
        if "공고문 원본 PDF" in post_html:
            return
        pdf_link = (
            f'<p style="text-align:center; margin:8px 0 20px;">'
            f'<a href="{cdn_url}" target="_blank" rel="noopener" '
            f'style="display:inline-block; padding:10px 20px; background:#2563eb; color:#fff; '
            f'border-radius:6px; text-decoration:none; font-size:14px; font-weight:bold;">'
            f'📄 공고문 원본 PDF 다운로드</a></p>\n'
        )
        # 썸네일 <figure> 다음에 삽입, 없으면 맨 앞에
        if post_html.startswith("<figure"):
            end = post_html.find("</figure>") + len("</figure>")
            new_content = post_html[:end] + "\n" + pdf_link + post_html[end:]
        else:
            new_content = pdf_link + post_html
        slogan = _re.sub(r"\s+", "-", _re.sub(r"[^\w\s가-힣]", "", post_title).strip())
        tag_str = ",".join(tags) if tags else ""
        payload = {
            "id": str(post_id), "title": post_title, "content": new_content,
            "slogan": slogan, "visibility": 20, "category": 0,
            "tag": tag_str, "acceptComment": 1, "published": 0,
            "password": "", "uselessMarginForEntry": 1,
            "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
            "type": "post", "attachments": [],
            "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
        }
        put_hdrs = {
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": f"{blog_url}/manage/newpost/{post_id}?type=post",
            "Origin": blog_url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        r = _req.put(f"{blog_url}/manage/post/{post_id}.json",
                     json=payload, cookies=cookies, headers=put_hdrs, timeout=20)
        if r.status_code in (200, 201, 204):
            print(f"  🔗 PDF 다운로드 링크 본문 삽입 완료")
        else:
            print(f"  ⚠️  링크 삽입 PUT 실패: {r.status_code}")
    except Exception as e:
        print(f"  ⚠️  PDF 처리 오류: {e}")


def run(blog: str):
    print("=" * 50)
    print(f"Publisher Agent — {blog}")
    print("=" * 50)

    config   = load_config(blog)
    blog_url = config.get("blog_url", f"https://{blog}.tistory.com")
    paths    = get_paths(blog)

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    task_file = get_next_task(paths["tasks_writing"])
    if not task_file:
        print(f"발행할 Task 없음 ({paths['tasks_writing']})")
        return

    task_id = task_file.stem
    print(f"Task: {task_id}")

    title, html, tags = read_draft(task_id, paths["articles_draft"])
    print(f"제목: {title}")
    print(f"태그: {', '.join(tags) if tags else '없음'}")

    BROWSER_DATA_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
        )
        page = context.new_page()

        if not is_logged_in(page, blog_url):
            print("  로그인 필요 → 자동 로그인 시도...")
            if not auto_login(page, blog_url):
                print("  재인증 시작...")
                context.close()
                context = reauth(pw, blog_url)
                if not context:
                    print("❌ 재인증 실패.")
                    shutil.move(str(task_file), str(paths["tasks_failed"] / task_file.name))
                    return
                page = context.new_page()
                if not is_logged_in(page, blog_url):
                    print("❌ 로그인 실패.")
                    context.close()
                    shutil.move(str(task_file), str(paths["tasks_failed"] / task_file.name))
                    return

        try:
            thumbnail_url = ""
            publish_html = html

            # llmenginehistory: 발행 전에 썸네일 생성
            # → 임시 파일로 저장 (대표이미지 파일 업로드용)
            # → CDN 업로드 후 html 앞에 삽입 (본문 상단 이미지용)
            category_id = 0
            thumbnail_file = ""
            if blog == "llmenginehistory":
                import sys as _sys, os as _os, tempfile as _tmp
                _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
                from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

                task_meta = {}
                for line in task_file.read_text(encoding="utf-8").splitlines():
                    for key in ("notice_name", "region", "housing_category",
                                "supply_type", "detail_url", "housing_source"):
                        if line.startswith(f"{key}:"):
                            task_meta[key] = line.split(":", 1)[1].strip()

                detail_url   = task_meta.get("detail_url", "")
                supply_type  = task_meta.get("supply_type", "")
                housing_src  = task_meta.get("housing_source", "")
                category_id  = get_category_id(supply_type, detail_url, housing_src)

                # 서브카테고리 ID 없으면 부모 카테고리로 폴백
                if not category_id:
                    category_id = (CATEGORY_APPLYHOME if "applyhome.co.kr" in detail_url
                                   else CATEGORY_LH)
                    print(f"  ⚠️  서브카테고리 미설정 — 부모 카테고리 사용 (id={category_id})")

                print(f"  🎨 썸네일 생성 중...")
                img_bytes = generate_thumbnail(task_meta)
                if img_bytes:
                    # 썸네일 캐시 저장 (재생성 방지)
                    thumb_cache = _os.path.join("data", blog, "thumbnails", f"{task_id}.png")
                    _os.makedirs(_os.path.dirname(thumb_cache), exist_ok=True)
                    with open(thumb_cache, "wb") as _f:
                        _f.write(img_bytes)

                    # 임시 파일 저장 (대표이미지 파일 업로드용)
                    tmp = _tmp.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp.write(img_bytes)
                    tmp.close()
                    thumbnail_file = tmp.name

                    # CDN 업로드 → 본문 상단 이미지 삽입
                    cookies = {c["name"]: c["value"] for c in context.cookies()
                               if "tistory" in c.get("domain", "")}
                    cdn_url = upload_thumbnail_to_tistory(img_bytes, blog_url, cookies)
                    if cdn_url:
                        img_html = (
                            f'<figure style="margin:0 0 16px 0; text-align:center;">'
                            f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
                            f'alt="{task_meta.get("notice_name", "")} 썸네일">'
                            f'</figure>\n'
                        )
                        publish_html = img_html + html

            # 발행 전 검증 (llmenginehistory만 적용)
            if blog == "llmenginehistory":
                issues = _validate_pre_publish(title, publish_html, tags, category_id)
                if issues:
                    reasons = "; ".join(issues)
                    print(f"❌ 발행 전 검증 실패: {reasons}")
                    raise RuntimeError(f"검증 실패: {reasons}")

            post_id = post_article(page, blog_url, title, publish_html,
                                   thumbnail_file, category_id=category_id,
                                   tags=tags)

            # 임시 파일 정리
            if thumbnail_file:
                try:
                    import os as _os2
                    _os2.unlink(thumbnail_file)
                except Exception:
                    pass
            shutil.move(str(task_file), str(paths["tasks_published"] / task_file.name))
            draft_src = paths["articles_draft"] / f"{task_id}.html"
            shutil.copy(str(draft_src), str(paths["articles_pub"] / f"{task_id}.html"))
            save_summary(task_id, html, paths["articles_summary"])
            print(f"✅ 발행 완료 → tasks/published/" + (f" (post_id={post_id})" if post_id else ""))

            published_task = paths["tasks_published"] / task_file.name

            # PDF 첨부파일 업로드 + 본문 다운로드 링크 삽입
            _upload_pdf_attachment(page, blog_url, context, published_task,
                                   post_id=post_id or 0,
                                   post_title=title,
                                   post_html=publish_html,
                                   tags=tags)
        except Exception as e:
            shutil.move(str(task_file), str(paths["tasks_failed"] / task_file.name))
            print(f"❌ 발행 실패: {e} → tasks/failed/")
        finally:
            context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", required=True, help="블로그 이름 (blogs/ 하위 폴더명)")
    args = parser.parse_args()
    run(args.blog)
