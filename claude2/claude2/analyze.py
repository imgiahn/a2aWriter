"""
analyze.py — 주간 피드백 분석기
크론탭이 매주 월요일 실행. 성과 분석 → writing_guide 업데이트
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
BLOG_DIR = BASE_DIR / "blogs" / "dlarldks"


def get_last_week_articles() -> list:
    """지난 주 발행된 글 목록"""
    published_dir = BLOG_DIR / "tasks" / "published"
    articles = []
    cutoff = datetime.now() - timedelta(days=7)

    for f in published_dir.glob("*.md"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime >= cutoff:
                content = f.read_text(encoding="utf-8")
                title_match = re.search(r"title: (.+)", content)
                date_match = re.search(r"date: (.+)", content)
                articles.append({
                    "file": f.name,
                    "title": title_match.group(1) if title_match else f.stem,
                    "date": date_match.group(1)[:10] if date_match else str(mtime.date()),
                    "views": "미수집",
                })
        except Exception:
            pass

    return articles


def update_writing_guide(new_insights: str):
    """writing_guide.md의 성과 기반 인사이트 섹션 업데이트"""
    guide_path = BLOG_DIR / "writing_guide.md"
    content = guide_path.read_text(encoding="utf-8")

    section_marker = "## 성과 기반 인사이트"
    updated = f"{section_marker}\n\n{new_insights}"

    if section_marker in content:
        content = re.sub(
            rf"{re.escape(section_marker)}.*",
            updated,
            content,
            flags=re.DOTALL,
        )
    else:
        content += f"\n\n{updated}"

    guide_path.write_text(content, encoding="utf-8")


def append_insight_history(summary: str, period: str):
    """metrics.md에 인사이트 히스토리 추가"""
    metrics_path = BLOG_DIR / "metrics.md"
    entry = f"\n### {period}\n{summary}\n"
    with open(metrics_path, "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    print("=" * 50)
    print(f"claude2 analyze.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    from tools.metrics_collector import get_recent_posts_stats, update_metrics_views
    from agents.runner import run_analyzer

    # 조회수 먼저 수집
    print("\n📊 조회수 수집 중...")
    try:
        stats = get_recent_posts_stats()
        update_metrics_views(stats)
        print(f"  {len(stats)}건 업데이트")
    except Exception as e:
        print(f"  조회수 수집 실패 (계속 진행): {e}")

    # 지난 주 글 목록
    articles = get_last_week_articles()
    if not articles:
        print("\n지난 주 발행된 글 없음 — 분석 건너뜀")
        return

    print(f"\n📝 지난 주 발행: {len(articles)}건")

    metrics = (BLOG_DIR / "metrics.md").read_text(encoding="utf-8")
    writing_guide = (BLOG_DIR / "writing_guide.md").read_text(encoding="utf-8")

    # Analyzer 실행
    print("\n🧠 Analyzer (Claude Opus) 분석 중...")
    try:
        result = run_analyzer(metrics, writing_guide, articles)
        print(f"  분석 완료: {result.get('summary', '')[:80]}")
    except Exception as e:
        print(f"❌ Analyzer 오류: {e}")
        sys.exit(1)

    # writing_guide 업데이트
    if result.get("writing_guide_update"):
        update_writing_guide(result["writing_guide_update"])
        print("\n✅ writing_guide.md 업데이트 완료")

    # 히스토리 기록
    append_insight_history(result.get("summary", ""), result.get("period", ""))
    print("✅ 인사이트 히스토리 기록 완료")


if __name__ == "__main__":
    main()
