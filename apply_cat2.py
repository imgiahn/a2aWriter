"""
카테고리 소급 적용 v2 — Playwright로 에디터에서 content 읽어 PUT
"""
import os, re, time, requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BLOG_URL         = "https://llmenginehistory.tistory.com"
CATEGORY_LH      = 1311445
CATEGORY_APPLYHOME = 1311446
TASKS_DIR        = Path("blogs/llmenginehistory/tasks/published")
EMAIL    = os.getenv("KAKAO_EMAIL", "")
PASSWORD = os.getenv("KAKAO_PASSWORD", "")


def get_category_for_task(task_path):
    for line in task_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("detail_url:"):
            url = line.split(":", 1)[1].strip()
            if "applyhome.co.kr" in url: return CATEGORY_APPLYHOME
            if "apply.lh.or.kr" in url:  return CATEGORY_LH
    return 0


def get_post_list(page):
    posts = []
    for n in range(1, 5):
        page.goto(BLOG_URL + "/manage/posts?page=" + str(n), timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(2000)
        try: page.wait_for_selector("a.link_cont", timeout=8000)
        except: pass
        result = page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('a.link_cont').forEach(lk => {
                const li = lk.closest('li');
                const btn = li ? li.querySelector('a.btn_post') : null;
                if (!btn) return;
                const m = btn.getAttribute('href').match(/\/manage\/post\/(\d+)/);
                if (m) items.push({id: parseInt(m[1]),
                    title: (lk.getAttribute('title')||lk.textContent).trim()});
            });
            return items;
        }""")
        posts.extend(result)
        if not result or not page.query_selector("a[href*='page=" + str(n+1) + "']"):
            break
    return posts


def find_post_id(posts, task_path):
    for folder in ("published", "draft", "preview"):
        p = Path(f"articles/llmenginehistory/{folder}/{task_path.stem}.html")
        if p.exists():
            m = re.match(r"<!-- TITLE: (.+?) -->", p.read_text(encoding="utf-8"))
            if m:
                pub_title = re.sub(r"^[🏠\s]+", "", m.group(1)).strip()
                for post in posts:
                    clean = re.sub(r"^[🏠\s]+", "", post["title"]).strip()
                    if clean == pub_title or clean[:20] == pub_title[:20]:
                        return post["id"]
    notice_name = ""
    for line in task_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("notice_name:"):
            notice_name = line.split(":", 1)[1].strip()
            break
    if notice_name:
        kw = re.sub(r"\s+", "", re.sub(r"[\(\[].+?[\)\]]", "", notice_name).strip())[:10]
        for post in posts:
            if kw and kw in re.sub(r"\s+", "", post["title"]):
                return post["id"]
    return 0


def read_and_update(page, post_id, category_id, cookies):
    """에디터 페이지에서 content/title 읽어 category만 바꿔 PUT."""
    page.goto(BLOG_URL + "/manage/post/" + str(post_id), timeout=20000, wait_until="networkidle")
    page.wait_for_timeout(2000)
    try:
        page.wait_for_function("typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor !== null", timeout=10000)
        page.wait_for_timeout(1000)
    except: pass

    # tinyMCE에서 content 읽기
    content = page.evaluate("""() => {
        try { return tinyMCE.activeEditor.getContent(); } catch(e) { return ''; }
    }""")
    # title 읽기
    title = page.evaluate("""() => {
        const t = document.querySelector('#post-title-inp, .tf_subject, textarea[id*=title]');
        return t ? t.value : '';
    }""")
    # tag 읽기
    tag = page.evaluate("""() => {
        const t = document.querySelector('#tagText, input[name=tag], .tag-input');
        return t ? t.value : '';
    }""")

    if not content or not title:
        return False, f"에디터 읽기 실패 (title={bool(title)}, content={len(content)}자)"

    slogan = re.sub(r"\s+", "-", re.sub(r"[^\w\s가-힣]", "", title).strip())
    payload = {
        "id": str(post_id), "title": title, "content": content,
        "slogan": slogan, "visibility": 20, "category": category_id,
        "tag": tag or "", "acceptComment": 1, "published": 0,
        "password": "", "uselessMarginForEntry": 1,
        "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
        "type": "post", "attachments": [],
        "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
    }
    r = requests.put(
        BLOG_URL + "/manage/post/" + str(post_id) + ".json",
        json=payload, cookies=cookies,
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": BLOG_URL + "/manage/newpost/" + str(post_id) + "?type=post",
            "Origin": BLOG_URL,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=20,
    )
    if r.status_code in (200, 201, 204):
        return True, ""
    return False, f"PUT {r.status_code}: {r.text[:80]}"


with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--disable-dev-shm-usage","--disable-gpu","--no-sandbox"]
    )
    page = ctx.new_page()

    try: page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
    except: pass
    if "login" in page.url:
        try: page.goto("https://www.tistory.com/auth/login", timeout=20000, wait_until="domcontentloaded")
        except: pass
        page.wait_for_timeout(1000)
        page.locator("a.link_kakao_id").click()
        page.wait_for_timeout(3000)
        if "accounts.kakao.com" in page.url:
            page.locator("input[name='loginId']").fill(EMAIL)
            page.locator("input[name='password']").fill(PASSWORD)
            page.locator("button[type='submit']").click()
            page.wait_for_timeout(5000)
        try: page.goto(BLOG_URL + "/manage", timeout=20000, wait_until="domcontentloaded")
        except: pass
    print("로그인:", page.url)

    cookies = {c["name"]: c["value"] for c in ctx.cookies() if "tistory" in c.get("domain", "")}
    posts = get_post_list(page)
    print(f"포스트 {len(posts)}개\n")

    ok = skip = fail = 0
    for task_path in sorted(TASKS_DIR.glob("*.md")):
        if "deleted" in task_path.name: continue
        cat_id = get_category_for_task(task_path)
        if not cat_id:
            print(f"  [{task_path.stem}] ⏭  스킵")
            skip += 1; continue

        cat_name = "LH 청약 플러스" if cat_id == CATEGORY_LH else "청약 Home"
        post_id = find_post_id(posts, task_path)
        if not post_id:
            print(f"  [{task_path.stem}] ⚠️  포스트 못 찾음")
            skip += 1; continue

        success, err = read_and_update(page, post_id, cat_id, cookies)
        if success:
            print(f"  [{task_path.stem}] ✅ {cat_name} (post_id={post_id})")
            ok += 1
        else:
            print(f"  [{task_path.stem}] ❌ {err}")
            fail += 1
        time.sleep(1)

    ctx.close()
print(f"\n완료 — 성공 {ok}개 / 스킵 {skip}개 / 실패 {fail}개")
