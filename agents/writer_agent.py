"""
Writer Agent

역할: Task를 읽어 글 초안 생성
입력: blogs/{blog}/tasks/planned/*.md, blogs/{blog}/writing_guide.md
출력: articles/{blog}/draft/{task_id}.html

실행: python agents/writer_agent.py --blog mbtireallove
      python agents/writer_agent.py --blog llmenginehistory
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import date
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
        "tasks_planned":  base / "tasks/planned",
        "tasks_writing":  base / "tasks/writing",
        "articles_draft": Path(f"articles/{blog}/draft"),
        "writing_guide":  base / "writing_guide.md",
    }


def parse_task(task_file: Path) -> dict:
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


def get_next_task(tasks_planned: Path) -> Optional[Path]:
    tasks = sorted(tasks_planned.glob("*.md"))
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda p: priority_order.get(parse_task(p).get("priority", "medium"), 1))
    return tasks[0] if tasks else None


def fetch_lh_detail_text(url: str) -> str:
    """LH 공고 상세 페이지 텍스트를 Playwright로 추출한다."""
    if not url:
        return ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            page.goto(url, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 본문 영역 우선 추출
            for selector in [".view_wrap", ".detail_wrap", ".cont_wrap", "#content", "main"]:
                el = page.query_selector(selector)
                if el:
                    text = el.inner_text()
                    if len(text) > 200:
                        browser.close()
                        return text.strip()[:5000]

            text = page.inner_text("body").strip()[:5000]
            browser.close()
            return text
    except Exception as e:
        print(f"  ⚠️  상세 페이지 로드 실패: {e}")
        return ""


def generate_lh_content(task: dict, writing_guide: Path) -> tuple:
    """LH 청약 공고 해설 콘텐츠를 생성한다."""
    notice_name = task.get("notice_name", task.get("topic", ""))
    supply_type = task.get("supply_type", "")
    region      = task.get("region", "")
    notice_date = task.get("notice_date", "")
    notice_id   = task.get("notice_id", "")
    detail_url  = task.get("detail_url", "")
    guide       = writing_guide.read_text(encoding="utf-8") if writing_guide.exists() else ""

    print(f"  상세 페이지 수집 중: {detail_url}")
    detail_text = fetch_lh_detail_text(detail_url)

    system_prompt = (
        "당신은 부동산/청약 정보를 쉽게 설명해주는 블로그 작가입니다.\n"
        "아래 작성 가이드를 반드시 따라 HTML 형식으로만 출력합니다.\n\n"
        f"{guide}"
    )

    user_prompt = f"""아래 LH 청약 공고를 독자가 쉽게 이해할 수 있도록 해설하는 블로그 글을 작성해주세요.

## 공고 기본 정보
- 공고명: {notice_name}
- 공고번호: {notice_id}
- 공급유형: {supply_type}
- 지역: {region}
- 공고일: {notice_date}
- 출처: {detail_url}

## 공고 상세 내용 (원문)
{detail_text if detail_text else "상세 내용을 가져오지 못했습니다. 공고 기본 정보만으로 작성해주세요."}

---

맨 첫 줄에 부제목을 넣어주세요:
<!-- SUBTITLE: [부제목] -->

이후 writing_guide의 구조대로 HTML 본문을 작성해주세요.
투자 분석, 분양가 평가 등 고급 분석은 하지 말고
"이 공고가 무슨 내용인지" 해설에만 집중해주세요."""

    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=3000,
        timeout=90,
    )
    raw = resp.choices[0].message.content.strip()

    m        = re.search(r"<!--\s*SUBTITLE:\s*(.+?)\s*-->", raw)
    subtitle = m.group(1) if m else notice_name
    html     = re.sub(r"<!--\s*SUBTITLE:\s*.+?\s*-->\n?", "", raw)
    title    = f"🏠 {notice_name} — {subtitle}"

    return title, html


def generate_content(task: dict, writing_guide: Path) -> tuple:
    topic    = task.get("topic", "")
    series   = task.get("series", "")
    body     = task.get("_body", "")
    guide    = writing_guide.read_text(encoding="utf-8") if writing_guide.exists() else ""
    prefix   = task.get("title_prefix", "")

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
    title    = f"{prefix} {topic} – {subtitle}".strip() if prefix else f"{topic} – {subtitle}"

    return title, html


def run(blog: str):
    print("=" * 50)
    print(f"Writer Agent — {blog}")
    print("=" * 50)

    paths = get_paths(blog)
    paths["articles_draft"].mkdir(parents=True, exist_ok=True)
    paths["tasks_writing"].mkdir(parents=True, exist_ok=True)

    task_file = get_next_task(paths["tasks_planned"])
    if not task_file:
        print(f"처리할 Task 없음 ({paths['tasks_planned']})")
        return

    task    = parse_task(task_file)
    task_id = task.get("task_id", task_file.stem)
    topic   = task.get("topic", "")

    print(f"Task: {task_id} — {topic}")
    print("  글 생성 중...")

    # 블로그별 글 생성 분기
    if blog == "llmenginehistory":
        title, html = generate_lh_content(task, paths["writing_guide"])
    else:
        title, html = generate_content(task, paths["writing_guide"])

    print(f"  제목: {title}")

    draft_path = paths["articles_draft"] / f"{task_id}.html"
    draft_path.write_text(f"<!-- TITLE: {title} -->\n{html}", encoding="utf-8")
    print(f"  초안 저장: {draft_path}")

    writing_path = paths["tasks_writing"] / task_file.name
    shutil.move(str(task_file), str(writing_path))
    print(f"  Task 이동: planned/ → writing/")

    print(f"\n✅ 완료: {task_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", required=True, help="블로그 이름 (blogs/ 하위 폴더명)")
    args = parser.parse_args()
    run(args.blog)
