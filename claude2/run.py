"""
run.py — 메인 오케스트레이터
크론탭이 매일 실행. 뉴스 수집 → 작성 → 퇴고 → 발행 → 기록
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
BLOG = "dlarldks"
BLOG_DIR = BASE_DIR / "blogs" / BLOG
TASKS_PUBLISHED = BLOG_DIR / "tasks" / "published"
TASKS_FAILED = BLOG_DIR / "tasks" / "failed"


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_published_titles() -> list:
    """이미 발행된 글 제목 + 뉴스 URL 목록 (중복 방지용)"""
    if not TASKS_PUBLISHED.exists():
        return []
    titles = []
    for f in sorted(TASKS_PUBLISHED.glob("*.md")):
        content = load_file(f)
        title_match = re.search(r"^title: (.+)$", content, re.MULTILINE)
        news_match = re.search(r"^news: (.+)$", content, re.MULTILINE)
        if title_match:
            entry = {"title": title_match.group(1).strip()}
            if news_match:
                entry["news_url"] = news_match.group(1).strip()
            titles.append(entry)
    return titles


def save_published(title: str, content: str, research: dict):
    TASKS_PUBLISHED.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:40]
    path = TASKS_PUBLISHED / f"{timestamp}_{safe_title}.md"
    path.write_text(
        f"---\ntitle: {title}\ndate: {datetime.now().isoformat()}\n"
        f"news: {research.get('selected_news', {}).get('url', '')}\n"
        f"paper: {research.get('selected_paper', {}).get('url', '')}\n---\n\n{content}",
        encoding="utf-8",
    )
    return path


def append_metrics(title: str, date: str):
    metrics_path = BLOG_DIR / "metrics.md"
    existing = load_file(metrics_path)
    new_row = f"| {date} | {title} | - | - | - |"
    if "| 날짜 |" in existing:
        metrics_path.write_text(
            existing.replace(
                "| 날짜 | 제목 | URL | 조회수 | 비고 |",
                f"| 날짜 | 제목 | URL | 조회수 | 비고 |\n{new_row}",
            ),
            encoding="utf-8",
        )
    else:
        with open(metrics_path, "a", encoding="utf-8") as f:
            f.write(f"\n{new_row}")


def main():
    print("=" * 50)
    print(f"claude2 run.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 필수 환경변수 체크
    required = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
                "KAKAO_EMAIL", "KAKAO_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"❌ 환경변수 없음: {missing}")
        sys.exit(1)

    from tools.search import fetch_llm_news, fetch_trending_paper
    from agents.runner import run_researcher, run_writer, run_editor
    from tools.publisher import publish

    writing_guide = load_file(BLOG_DIR / "writing_guide.md")
    metrics = load_file(BLOG_DIR / "metrics.md")

    # 1. 소재 수집
    print("\n📡 소재 수집 중...")
    news_list = fetch_llm_news(limit=5)
    paper = fetch_trending_paper()
    print(f"  뉴스 {len(news_list)}건, 논문 1건 수집 완료")

    if not news_list and not paper:
        print("❌ 소재 수집 실패")
        sys.exit(1)

    # 2. Researcher
    print("\n🔍 Researcher 분석 중...")
    published_titles = get_published_titles()
    print(f"  기발행 글: {len(published_titles)}건 (중복 방지 적용)")
    try:
        research = run_researcher(news_list, paper, writing_guide, metrics, published_titles)
        print(f"  각도: {research.get('story_angle', '')[:60]}")
    except Exception as e:
        print(f"❌ Researcher 오류: {e}")
        sys.exit(1)

    # 3. Writer (GPT)
    print("\n✍️  Writer 작성 중 (GPT)...")
    try:
        draft = run_writer(research, writing_guide)
        print(f"  초안 완성 ({len(draft)}자)")
    except Exception as e:
        print(f"❌ Writer 오류: {e}")
        sys.exit(1)

    # 4. Editor (Claude)
    print("\n📝 Editor 퇴고 중...")
    try:
        final = run_editor(draft, writing_guide)
        print(f"  사람 냄새 점수: {final.get('human_score', '?')}/10")
        print(f"  최종 제목: {final.get('title', '')}")
    except Exception as e:
        print(f"❌ Editor 오류: {e}")
        sys.exit(1)

    title = final["title"]
    content = final["content"]
    tags = final.get("tags", [])

    # 5. 발행
    print("\n🚀 발행 중...")
    result = publish(title, content, tags)

    if result["success"]:
        save_published(title, content, research)
        append_metrics(title, datetime.now().strftime("%Y-%m-%d"))
        print(f"\n✅ 완료: {title}")
    else:
        TASKS_FAILED.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (TASKS_FAILED / f"{ts}_failed.md").write_text(
            f"# 발행 실패\n\n**제목:** {title}\n**오류:** {result.get('error')}\n\n{content}",
            encoding="utf-8",
        )
        print(f"\n❌ 발행 실패: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
