"""포스트 24번 썸네일 — 내용 첫 이미지로 삽입 테스트"""
import os, base64, requests, re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

load_dotenv()

BLOG_URL = "https://llmenginehistory.tistory.com"
POST_ID  = 24

task = {
    "notice_name":      "풍무역 푸르지오 시티",
    "region":           "경기",
    "housing_category": "general",
    "supply_type":      "오피스텔",
}

# 1. 이미지 생성
print("썸네일 생성 중...")
img_bytes = generate_thumbnail(task)
if not img_bytes:
    print("❌ 생성 실패")
    exit(1)

# 2. 쿠키 추출
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

# 3. 업로드
cdn_url = upload_thumbnail_to_tistory(img_bytes, BLOG_URL, cookies)
if not cdn_url:
    print("❌ 업로드 실패")
    exit(1)

# 4. 포스트 내용 앞에 이미지 삽입
preview = Path("articles/llmenginehistory/preview/20260606_001.html")
post_html = re.sub(r"<!-- TITLE: .+? -->\n?", "",
                   preview.read_text(encoding="utf-8"), flags=re.DOTALL)

img_html = (
    f'<figure style="margin:0 0 16px 0; text-align:center;">'
    f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
    f'alt="풍무역 푸르지오 시티 썸네일">'
    f'</figure>\n'
)
new_content = img_html + post_html
print(f"content 길이: {len(new_content)}")

# 5. PUT
title  = "🏠 풍무역 푸르지오 시티 오피스텔 신청 조건 총정리"
slogan = re.sub(r"[^\w\s가-힣]", "", title)
slogan = re.sub(r"\s+", "-", slogan.strip())
payload = {
    "id": str(POST_ID), "title": title, "content": new_content,
    "slogan": slogan, "visibility": 20, "category": 0,
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
print(f"PUT → HTTP {r.status_code} | {r.text[:80]}")
