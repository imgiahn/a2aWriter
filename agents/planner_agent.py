"""
Planner Agent

역할: 블로그별 콘텐츠 기획 및 Task 생성
실행: python agents/planner_agent.py --blog mbtireallove [--suggest]
      python agents/planner_agent.py --blog llmenginehistory
"""

import os
import re
import sys
import json
import argparse
from datetime import date
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

azure_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    timeout=60,
    max_retries=1,
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


def get_paths(blog: str) -> dict:
    base = Path(f"blogs/{blog}")
    return {
        "memory":      base / "memory",
        "planned":     base / "tasks/planned",
        "suggestions": base / "tasks/suggestions",
        "published":   base / "tasks/published",
    }


def load_memory(memory_dir: Path) -> dict:
    result = {}
    for key in ("history", "decisions", "metrics"):
        path = memory_dir / f"{key}.md"
        result[key] = path.read_text(encoding="utf-8") if path.exists() else ""
    return result


def get_existing_topics(blog: str) -> set:
    topics = set()
    base = Path(f"blogs/{blog}/tasks")
    for folder in ["planned", "writing", "published", "failed", "suggestions"]:
        folder_path = base / folder
        if not folder_path.exists():
            continue
        for f in folder_path.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("topic:"):
                    topics.add(line.split(":", 1)[1].strip())
                    break
    return topics


def get_next_task_id(folder: Path, suffix: str = "") -> str:
    today = date.today().strftime("%Y%m%d")
    existing = list(folder.glob(f"{today}_*.md"))
    seq = len(existing) + 1
    return f"{today}_{seq:03d}{suffix}"


def create_task(folder: Path, task_id: str, topic: str, series: str,
                priority: str, template: str, content_type: str,
                parts: int, outline: str, status: str = "planned") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    content = f"""---
task_id: {task_id}
status: {status}
topic: {topic}
series: {series}
priority: {priority}
template: {template}
type: {content_type}
parts: {parts}
created_by: planner_agent
created_at: {date.today().isoformat()}
---

# 콘텐츠 개요

{outline}
"""
    path = folder / f"{task_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ─────────────────────────────────────────────
# mbtireallove 전용 로직
# ─────────────────────────────────────────────

def mbti_suggest(paths: dict):
    print("=" * 50)
    print("Planner Agent — mbtireallove 주제 제안 모드")
    print("=" * 50)

    memory          = load_memory(paths["memory"])
    existing        = get_existing_topics("mbtireallove")
    planned_count   = len(list(paths["planned"].glob("*.md")))
    published_count = len(list(paths["published"].glob("*.md")))

    print(f"발행 완료: {published_count}개 | 대기 중: {planned_count}개")
    print("GPT에게 새 콘텐츠 기획 요청 중...")

    existing_sample = "\n".join(f"- {t}" for t in sorted(existing)[:30])
    prompt = f"""당신은 MBTI 블로그 편집국의 수석 기획자입니다.

## 현재 콘텐츠 현황
- 발행 완료: {published_count}개 | 대기 중: {planned_count}개

## 기존 주제 샘플 (이 패턴 반복 금지)
{existing_sample}
{"  ... (외 " + str(len(existing)-30) + "개 동일 패턴)" if len(existing) > 30 else ""}

## 편집 방침
{memory.get('decisions', '')}

---

기존과 다른 새로운 각도의 콘텐츠 5개를 기획해주세요.
기획 원칙:
1. 단순 MBTI 조합 반복 금지
2. 독자가 실제로 궁금해할 구체적인 상황/감정 기반 주제
3. 단편(1개 완결) 또는 시리즈 중 적합한 형태 선택

아래 JSON 배열 형식으로만 출력:
[
  {{
    "topic": "구체적인 주제명",
    "series": "시리즈명",
    "priority": "high/medium/low",
    "template": "default",
    "type": "단편 또는 시리즈",
    "parts": 1,
    "outline": "## 기획 의도\\n왜 이 주제인가\\n\\n## 구성안\\n- 1단락:\\n- 2단락:\\n- 3단락:\\n\\n## 핵심 포인트\\n독자가 얻어가야 할 것"
  }}
]"""

    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_completion_tokens=3000,
    )
    raw = resp.choices[0].message.content.strip()
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if not json_match:
        print(f"❌ JSON 추출 실패:\n{raw}")
        return

    suggestions = json.loads(json_match.group())
    today_str   = date.today().strftime("%Y%m%d")
    existing_s  = list(paths["suggestions"].glob(f"{today_str}_*.md"))

    for i, s in enumerate(suggestions, len(existing_s) + 1):
        task_id = f"{today_str}_{i:03d}s"
        create_task(
            folder       = paths["suggestions"],
            task_id      = task_id,
            topic        = s.get("topic", ""),
            series       = s.get("series", "mbti_relationship"),
            priority     = s.get("priority", "medium"),
            template     = s.get("template", "default"),
            content_type = s.get("type", "단편"),
            parts        = int(s.get("parts", 1)),
            outline      = s.get("outline", "").replace("\\n", "\n"),
            status       = "suggestion",
        )
        print(f"  💡 {s.get('topic', '')}")

    print(f"\n✅ {len(suggestions)}개 주제 제안 → blogs/mbtireallove/tasks/suggestions/")


