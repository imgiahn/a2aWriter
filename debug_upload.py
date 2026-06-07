"""썸네일: 이미지 생성 → 티스토리 업로드 → thumbnail 필드 확인"""
import os, base64, requests, json
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login

load_dotenv()

BLOG_URL = "https://llmenginehistory.tistory.com"
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
API_KEY  = os.getenv("AZURE_OPENAI_API_KEY")

# 1. gpt-image-2로 이미지 생성
print("=== 1. 이미지 생성 ===")
resp = requests.post(
    f"{ENDPOINT}/openai/deployments/gpt-image-2/images/generations?api-version=2025-04-01-preview",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json={
        "prompt": "청약 아파트 분양 공고 썸네일. 한국 현대 아파트 단지 전경, 파란 하늘, 깔끔한 미니멀 디자인, 부동산 블로그 썸네일 스타일",
        "n": 1,
        "size": "1024x1024",
        "output_format": "png"
    },
    timeout=60
)
print("HTTP:", resp.status_code)
data = resp.json()
b64 = data["data"][0]["b64_json"]
img_bytes = base64.b64decode(b64)
print(f"이미지 크기: {len(img_bytes):,} bytes")
Path("/tmp/test_thumb.png").write_bytes(img_bytes)

# 2. 쿠키 추출
print("\n=== 2. 쿠키 추출 ===")
cookies = {}
put_bodies = []
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir="browser_data", headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    def on_req(req):
        if req.method == "POST" and "/manage/post/" in req.url and "image" in req.url.lower():
            put_bodies.append(f"POST {req.url}")
        if req.method == "PUT" and "/manage/post/" in req.url:
            try:
                b = json.loads(req.post_data or "{}")
                put_bodies.append({"thumbnail": b.get("thumbnail"), "url": req.url})
            except Exception:
                pass

    page.on("request", on_req)
    page.goto(f"{BLOG_URL}/manage", timeout=15000, wait_until="networkidle")
    if "login" in page.url:
        auto_login(page, BLOG_URL)
    for c in ctx.cookies():
        if "tistory" in c.get("domain", ""):
            cookies[c["name"]] = c["value"]
    ctx.close()
print(f"쿠키 {len(cookies)}개")

# 3. attach.json으로 이미지 업로드 시도
print("\n=== 3. 이미지 업로드 (attach.json) ===")
hdrs = {
    "Referer": f"{BLOG_URL}/manage/newpost/",
    "Origin":  BLOG_URL,
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}
r2 = requests.post(f"{BLOG_URL}/manage/post/attach.json",
    files={"file": ("thumbnail.png", img_bytes, "image/png")},
    cookies=cookies, headers=hdrs, timeout=30)
print(f"attach.json: HTTP {r2.status_code}")
print(f"응답: {r2.text[:300]}")

# 4. image.json 엔드포인트도 시도
print("\n=== 4. 이미지 업로드 (image.json) ===")
r3 = requests.post(f"{BLOG_URL}/manage/post/image.json",
    files={"image": ("thumbnail.png", img_bytes, "image/png")},
    cookies=cookies, headers=hdrs, timeout=30)
print(f"image.json: HTTP {r3.status_code}")
print(f"응답: {r3.text[:300]}")
