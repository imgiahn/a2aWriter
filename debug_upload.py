"""thumbnail 필드에 이미지 URL 넣어서 PUT 테스트"""
import os, base64, requests, json, re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login

load_dotenv()

BLOG_URL = "https://llmenginehistory.tistory.com"
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
API_KEY  = os.getenv("AZURE_OPENAI_API_KEY")

# 1. 이미지 생성
print("이미지 생성 중...")
resp = requests.post(
    f"{ENDPOINT}/openai/deployments/gpt-image-2/images/generations?api-version=2025-04-01-preview",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json={"prompt": "한국 아파트 청약 분양 공고 블로그 썸네일. 현대적 아파트 단지 전경, 파란 하늘, 미니멀 디자인", "n": 1, "size": "1024x1024"},
    timeout=60
)
img_bytes = base64.b64decode(resp.json()["data"][0]["b64_json"])
print(f"이미지 생성 완료: {len(img_bytes):,} bytes")

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

# 3. 이미지 업로드
hdrs = {
    "Referer": f"{BLOG_URL}/manage/newpost/",
    "Origin": BLOG_URL, "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}
r = requests.post(f"{BLOG_URL}/manage/post/attach.json",
    files={"file": ("thumb.png", img_bytes, "image/png")},
    cookies=cookies, headers=hdrs, timeout=30)
upload_data = r.json()
img_url = upload_data["url"]
img_key = upload_data.get("key", "")
print(f"업로드 완료: {img_url[:80]}...")

# 4. 포스트 23번에 thumbnail 설정 시도 (여러 포맷 테스트)
put_hdrs = {
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BLOG_URL}/manage/newpost/23?type=post",
    "Origin": BLOG_URL, "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}

# 현재 포스트 HTML
preview = Path("articles/llmenginehistory/preview/20260605_011.html")
content = re.sub(r"<!-- TITLE: .+? -->\n?", "", preview.read_text(encoding="utf-8"), flags=re.DOTALL) if preview.exists() else ""

base_payload = {
    "id": "23", "title": "🏠 화성동탄2 공공분양 신청 조건과 분양가 정리",
    "content": content,
    "slogan": "화성동탄2-공공분양-신청-조건과-분양가-정리",
    "visibility": 20, "category": 0, "tag": "", "acceptComment": 1,
    "published": 0, "password": "", "uselessMarginForEntry": 1,
    "daumLike": None, "cclCommercial": 0, "cclDerive": 0,
    "type": "post", "attachments": [], "recaptchaValue": "",
    "draftSequence": None, "totalWritingTimeMs": 5000,
}

# URL 앞부분만 (credential 제외)
clean_url = img_url.split("?")[0]

for thumb_val in [img_url, clean_url, img_key, {"url": img_url}, {"url": clean_url, "key": img_key}]:
    payload = {**base_payload, "thumbnail": thumb_val}
    r2 = requests.put(f"{BLOG_URL}/manage/post/23.json",
        json=payload, cookies=cookies, headers=put_hdrs, timeout=20)
    print(f"thumbnail={str(thumb_val)[:60]} → HTTP {r2.status_code} | {r2.text[:80]}")
    if r2.status_code == 200:
        break
