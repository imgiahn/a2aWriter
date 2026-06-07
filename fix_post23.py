"""포스트 23번 썸네일 적용"""
import re, requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

load_dotenv()

BLOG_URL = "https://llmenginehistory.tistory.com"
POST_ID  = 23

# 쿠키
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

# HTML
for folder in ("preview", "draft", "published"):
    html_path = Path(f"articles/llmenginehistory/{folder}/20260605_011.html")
    if html_path.exists():
        break
post_html = re.sub(r"<!-- TITLE: .+? -->\n?", "",
                   html_path.read_text(encoding="utf-8"), flags=re.DOTALL)
print(f"HTML 경로: {html_path} / 길이: {len(post_html)}")

# 이미지 생성
task = {"notice_name": "화성동탄2 공공분양", "region": "경기",
        "housing_category": "sale", "supply_type": "공공분양"}
img = generate_thumbnail(task)
cdn_url = upload_thumbnail_to_tistory(img, BLOG_URL, cookies)
print(f"CDN: {cdn_url[:80]}")

img_html = (
    f'<figure style="margin:0 0 16px 0; text-align:center;">'
    f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;">'
    f'</figure>\n'
)
new_content = img_html + post_html

title  = "🏠 화성동탄2 공공분양 신청 조건과 분양가 정리"
slogan = re.sub(r"[^\w\s가-힣]", "", title)
slogan = re.sub(r"\s+", "-", slogan.strip())

payload = {
    "id": str(POST_ID), "title": title, "content": new_content,
    "slogan": "", "visibility": 20, "category": 0,
    "tag": "", "acceptComment": 1, "published": 0,
    "password": "", "uselessMarginForEntry": 1,
    "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
    "thumbnail": cdn_url, "type": "post", "attachments": [],
    "recaptchaValue": "", "draftSequence": None, "totalWritingTimeMs": 3000,
}
hdrs = {
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BLOG_URL}/manage/newpost/{POST_ID}?type=post",
    "Origin": BLOG_URL, "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}
r = requests.put(f"{BLOG_URL}/manage/post/{POST_ID}.json",
                 json=payload, cookies=cookies, headers=hdrs, timeout=20)
print(f"PUT → HTTP {r.status_code} | {r.text[:150]}")
