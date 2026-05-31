"""
Planner Agent

역할: 콘텐츠 기획 및 Task 생성
입력: memory/*.md, posted_combos.json, daily_log.json
출력: tasks/planned/YYYYMMDD_NNN.md

절대 원칙:
- 글을 생성하지 않는다
- 편집장(사람)이 승인한 시리즈만 Task로 만든다
- decisions.md에 없는 시리즈는 제안만 하고 생성하지 않는다
"""

import os
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MEMORY_DIR    = Path("memory")
TASKS_PLANNED = Path("tasks/planned")


def load_memory() -> dict:
    return {
        "history":   (MEMORY_DIR / "history.md").read_text(encoding="utf-8"),
        "decisions": (MEMORY_DIR / "decisions.md").read_text(encoding="utf-8"),
        "metrics":   (MEMORY_DIR / "metrics.md").read_text(encoding="utf-8"),
    }


def load_posted_combos() -> list:
    f = Path("posted_combos.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def get_next_task_id() -> str:
    today = date.today().strftime("%Y%m%d")
    existing = list(TASKS_PLANNED.glob(f"{today}_*.md"))
    seq = len(existing) + 1
    return f"{today}_{seq:03d}"


def create_task(task_id: str, topic: str, series: str, priority: str,
                template: str, intention: str):
    """승인된 Task를 파일로 저장한다."""
    today = date.today().isoformat()
    content = f"""---
task_id: {task_id}
status: planned
topic: {topic}
series: {series}
priority: {priority}
template: {template}
created_by: planner_agent
created_at: {today}
---

# 기획 의도

{intention}
"""
    path = TASKS_PLANNED / f"{task_id}.md"
    path.write_text(content, encoding="utf-8")
    print(f"  📋 Task 생성: {path.name} — {topic}")


def run():
    """
    TODO: 트렌드 분석 기반 자동 기획 (편집장과 회의 후 구현)

    현재는 수동 호출 전용.
    편집장이 승인한 주제 목록을 아래에 직접 입력하면 Task를 생성한다.
    """
    memory = load_memory()
    posted = load_posted_combos()

    print("=" * 50)
    print("Planner Agent")
    print("=" * 50)
    print(f"발행 완료: {len(posted)}개")
    print()

    # ── 편집장 승인 후 여기에 주제 추가 ──────────────────
    approved_tasks = [
        # {"topic": "ENFP 권태기", "series": "mbti_relationship", "priority": "high",
        #  "template": "relationship_v1", "intention": "ENFP 권태기 주제 반응 테스트"},
    ]
    # ──────────────────────────────────────────────────────

    if not approved_tasks:
        print("⏸  승인된 Task 없음. decisions.md를 확인하거나 편집장과 회의하세요.")
        return

    for task_data in approved_tasks:
        task_id = get_next_task_id()
        create_task(task_id=task_id, **task_data)

    print(f"\n✅ {len(approved_tasks)}개 Task 생성 완료")


if __name__ == "__main__":
    run()
