"""화성동탄2 (20260605_011) 재발행 + 썸네일"""
import re, shutil
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from agents.publisher_agent import auto_login, post_article, save_summary, BROWSER_DATA_DIR
from tools.thumbnail_gen import generate_thumbnail, upload_thumbnail_to_tistory

load_dotenv()

BLOG     = "llmenginehistory"
BLOG_URL = "https://llmenginehistory.tistory.com"
TASK_ID  = "20260605_011"

# 경로
draft_path   = Path(f"articles/{BLOG}/draft/{TASK_ID}.html")
pub_art_path = Path(f"articles/{BLOG}/published/{TASK_ID}.html")
summary_path = Path(f"articles/{BLOG}/summary")

# draft 읽기
raw = draft_path.read_text(encoding="utf-8")
m = re.match(r"<!-- TITLE: (.+?) -->\n?(.*)", raw, re.DOTALL)
title   = m.group(1)
content = m.group(2)
print(f"제목: {title}")
print(f"content 길이: {len(content)}")

# 썸네일 생성
task = {"notice_name": "화성동탄2 공공분양", "region": "경기",
        "housing_category": "sale", "supply_type": "공공분양"}

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR), headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = ctx.new_page()

    if not (lambda p: "/manage" in p.url and "login" not in p.url)(
        (lambda: page.goto(f"{BLOG_URL}/manage", timeout=15000,
                           wait_until="networkidle") or page)()
    ):
        print("자동 로그인...")
        auto_login(page, BLOG_URL)

    # 썸네일 생성 + 업로드
    print("썸네일 생성 중...")
    cookies = {c["name"]: c["value"] for c in ctx.cookies()
               if "tistory" in c.get("domain", "")}
    img_bytes = generate_thumbnail(task)
    cdn_url   = upload_thumbnail_to_tistory(img_bytes, BLOG_URL, cookies) if img_bytes else ""

    if cdn_url:
        img_html = (
            f'<figure style="margin:0 0 16px 0; text-align:center;">'
            f'<img src="{cdn_url}" style="width:100%; max-width:800px; border-radius:8px;" '
            f'alt="화성동탄2 공공분양 썸네일">'
            f'</figure>\n'
        )
        final_content = img_html + content
    else:
        final_content = content

    # 발행
    print("발행 중...")
    post_id = post_article(page, BLOG_URL, title, final_content)
    print(f"✅ 발행 완료 (post_id={post_id})")

    # 파일 저장
    pub_art_path.write_text(f"<!-- TITLE: {title} -->\n{final_content}", encoding="utf-8")
    save_summary(TASK_ID, final_content, summary_path)

    ctx.close()