def mbti_run(paths: dict):
    memory    = load_memory(paths["memory"])
    published = len(list(paths["published"].glob("*.md")))
    planned   = len(list(paths["planned"].glob("*.md")))

    print("=" * 50)
    print("Planner Agent — mbtireallove")
    print("=" * 50)
    print(f"발행 완료: {published}개 | 대기 중: {planned}개\n")

    # ── 편집장 승인 후 여기에 주제 추가 ──────────────────
    approved_tasks = [
        # {"topic": "ENFP 권태기", "series": "mbti_relationship", "priority": "high",
        #  "template": "default", "outline": "ENFP 권태기 주제 반응 테스트"},
    ]
    # ──────────────────────────────────────────────────────

    if not approved_tasks:
        print("⏸  승인된 Task 없음. tasks/suggestions/ 에서 AI 제안을 확인하세요.")
        return

    for task_data in approved_tasks:
        task_id = get_next_task_id(paths["planned"])
        create_task(
            folder       = paths["planned"],
            task_id      = task_id,
            content_type = task_data.pop("type", "단편"),
            parts        = task_data.pop("parts", 1),
            outline      = task_data.pop("outline", ""),
            **task_data,
        )
        print(f"  📋 Task 생성: {task_id} — {task_data['topic']}")

    print(f"\n✅ {len(approved_tasks)}개 Task 생성 완료")


# ─────────────────────────────────────────────
# llmenginehistory 전용 로직 (청약 분석)
# ─────────────────────────────────────────────

