"""
apply_safety_margin.py — 기존 발행 글에 안전마진 분석 섹션 소급 적용

실행 (전체):  python apply_safety_margin.py
실행 (1건):   python apply_safety_margin.py --task 20260606_007
"""

import re
import sys
import time
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from agents.writer_agent import (
    _parse_sale_info,
    _build_safety_margin_html,
)
from tools.market_price import get_market_price

BLOG      = "llmenginehistory"
BLOG_URL  = "https://llmenginehistory.tistory.com"
TASKS_DIR = Path(f"blogs/{BLOG}/tasks/published")


def parse_task(path):
    result = {"task_id": path.stem}
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return result
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            result[k.strip()] = v.strip()
    return result


def get_article_html(task_id):
    """저장된 HTML 파일 반환 (title 포함). 없으면 ("", "")."""
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            raw = p.read_text(encoding="utf-8")
            m = re.match(r"<!-- TITLE: (.+?) -->\n?", raw)
            title = m.group(1).strip() if m else ""
            html  = re.sub(r"<!-- TITLE: .+? -->\n?", "", raw).strip()
            return title, html
    return "", ""


def find_post_id(posts, notice_name, task_id):
    _, html = get_article_html(task_id)
    # HTML 파일의 TITLE로 먼저 매칭
    raw = ""
    for folder in ("published", "preview", "draft"):
        p = Path(f"articles/{BLOG}/{folder}/{task_id}.html")
        if p.exists():
            raw = p.read_text(encoding="utf-8")
            break
    title_m = re.match(r"<!-- TITLE: (.+?) -->", raw)
    if title_m:
        pub_title = re.sub(r"^[🏠\s]+", "", title_m.group(1)).strip()
        for p in posts:
            if re.sub(r"^[🏠\s]+", "", p["title"]).strip() == pub_title:
                return p["id"]
        for p in posts:
            if pub_title[:15] and pub_title[:15] in re.sub(r"^[🏠\s]+", "", p["title"]).strip():
                return p["id"]
    # notice_name으로 폴백
    clean = re.sub(r"\s+", "", re.sub(r"[\(\[].+?[\)\]]", "", notice_name).strip())
    for length in [10, 8, 6, 5, 4]:
        kw = clean[:length]
        if not kw:
            continue
        for p in posts:
            if kw in re.sub(r"\s+", "", p["title"]):
                return p["id"]
    return 0


def get_post_list(page):
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


def put_post(post_id, title, html, cookies):
    slogan = re.sub(r"\s+", "-", re.sub(r"[^\w\s가-힣]", "", title).strip())
    payload = {
        "id": str(post_id), "title": title, "content": html,
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
    return r.status_code in (200, 201, 204)


def main(only_task_id=None):
    print("=" * 55)
    print("기존 발행 글 안전마진 분석 소급 적용")
    print("=" * 55)

    # 대상 태스크 수집
    targets = []
    for tf in sorted(TASKS_DIR.glob("*.md")):
        if tf.stem.startswith("."):
            continue
        if only_task_id and tf.stem != only_task_id:
            continue
        t = parse_task(tf)
        if not t.get("sale_price"):
            continue
        if not t.get("location_detail") and not t.get("region"):
            continue
        targets.append(t)

    if not targets:
        print("적용 대상 없음")
        return

    print(f"대상: {len(targets)}개\n")

    # Playwright 로그인 + 포스트 목록
    from agents.publisher_agent import auto_login
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="browser_data", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = ctx.new_page()
        page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
        if "login" in page.url:
            auto_login(page, BLOG_URL)
        print("로그인 확인")
        posts = get_post_list(page)
        print(f"포스트 {len(posts)}개 확인\n")
        cookies = {c["name"]: c["value"] for c in ctx.cookies()
                   if "tistory" in c.get("domain", "")}
        ctx.close()

    ok = skip = fail = 0
    for t in targets:
        task_id     = t["task_id"]
        notice_name = t.get("notice_name", "")
        location    = t.get("location_detail") or t.get("region", "")
        sale_price  = t.get("sale_price", "")
        house_types = t.get("house_types", "")

        print(f"[{task_id}] {notice_name[:35]}")

        # 저장된 HTML 불러오기
        title, html = get_article_html(task_id)
        if not html:
            print(f"  HTML 파일 없음 — 스킵")
            skip += 1
            continue

        # 이미 적용된 경우 스킵
        if "안전마진 분석" in html:
            print(f"  이미 적용됨 — 스킵")
            skip += 1
            continue

        # 안전마진 섹션 생성
        sale_info = _parse_sale_info(sale_price, house_types)
        if not sale_info:
            print(f"  분양가 파싱 실패 — 스킵")
            skip += 1
            continue

        print(f"  시세 조회 중... ({location[:20]})")
        market_data = get_market_price(location, sale_info["area_m2"])
        safety_html = _build_safety_margin_html(t, market_data)
        if not safety_html:
            print(f"  시세 데이터 없음 — 스킵")
            skip += 1
            continue

        # 청약 조건 섹션 앞에 삽입
        if "<h2>청약 조건</h2>" in html:
            new_html = html.replace("<h2>청약 조건</h2>", safety_html + "<h2>청약 조건</h2>", 1)
        else:
            # 섹션 없으면 맨 끝에 추가
            new_html = html + "\n" + safety_html

        # post_id 찾기
        post_id = find_post_id(posts, notice_name, task_id)
        if not post_id:
            print(f"  포스트 못 찾음 — 스킵")
            skip += 1
            continue

        # PUT
        if put_post(post_id, title, new_html, cookies):
            print(f"  안전마진 섹션 적용 완료 (post_id={post_id})")
            ok += 1
        else:
            print(f"  PUT 실패")
            fail += 1

        time.sleep(1)

    print(f"\n완료 {ok}개 / 스킵 {skip}개 / 실패 {fail}개")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=None, help="특정 task_id만 적용 (예: 20260606_007)")
    args = parser.parse_args()
    main(only_task_id=args.task)
