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
# llmenginehistory 전용 로직 (LH 청약 공고 해설)
# ─────────────────────────────────────────────

SUPPLY_TO_CATEGORY = {
    "국민임대":       "national_rental",
    "영구임대":       "permanent_rental",
    "행복주택":       "happy_housing",
    "매입임대":       "jeonse",
    "든든전세":       "jeonse",
    "공공임대":       "public_rental_10y",
    "통합공공임대":   "integrated_public_rental",
    "분양전환":       "purchase_rental",
    "공공분양":       "sale",
    "분양주택":       "sale",
}


def get_housing_category(supply_type: str) -> str:
    for key, cat in SUPPLY_TO_CATEGORY.items():
        if key in supply_type:
            return cat
    return "general"


def extract_notice_fields(detail_text: str, supply_type: str) -> dict:
    """공고 상세 텍스트에서 구조화 데이터를 GPT로 추출한다."""
    if not detail_text:
        return {}

    prompt = f"""아래 LH 청약 공고 텍스트에서 정보를 추출하세요.
정보가 없으면 빈 문자열로 두세요. JSON만 출력하세요.

공급유형: {supply_type}

공고 텍스트:
{detail_text[:4000]}

{{
  "total_units": "총 공급세대수 (예: 50세대)",
  "apply_start": "신청 시작일 YYYY.MM.DD",
  "apply_end": "신청 마감일 YYYY.MM.DD",
  "result_date": "당첨자 발표일 YYYY.MM.DD",
  "move_in": "입주 예정일",
  "supply_target": "공급 대상 (예: 무주택세대구성원)",
  "qualifications": "신청 자격 핵심 요약 (3줄 이내)",
  "deposit": "보증금 (임대의 경우)",
  "monthly_rent": "월 임대료",
  "jeonse_amount": "전세금 (전세형의 경우)",
  "house_types": "주택형/면적 (예: 36㎡, 46㎡, 59㎡)",
  "priority": "우선공급 조건 요약",
  "conversion": "분양전환 여부 (예: 10년 후 분양전환 가능, 해당없음)",
  "location_detail": "단지 위치 상세 주소"
}}"""

    try:
        resp = azure_client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        import json as _json, re as _re
        m = _re.search(r"\{[\s\S]*\}", raw)
        if m:
            return _json.loads(m.group())
    except Exception as e:
        print(f"  ⚠️  필드 추출 오류: {e}")
    return {}


def get_existing_notice_ids(blog: str) -> set:
    ids = set()
    base = Path(f"blogs/{blog}/tasks")
    for folder in ["planned", "writing", "published", "failed"]:
        for f in (base / folder).glob("*.md"):
            text = f.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("notice_id:"):
                    ids.add(line.split(":", 1)[1].strip())
                    break
    return ids


def cheongyak_run(paths: dict):
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.lh_scraper import scrape, fetch_detail

    print("=" * 50)
    print("Planner Agent — llmenginehistory (LH 청약 공고)")
    print("=" * 50)

    existing_ids = get_existing_notice_ids("llmenginehistory")
    print(f"기존 처리 공고: {len(existing_ids)}건")
    print("LH 청약플러스 서울/경기 공고 수집 중...")

    announcements = scrape()
    if not announcements:
        print("⚠️  수집된 공고 없음")
        return

    print(f"수집: {len(announcements)}건")

    created = 0
    for item in announcements:
        notice_id   = item.get("notice_id", "")
        notice_name = item.get("notice_name", "")
        supply_type = item.get("supply_type", "")
        region      = item.get("region", "")
        notice_date = item.get("notice_date", "")
        detail_url  = item.get("detail_url", "")

        if not notice_name or not detail_url:
            continue

        dedup_key = notice_id or notice_name
        if dedup_key in existing_ids:
            print(f"  스킵 (중복): {notice_name}")
            continue

        # 상세 페이지 크롤링 + 구조화 추출
        print(f"  상세 수집 중: {notice_name[:30]}...")
        detail_text = fetch_detail(detail_url)
        fields      = extract_notice_fields(detail_text, supply_type)
        category    = get_housing_category(supply_type)

        task_id = get_next_task_id(paths["planned"])
        folder  = paths["planned"]
        folder.mkdir(parents=True, exist_ok=True)

        content = f"""---
task_id: {task_id}
status: planned
topic: {notice_name} 공고 해설
series: 청약공고해설
priority: high
template: {category}
type: 단편
parts: 1
notice_id: {notice_id}
notice_name: {notice_name}
supply_type: {supply_type}
housing_category: {category}
region: {region}
notice_date: {notice_date}
deadline: {item.get('deadline', '')}
detail_url: {detail_url}
total_units: {fields.get('total_units', '')}
apply_start: {fields.get('apply_start', '')}
apply_end: {fields.get('apply_end', '')}
result_date: {fields.get('result_date', '')}
move_in: {fields.get('move_in', '')}
supply_target: {fields.get('supply_target', '')}
deposit: {fields.get('deposit', '')}
monthly_rent: {fields.get('monthly_rent', '')}
jeonse_amount: {fields.get('jeonse_amount', '')}
house_types: {fields.get('house_types', '')}
priority: {fields.get('priority', '')}
conversion: {fields.get('conversion', '')}
location_detail: {fields.get('location_detail', '')}
qualifications: |
  {fields.get('qualifications', '').replace(chr(10), chr(10) + '  ')}
created_by: planner_agent
created_at: {date.today().isoformat()}
---
"""
        (folder / f"{task_id}.md").write_text(content, encoding="utf-8")
        print(f"  📋 Task 생성: {task_id} — [{category}] {notice_name[:30]}")
        created += 1

    if created == 0:
        print("새 공고 없음 (모두 기존 Task 존재)")
    else:
        print(f"\n✅ {created}개 Task 생성 완료")


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
