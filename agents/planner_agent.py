"""
Planner Agent

역할: 콘텐츠 기획 및 Task 생성
입력: memory/*.md
출력: tasks/planned/YYYYMMDD_NNN.md  (run 모드)
      tasks/suggestions/YYYYMMDD_NNNs.md (--suggest 모드)

절대 원칙:
- 글을 생성하지 않는다
- 편집장(사람)이 승인한 시리즈만 Task로 만든다
- decisions.md에 없는 시리즈는 제안만 하고 생성하지 않는다
"""

import os
import re
import sys
import json
from datetime import date
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

MEMORY_DIR        = Path("memory")
TASKS_PLANNED     = Path("tasks/planned")
TASKS_SUGGESTIONS = Path("tasks/suggestions")

azure_client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    timeout        = 60,
    max_retries    = 1,
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


def load_memory() -> dict:
    result = {}
    for key in ("history", "decisions", "metrics"):
        path = MEMORY_DIR / f"{key}.md"
        result[key] = path.read_text(encoding="utf-8") if path.exists() else ""
    return result


def get_existing_topics() -> set:
    """이미 기획/발행된 주제 목록 (중복 방지용)."""
    topics = set()
    for folder in ["planned", "writing", "published", "failed", "suggestions"]:
        folder_path = Path(f"tasks/{folder}")
        if not folder_path.exists():
            continue
        for f in folder_path.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("topic:"):
                    topics.add(line.split(":", 1)[1].strip())
                    break
    return topics


def count_published() -> int:
    return len(list(Path("tasks/published").glob("*.md")))


def get_next_task_id(folder: Optional[Path] = None) -> str:
    folder = folder or TASKS_PLANNED
    today = date.today().strftime("%Y%m%d")
    existing = list(folder.glob(f"{today}_*.md"))
    seq = len(existing) + 1
    return f"{today}_{seq:03d}"


def create_task(task_id: str, topic: str, series: str, priority: str,
                template: str, intention: str, status: str = "planned",
                folder: Optional[Path] = None):
    folder = folder or TASKS_PLANNED
    folder.mkdir(exist_ok=True)
    content = f"""---
task_id: {task_id}
status: {status}
topic: {topic}
series: {series}
priority: {priority}
template: {template}
created_by: planner_agent
created_at: {date.today().isoformat()}
---

# 기획 의도

{intention}
"""
    path = folder / f"{task_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def suggest():
    """AI가 새 주제를 제안하고 tasks/suggestions/ 에 저장한다."""
    print("=" * 50)
    print("Planner Agent — 주제 제안 모드")
    print("=" * 50)

    memory   = load_memory()
    existing = get_existing_topics()
    planned_count   = len(list(TASKS_PLANNED.glob("*.md")))
    published_count = count_published()

    print(f"발행 완료: {published_count}개 | 대기 중: {planned_count}개")
    print(f"기존 주제 {len(existing)}개 제외하고 새 주제 제안 요청 중...")

    existing_list = "\n".join(f"- {t}" for t in sorted(existing)[:60])
    if len(existing) > 60:
        existing_list += f"\n- ... 외 {len(existing)-60}개"

    prompt = f"""당신은 MBTI 블로그 편집국의 AI 기획자입니다.

현재 운영 현황:
- 발행 완료: {published_count}개
- 대기 중: {planned_count}개

편집 방침 (decisions.md):
{memory.get('decisions', '')}

이미 기획/발행된 주제 (중복 금지):
{existing_list}

위 내용을 바탕으로 블로그에 새롭게 추가할 주제 15개를 제안해주세요.
기존 mbti_relationship 시리즈의 새 조합이나 완전히 새로운 시리즈 모두 환영합니다.

아래 JSON 배열 형식으로만 출력하세요 (다른 텍스트 없이):
[
  {{
    "topic": "주제명",
    "series": "시리즈명",
    "priority": "high 또는 medium 또는 low",
    "template": "relationship_v1",
    "intention": "기획 의도 1-2문장"
  }}
]"""

    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_completion_tokens=2000,
    )
    raw = resp.choices[0].message.content.strip()

    json_match = re.search(r"\[[\s\S]*\]", raw)
    if not json_match:
        print(f"❌ JSON 추출 실패:\n{raw}")
        return

    suggestions = json.loads(json_match.group())
    TASKS_SUGGESTIONS.mkdir(exist_ok=True)
    today_str = date.today().strftime("%Y%m%d")
    existing_sugg = list(TASKS_SUGGESTIONS.glob(f"{today_str}_*.md"))

    saved = 0
    for i, s in enumerate(suggestions, len(existing_sugg) + 1):
        task_id = f"{today_str}_{i:03d}s"
        path = create_task(
            task_id  = task_id,
            topic    = s.get("topic", ""),
            series   = s.get("series", "mbti_relationship"),
            priority = s.get("priority", "medium"),
            template = s.get("template", "relationship_v1"),
            intention= s.get("intention", ""),
            status   = "suggestion",
            folder   = TASKS_SUGGESTIONS,
        )
        print(f"  💡 {s.get('topic', '')}")
        saved += 1

    print(f"\n✅ {saved}개 주제 제안 완료 → tasks/suggestions/")


def run():
    memory    = load_memory()
    published = count_published()
    planned   = len(list(TASKS_PLANNED.glob("*.md")))

    print("=" * 50)
    print("Planner Agent")
    print("=" * 50)
    print(f"발행 완료: {published}개 | 대기 중: {planned}개")
    print()

    # ── 편집장 승인 후 여기에 주제 추가 ──────────────────
    approved_tasks = [
        # {"topic": "ENFP 권태기", "series": "mbti_relationship", "priority": "high",
        #  "template": "relationship_v1", "intention": "ENFP 권태기 주제 반응 테스트"},
    ]
    # ──────────────────────────────────────────────────────

    if not approved_tasks:
        print("⏸  승인된 Task 없음. 대시보드에서 AI 제안을 승인하거나 편집장과 회의하세요.")
        return

    for task_data in approved_tasks:
        task_id = get_next_task_id()
        create_task(task_id=task_id, **task_data)
        print(f"  📋 Task 생성: {task_id} — {task_data['topic']}")

    print(f"\n✅ {len(approved_tasks)}개 Task 생성 완료")


if __name__ == "__main__":
    if "--suggest" in sys.argv:
        suggest()
    else:
        run()
