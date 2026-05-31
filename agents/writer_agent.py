"""
Writer Agent

역할: Task를 읽어 글 초안 생성
입력: tasks/planned/*.md, writing_guide.md
출력: articles/draft/{task_id}.html

작업 완료 시: tasks/planned/ → tasks/writing/ 이동
"""

import os
import re
import json
import shutil
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

TASKS_PLANNED  = Path("tasks/planned")
TASKS_WRITING  = Path("tasks/writing")
ARTICLES_DRAFT = Path("articles/draft")
WRITING_GUIDE  = Path("writing_guide.md")

azure_client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    timeout        = 60,
    max_retries    = 1,
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


def parse_task(task_file: Path) -> dict:
    """Task 파일의 frontmatter와 본문을 파싱한다."""
    content = task_file.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not match:
        return {}

    meta, body = match.group(1), match.group(2).strip()
    parsed = {}
    for line in meta.strip().splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            parsed[k.strip()] = v.strip()
    parsed["_body"] = body
    return parsed


def get_next_task() -> Path | None:
    """planned/ 에서 priority → 파일명 순으로 다음 Task를 선택한다."""
    tasks = sorted(TASKS_PLANNED.glob("*.md"))
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda p: priority_order.get(
        parse_task(p).get("priority", "medium"), 1
    ))
    return tasks[0] if tasks else None


def load_template(template_name: str) -> str:
    """템플릿 파일이 있으면 로드, 없으면 기본 writing_guide.md 사용."""
    template_path = Path(f"templates/{template_name}.md")
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    if WRITING_GUIDE.exists():
        return WRITING_GUIDE.read_text(encoding="utf-8")
    return ""


def generate_content(task: dict) -> tuple[str, str]:
    topic    = task.get("topic", "")
    series   = task.get("series", "")
    template = task.get("template", "default")
    body     = task.get("_body", "")
    guide    = load_template(template)

    system_prompt = (
        "당신은 블로그 전문 작가입니다.\n"
        "아래 작성 가이드를 반드시 따라 HTML 형식으로만 출력합니다.\n\n"
        f"{guide}"
    )

    user_prompt = f"""다음 주제로 블로그 글을 작성해주세요.

주제: {topic}
시리즈: {series}

기획 의도:
{body}

맨 첫 줄에 반드시 부제목을 넣어주세요:
<!-- SUBTITLE: [부제목] -->

이후 HTML 본문을 가이드의 섹션 순서대로 작성해주세요.
각 섹션은 3~5문장, 핵심만 임팩트 있게."""

    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.8,
        max_completion_tokens=3000,
        timeout=60,
    )
    raw = resp.choices[0].message.content.strip()

    m        = re.search(r"<!--\s*SUBTITLE:\s*(.+?)\s*-->", raw)
    subtitle = m.group(1) if m else topic
    html     = re.sub(r"<!--\s*SUBTITLE:\s*.+?\s*-->\n?", "", raw)
    title    = f"💘 {topic} – {subtitle}"

    return title, html


def run():
    print("=" * 50)
    print("Writer Agent")
    print("=" * 50)

    task_file = get_next_task()
    if not task_file:
        print("처리할 Task 없음 (tasks/planned/ 가 비어있음)")
        return

    task    = parse_task(task_file)
    task_id = task.get("task_id", task_file.stem)
    topic   = task.get("topic", "")

    print(f"Task: {task_id} — {topic}")

    # 글 생성
    print("  글 생성 중...")
    title, html = generate_content(task)
    print(f"  제목: {title}")

    # 초안 저장
    draft_path = ARTICLES_DRAFT / f"{task_id}.html"
    draft_path.write_text(
        f"<!-- TITLE: {title} -->\n{html}",
        encoding="utf-8",
    )
    print(f"  초안 저장: {draft_path}")

    # Task 이동: planned → writing
    writing_path = TASKS_WRITING / task_file.name
    shutil.move(str(task_file), str(writing_path))
    print(f"  Task 이동: planned/ → writing/")

    print(f"\n✅ 완료: {task_id}")


if __name__ == "__main__":
    run()
