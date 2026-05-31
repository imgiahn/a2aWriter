"""
setup_server.py — EC2 서버에서 직접 실행

headless 브라우저로 카카오 자격증명 자동 입력 후
이메일 인증 링크 클릭만 기다린다.
"""

import os
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

KAKAO_EMAIL      = os.getenv("KAKAO_EMAIL")
KAKAO_PASSWORD   = os.getenv("KAKAO_PASSWORD")
BLOG_URL         = "https://mbtireallove.tistory.com"
BROWSER_DATA_DIR = Path("browser_data")


def run():
    print("=" * 50)
    print("카카오 로그인 (서버 headless)")
    print("=" * 50)

    if BROWSER_DATA_DIR.exists():
        shutil.rmtree(BROWSER_DATA_DIR)
    BROWSER_DATA_DIR.mkdir()

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
        )
        page = context.new_page()

        print("티스토리 로그인 페이지 이동 중...")
        page.goto("https://www.tistory.com/auth/login")
        page.wait_for_load_state("networkidle")

        print("카카오 로그인 버튼 클릭...")
        page.click("a.link_kakao_id")
        page.wait_for_load_state("networkidle")

        print("카카오 자격증명 입력 중...")
        page.fill("input[name='loginId']", KAKAO_EMAIL)
        page.fill("input[name='password']", KAKAO_PASSWORD)
        page.click("button[type='submit']")

        print("카카오 응답 대기 중...")

        # 이메일 인증 없이 바로 리다이렉트되는지 확인
        try:
            page.wait_for_url("**/tistory.com/**", timeout=10000)
            print("이메일 인증 없이 로그인 성공!")
        except Exception:
            print()
            print("=" * 50)
            print(f"  이메일 인증 필요!")
            print(f"  {KAKAO_EMAIL} 메일함에서")
            print(f"  [로그인 승인] 버튼을 클릭해주세요.")
            print(f"  최대 3분 대기합니다...")
            print("=" * 50)
            print()

            try:
                page.wait_for_url("**/tistory.com/**", timeout=180000)
                print("이메일 인증 완료!")
            except Exception:
                print("시간 초과. 다시 실행해주세요.")
                context.close()
                return

        # 로그인 확인
        page.goto(f"{BLOG_URL}/manage", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)

        if "/manage" in page.url and "login" not in page.url:
            print()
            print("✅ 티스토리 로그인 확인! 쿠키 저장 완료.")
            print("   이제 publisher_agent가 자동 로그인됩니다.")
        else:
            print(f"❌ 로그인 실패. URL: {page.url}")

        context.close()


if __name__ == "__main__":
    run()
