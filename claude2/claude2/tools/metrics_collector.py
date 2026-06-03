"""
Metrics Collector — 티스토리 조회수 수집
Playwright로 관리자 페이지 방문 후 조회수 스크랩
"""

import os
import re
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright

BLOG_NAME = "dlarldks"
BLOG_URL = f"https://{BLOG_NAME}.tistory.com"
BROWSER_DATA_DIR = Path(__file__).parent.parent / "browser_data"
METRICS_PATH = Path(__file__).parent.parent / "blogs" / "dlarldks" / "metrics.md"


def get_recent_posts_stats() -> list:
    """관리자 페이지에서 최근 글 조회수 수집"""
    stats = []

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=True,
        )
        page = context.new_page()

        try:
            page.goto(f"{BLOG_URL}/manage/posts/", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)

            rows = page.query_selector_all("table tr, .post-item")
            for row in rows[:10]:
                try:
                    title_el = row.query_selector("a.title, .post-title a")
                    view_el = row.query_selector(".cnt_view, .post-view")
                    if title_el and view_el:
                        stats.append({
                            "title": title_el.inner_text().strip(),
                            "url": title_el.get_attribute("href") or "",
                            "views": view_el.inner_text().strip(),
                        })
                except Exception:
                    pass

        except Exception as e:
            print(f"  조회수 수집 오류: {e}")
        finally:
            context.close()

    return stats


def update_metrics_views(stats: list):
    """metrics.md의 조회수 컬럼 업데이트"""
    if not METRICS_PATH.exists() or not stats:
        return

    content = METRICS_PATH.read_text(encoding="utf-8")

    for stat in stats:
        title_short = stat["title"][:20]
        views = stat["views"]
        # 해당 행의 조회수 미수집 부분 업데이트
        content = re.sub(
            rf"(\| [^\|]*{re.escape(title_short)}[^\|]* \| [^\|]+ \|) - (\|)",
            rf"\1 {views} \2",
            content
        )

    METRICS_PATH.write_text(content, encoding="utf-8")
    print(f"  ✅ 조회수 업데이트 완료 ({len(stats)}건)")


if __name__ == "__main__":
    print("조회수 수집 중...")
    stats = get_recent_posts_stats()
    for s in stats:
        print(f"  {s['title'][:30]} — {s['views']} 조회")
    update_metrics_views(stats)
