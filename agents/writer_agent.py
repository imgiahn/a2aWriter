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


CATEGORY_FOCUS = {
    "national_rental": "월임대료·보증금 수준, 소득 기준 핵심, 예비입주자 특성(대기 개념)",
    "permanent_rental": "극저소득층 대상, 소득·자산 기준이 핵심, 입주 조건 엄격",
    "happy_housing": "청년·신혼부부 특화, 거주기간 제한, 소득 기준, 면적 제한",
    "jeonse":        "든든전세·매입임대 특성, 전세금 수준, 일반 전세 대비 차이점",
    "public_rental_10y": "10년 공공임대 특성, 분양전환 여부, 리츠 구조면 언급",
    "integrated_public_rental": "통합공공임대 특성, 소득 구간별 임대료 차등, 유형 전환 가능성",
    "purchase_rental": "분양전환 일정, 전환 가격 산정 방식, 실질 내 집 마련 가능성",
    "sale":           "분양가, 청약 자격, 가점·추첨 비율, 계약 일정",
    "general":        "공고 핵심 조건, 신청 자격, 일정",
}


def _load_category_guide(blog: str, category: str) -> str:
    guide_path = Path(f"blogs/{blog}/guides/{category}.md")
    if guide_path.exists():
        return guide_path.read_text(encoding="utf-8")
    # 공통 가이드로 폴백
    common = Path(f"blogs/{blog}/writing_guide.md")
    return common.read_text(encoding="utf-8") if common.exists() else ""


def generate_lh_content(task: dict, writing_guide: Path) -> tuple:
    """LH 청약 공고 해설 콘텐츠를 생성한다 (task 데이터만 사용)."""
    notice_name  = task.get("notice_name", task.get("topic", ""))
    supply_type  = task.get("supply_type", "")
    category     = task.get("template", "general")   # housing_category
    region       = task.get("region", "")
    notice_date  = task.get("notice_date", "")
    deadline     = task.get("deadline", "")
    notice_id    = task.get("notice_id", "")
    detail_url   = task.get("detail_url", "")

    # task에서 추출된 구조화 데이터
    total_units  = task.get("total_units", "")
    apply_start  = task.get("apply_start", "")
    apply_end    = task.get("apply_end", "") or deadline
    result_date  = task.get("result_date", "")
    move_in      = task.get("move_in", "")
    supply_target = task.get("supply_target", "")
    qualifications = task.get("qualifications", "")
    deposit      = task.get("deposit", "")
    monthly_rent = task.get("monthly_rent", "")
    jeonse_amount = task.get("jeonse_amount", "")
    house_types  = task.get("house_types", "")
    first_supply = task.get("first_supply", "")
    conversion   = task.get("conversion", "")
    location_detail = task.get("location_detail", "")

    blog_name = "llmenginehistory"
    guide = _load_category_guide(blog_name, category)
    focus = CATEGORY_FOCUS.get(category, CATEGORY_FOCUS["general"])

    system_prompt = (
        "당신은 청약 정보를 전문적으로 해설하는 블로그 작가입니다.\n"
        "독자는 청약에 관심 있는 사람으로, LH·청약·국민임대 등 기본 개념은 알고 있습니다.\n"
        "기본 개념 설명 없이 이번 공고에만 집중해서 작성하세요.\n\n"
        "절대 금지 표현:\n"
        "- '공고문을 확인하세요', '알아보겠습니다', '살펴보겠습니다'\n"
        "- LH가 무엇인지, 청약이 무엇인지, 국민임대가 무엇인지 설명\n\n"
        "반드시 포함:\n"
        "- '누가 보면 좋은 공고인지' 명확하게 작성\n"
        f"- 이 공고 유형({supply_type})의 핵심 포인트: {focus}\n\n"
        "작성 가이드:\n"
        f"{guide}"
    )

    # 필드 요약 (없는 항목은 생략)
    fields_summary = []
    if total_units:   fields_summary.append(f"총 세대수: {total_units}")
    if apply_start:   fields_summary.append(f"신청 시작: {apply_start}")
    if apply_end:     fields_summary.append(f"신청 마감: {apply_end}")
    if result_date:   fields_summary.append(f"당첨 발표: {result_date}")
    if move_in:       fields_summary.append(f"입주 예정: {move_in}")
    if supply_target: fields_summary.append(f"공급 대상: {supply_target}")
    if qualifications:fields_summary.append(f"신청 자격: {qualifications}")
    if deposit:       fields_summary.append(f"보증금: {deposit}")
    if monthly_rent:  fields_summary.append(f"월 임대료: {monthly_rent}")
    if jeonse_amount: fields_summary.append(f"전세금: {jeonse_amount}")
    if house_types:   fields_summary.append(f"주택형: {house_types}")
    if first_supply:  fields_summary.append(f"우선공급: {first_supply}")
    if conversion:    fields_summary.append(f"분양전환: {conversion}")
    if location_detail: fields_summary.append(f"위치: {location_detail}")

    user_prompt = f"""다음 LH 청약 공고를 해설하는 블로그 글을 HTML로 작성해주세요.

## 공고 정보
- 공고명: {notice_name}
- 공급유형: {supply_type} (카테고리: {category})
- 지역: {region}
- 공고일: {notice_date}
- 공고번호: {notice_id}
- 원문: {detail_url}

## 추출된 공고 데이터
{chr(10).join(fields_summary) if fields_summary else "데이터 추출 미완료 — 공고명과 지역 기반으로 작성"}

---

맨 첫 줄에 부제목:
<!-- SUBTITLE: [이 공고의 핵심을 한 줄로] -->

이후 가이드 구조대로 HTML 본문 작성.
데이터가 없는 항목은 억측하지 말고 해당 항목을 자연스럽게 생략.
반드시 마지막에 "이런 분께 추천" 문단 포함."""

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
