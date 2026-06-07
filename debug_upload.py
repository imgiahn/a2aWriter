"""PDF 업로드 실제 테스트 + 원본 파일명 보존 확인"""
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login
from pathlib import Path
import requests, json

BLOG_URL = "https://llmenginehistory.tistory.com"
UPLOAD_URL = f"{BLOG_URL}/manage/post/attach.json"

test_pdf = list(Path("data/llmenginehistory/notices").rglob("original.pdf"))[0]
notice_id = test_pdf.parent.name
print(f"테스트 PDF: {test_pdf} (notice_id={notice_id})")

# 1. 쿠키 추출
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

# 2. PDF 업로드 시도 (파일명: 원본 공고명 사용)
original_filename = f"LH공고_{notice_id}.pdf"
headers = {
    "Referer": f"{BLOG_URL}/manage/newpost/",
    "Origin":  BLOG_URL,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

with open(test_pdf, "rb") as f:
    pdf_bytes = f.read()

# multipart/form-data로 업로드
files = {"file": (original_filename, pdf_bytes, "application/pdf")}
resp = requests.post(UPLOAD_URL, files=files, cookies=cookies, headers=headers, timeout=30)
print(f"\nPOST {UPLOAD_URL} → {resp.status_code}")
print("응답:", resp.text[:500])