def fetch_cheongyak_list() -> list[dict]:
    """청약홈에서 서울/경기 청약 공고를 수집한다."""
    import requests
    from bs4 import BeautifulSoup

    results = []
    target_regions = {"서울", "경기"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.applyhome.co.kr/",
    }

    try:
        # 청약홈 진행 중 공고 목록 AJAX
        url  = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancList.do"
        data = {
            "orderBy":    "RCRIT_PBLANC_DE",
            "region":     "02",  # 전체 조회 후 필터링
            "houseSecd":  "01",  # APT
            "rentSecd":   "0",   # 분양
            "searchRangeYn": "N",
        }
        resp = requests.post(url, data=data, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")

        for row in rows:
            cols = row.select("td")
            if len(cols) < 6:
                continue

            region = cols[1].get_text(strip=True)
            if not any(r in region for r in target_regions):
                continue

            name          = cols[2].get_text(strip=True)
            rcrit_de      = cols[3].get_text(strip=True)  # 청약 접수일
            pblanc_url    = row.select_one("a")
            detail_url    = ("https://www.applyhome.co.kr" + pblanc_url["href"]
                             if pblanc_url and pblanc_url.get("href") else "")

            results.append({
                "name":      name,
                "region":    region,
                "rcrit_de":  rcrit_de,
                "detail_url": detail_url,
            })

    except Exception as e:
        print(f"  ⚠️  청약홈 스크래핑 오류: {e}")

    return results


def fetch_cheongyak_detail(detail_url: str) -> dict:
    """청약 공고 상세 페이지에서 핵심 정보를 추출한다."""
    if not detail_url:
        return {}

    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    detail  = {}

    try:
        resp = requests.get(detail_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 공급 규모 테이블에서 정보 추출
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("th, td")]
            if len(cols) >= 2:
                key = cols[0]
                val = cols[1]
                if "총" in key and "세대" in key:
                    detail["total_units"] = val
                if "분양가" in key:
                    detail["price"] = val
                if "입주" in key and "예정" in key:
                    detail["move_in"] = val

    except Exception as e:
        print(f"  ⚠️  상세 페이지 오류: {e}")

    return detail


def cheongyak_run(paths: dict):
    print("=" * 50)
    print("Planner Agent — llmenginehistory (청약 분석)")
    print("=" * 50)

    existing_topics = get_existing_topics("llmenginehistory")
    print("청약홈 서울/경기 공고 수집 중...")

    announcements = fetch_cheongyak_list()
    if not announcements:
        print("⚠️  수집된 공고 없음 (청약홈 응답 오류 또는 진행 중 청약 없음)")
        return

    print(f"  총 {len(announcements)}건 수집")

    created = 0
    for item in announcements:
        topic = f"{item['region']} {item['name']} 청약 분석"

        if topic in existing_topics:
            print(f"  스킵 (중복): {topic}")
            continue

        detail = fetch_cheongyak_detail(item.get("detail_url", ""))

        outline = f"""## 청약 공고 정보

- 단지명: {item['name']}
- 위치: {item['region']}
- 청약 접수일: {item['rcrit_de']}
- 총 세대수: {detail.get('total_units', '확인 필요')}
- 분양가: {detail.get('price', '확인 필요')}
- 입주 예정: {detail.get('move_in', '확인 필요')}
- 공고 링크: {item.get('detail_url', '')}

## 작성 방향

writing_guide.md의 청약 분석 구조에 따라 작성:
1. 단지 기본 정보 표
2. 청약 일정 정리
3. 입지 분석 (교통/학군/편의시설)
4. 분양가 vs 주변 시세 분석
5. 청약 자격 & 전략 요약
6. 한줄 총평 + 별점
"""

        task_id = get_next_task_id(paths["planned"])
        create_task(
            folder       = paths["planned"],
            task_id      = task_id,
            topic        = topic,
            series       = "청약분석",
            priority     = "high",
            template     = "default",
            content_type = "단편",
            parts        = 1,
            outline      = outline,
        )
        print(f"  📋 Task 생성: {task_id} — {topic}")
        created += 1

    if created == 0:
        print("새로 추가할 청약 공고 없음 (모두 기존 Task 존재)")
    else:
        print(f"\n✅ {created}개 청약 분석 Task 생성 완료")


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog",    required=True, help="블로그 이름")
    parser.add_argument("--suggest", action="store_true", help="AI 주제 제안 모드 (mbtireallove 전용)")
    args = parser.parse_args()

    paths = get_paths(args.blog)

    if args.blog == "mbtireallove":
        if args.suggest:
            mbti_suggest(paths)
        else:
            mbti_run(paths)
    elif args.blog == "llmenginehistory":
        cheongyak_run(paths)
    else:
        print(f"❌ 알 수 없는 블로그: {args.blog}")
        sys.exit(1)
