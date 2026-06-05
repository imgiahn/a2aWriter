"""
PDF Reader Agent

역할: planned task의 공고 PDF에서 핵심 정보를 구조화 추출 → enriched task 생성
실행:
  python agents/pdf_reader_agent.py --blog llmenginehistory
  python agents/pdf_reader_agent.py --blog llmenginehistory --task-id 20260605_001
  python agents/pdf_reader_agent.py --blog llmenginehistory --dry-run
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

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

azure_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    timeout=120,
    max_retries=1,
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

# 섹션별 탐색 키워드
KEYWORD_GROUPS = {
    "price": [
        "공급금액", "분양가", "계약금", "중도금", "잔금",
        "납부일정", "공급가격", "납부방법", "공급대금",
    ],
    "schedule": [
        "신청기간", "접수기간", "접수일", "당첨자발표", "당첨자 발표",
        "계약일", "계약기간", "입주예정", "입주지정", "모집공고일",
    ],
    "qualification": [
        "신청자격", "무주택", "신혼부부", "한부모", "자격기준",
        "청약자격", "예비신혼", "공급대상",
    ],
    "income_asset": [
        "월평균소득", "도시근로자", "소득기준", "소득 기준",
        "총자산", "자산기준", "자산가액", "자동차가액",
    ],
}

# LLM 추출 프롬프트 (섹션별)
_PROMPTS = {
    "prices": """\
아래 LH 청약 공고 텍스트에서 공급금액 정보를 추출하세요.
PDF에서 확인된 값만 넣고, 없으면 null로 두세요. JSON만 출력하세요.

{
  "summary": {
    "min_sale_price": null,
    "max_sale_price": null
  },
  "by_type": [
    {"type": null, "area_sqm": null, "price_krw": null}
  ],
  "contract": {"note": null},
  "interim": {"note": null},
  "balance": {"note": null}
}""",

    "schedule": """\
아래 LH 청약 공고 텍스트에서 청약 일정을 추출하세요.
날짜 형식은 YYYY.MM.DD로 통일하세요. 없으면 null로 두세요. JSON만 출력하세요.

{
  "apply_start": null,
  "apply_end": null,
  "winner_date": null,
  "contract_start": null,
  "contract_end": null,
  "move_in": null
}""",

    "qualification": """\
아래 LH 청약 공고 텍스트에서 신청 자격과 소득/자산 기준을 추출하세요.
PDF에서 확인된 값만 넣고, 없으면 null로 두세요. JSON만 출력하세요.

{
  "target_groups": [],
  "no_home_required": null,
  "region_priority": null,
  "income_limit": {
    "single_income_pct": null,
    "dual_income_pct": null,
    "birth_benefit_1child_pct_add": null,
    "birth_benefit_2plus_pct_add": null
  },
  "asset_limit": {
    "total_asset_krw": null,
    "car_value_krw": null,
    "birth_1child_krw": null,
    "birth_2plus_krw": null
  },
  "restriction_rewin_years": null,
  "restriction_resale_years": null,
  "obligation_residence_years": null
}""",

    "decision_points": """\
아래 LH 청약 공고 데이터를 바탕으로 청약 신청자가 꼭 알아야 할 핵심 판단 포인트 3~5개를 추출하세요.
중요한 제한, 자격 조건, 가격 매력도, 일정 등을 간결한 문장으로 정리하세요.
추정하지 말고 데이터에서 확인된 내용만 포함하세요. JSON 배열만 출력하세요.

["포인트1", "포인트2", ...]""",
}


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────

def _get_paths(blog: str) -> dict:
    base = Path(f"blogs/{blog}")
    return {
        "planned":  base / "tasks/planned",
        "enriched": base / "tasks/enriched",
        "data":     Path(f"data/{blog}/notices"),
    }


def _parse_frontmatter(text: str) -> tuple:
    """frontmatter(dict)와 body(str)를 분리한다."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    meta_text, body = m.group(1), m.group(2).strip()
    meta = {}
    current_key = None
    for line in meta_text.splitlines():
        if line.startswith("  ") and current_key:
            meta[current_key] = meta[current_key] + "\n" + line.strip()
        elif ": " in line and not line.startswith(" "):
            k, v = line.split(": ", 1)
            current_key = k.strip()
            meta[current_key] = v.strip()
        elif line.endswith(": |") and not line.startswith(" "):
            current_key = line[:-3].strip()
            meta[current_key] = ""
    return meta, body


def _find_pdf_path(task: dict, blog: str) -> Optional[Path]:
    """저장된 PDF 파일 경로를 찾는다."""
    # 1. task의 pdf_path 필드
    if task.get("pdf_path"):
        p = Path(task["pdf_path"])
        if p.exists():
            return p

    # 2. data/ 디렉토리 기본 위치
    notice_id = task.get("notice_id", "")
    if notice_id:
        p = Path(f"data/{blog}/notices/{notice_id}/original.pdf")
        if p.exists():
            return p

    return None


def _classify_pages(pages: list) -> dict:
    """페이지 목록에서 섹션별 페이지 번호 목록을 반환한다."""
    result = {k: [] for k in KEYWORD_GROUPS}
    for p in pages:
        text = p["text"]
        for group, keywords in KEYWORD_GROUPS.items():
            if any(kw in text for kw in keywords):
                result[group].append(p["page_num"])
    return result


def _combine_pages(pages: list, page_nums: list, max_chars: int = 8000) -> str:
    """지정 페이지 번호의 텍스트를 합친다."""
    parts = []
    for p in pages:
        if p["page_num"] in page_nums:
            parts.append(f"[{p['page_num']}페이지]\n{p['text']}")
    return "\n\n".join(parts)[:max_chars]


def _save_page_artifacts(notice_id: str, blog: str, pages: list):
    """페이지별 텍스트를 data/ 폴더에 저장한다."""
    base = Path(f"data/{blog}/notices/{notice_id}/pages")
    base.mkdir(parents=True, exist_ok=True)
    for p in pages:
        (base / f"page_{p['page_num']:03d}.txt").write_text(p["text"], encoding="utf-8")


def _llm_extract(section: str, context: str) -> object:
    """LLM으로 섹션별 구조화 추출을 수행한다."""
    if not context.strip():
        return {} if section != "decision_points" else []

    prompt = _PROMPTS[section] + f"\n\n공고 텍스트:\n{context}"
    try:
        resp = azure_client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=1200,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"    ⚠️  {section} 추출 실패: {e}")
        return {} if section != "decision_points" else []


def _calc_confidence(page_groups: dict, warnings: list) -> str:
    found = sum(1 for v in page_groups.values() if v)
    if found >= 3 and not warnings:
        return "high"
    if found >= 2:
        return "medium"
    return "low"


def _build_enriched_content(meta: dict, original_body: str,
                             page_groups: dict, extracted: dict,
                             confidence: str, warnings: list) -> str:
    """enriched task 파일 내용(문자열)을 생성한다."""

    # ── frontmatter ──────────────────────────────────────────
    lines = []
    for k, v in meta.items():
        sv = str(v)
        if "\n" in sv:
            lines.append(f"{k}: |")
            for l in sv.splitlines():
                lines.append(f"  {l}")
        else:
            lines.append(f"{k}: {sv}")

    # status 변경 + enriched 메타
    for i, l in enumerate(lines):
        if l.startswith("status: "):
            lines[i] = "status: enriched"
    lines.append(f"enriched_by: pdf_reader_agent")
    lines.append(f"enriched_at: {date.today().isoformat()}")
    lines.append(f"pdf_status: {'ok' if extracted else 'no_pdf'}")
    lines.append(f"pdf_confidence: {confidence}")

    frontmatter = "---\n" + "\n".join(lines) + "\n---\n\n"

    # ── JSON 섹션 ─────────────────────────────────────────────
    sections = []

    pdf_meta = {
        "status":               "ok" if extracted else "no_pdf",
        "price_pages":          page_groups.get("price", []),
        "schedule_pages":       page_groups.get("schedule", []),
        "qualification_pages":  page_groups.get("qualification", []),
        "income_asset_pages":   page_groups.get("income_asset", []),
        "confidence":           confidence,
        "warnings":             warnings,
    }
    sections.append(
        "## pdf_extraction\n```json\n"
        + json.dumps(pdf_meta, ensure_ascii=False, indent=2)
        + "\n```"
    )

    for key in ("prices", "schedule", "qualification", "decision_points"):
        data = extracted.get(key)
        if data is not None:
            sections.append(
                f"## {key}\n```json\n"
                + json.dumps(data, ensure_ascii=False, indent=2)
                + "\n```"
            )

    # ── 원본 body 보존 ────────────────────────────────────────
    if original_body:
        sections.append(original_body)

    return frontmatter + "\n\n".join(sections) + "\n"


# ─────────────────────────────────────────────
# 단일 task 처리
# ─────────────────────────────────────────────

def process_task(task_file: Path, blog: str, paths: dict, dry_run: bool = False) -> bool:
    task_id = task_file.stem
    enriched_path = paths["enriched"] / task_file.name

    if enriched_path.exists():
        print(f"  스킵 (enriched 존재): {task_id}")
        return True

    text = task_file.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    notice_name = meta.get("notice_name", task_id)
    notice_id   = meta.get("notice_id", "")
    supply_type = meta.get("supply_type", "")

    print(f"\n  [{task_id}] {notice_name[:35]}")

    # ── PDF 로드 ──────────────────────────────────────────────
    pdf_path = _find_pdf_path(meta, blog)
    if not pdf_path:
        print(f"    ⚠️  PDF 없음 → enriched 생성 (no_pdf)")
        content = _build_enriched_content(
            meta, body, {}, {}, "low", ["PDF 파일 없음 — planner 재실행 필요"]
        )
        if not dry_run:
            paths["enriched"].mkdir(parents=True, exist_ok=True)
            enriched_path.write_text(content, encoding="utf-8")
        else:
            print("    [DRY-RUN] enriched 저장 생략")
        return True

    pdf_bytes = pdf_path.read_bytes()

    # ── 페이지별 텍스트 추출 ──────────────────────────────────
    from tools.pdf_parser import extract_pages_text
    pages = extract_pages_text(pdf_bytes)
    print(f"    📄 {len(pages)}페이지 추출")

    if not dry_run and notice_id:
        _save_page_artifacts(notice_id, blog, pages)

    # ── 관련 페이지 분류 ──────────────────────────────────────
    page_groups = _classify_pages(pages)
    for g, nums in page_groups.items():
        if nums:
            print(f"    🔍 {g}: p{nums}")

    # ── LLM 섹션별 추출 ──────────────────────────────────────
    extracted = {}
    warnings  = []

    # prices
    price_pages = page_groups.get("price", [])
    if price_pages:
        ctx = _combine_pages(pages, price_pages)
        extracted["prices"] = _llm_extract("prices", ctx)
        print(f"    💰 prices 추출 완료")
    else:
        warnings.append("가격 정보 페이지 미발견")

    # schedule
    sched_pages = page_groups.get("schedule", [])
    if sched_pages:
        ctx = _combine_pages(pages, sched_pages[:5])
        extracted["schedule"] = _llm_extract("schedule", ctx)
        print(f"    📅 schedule 추출 완료")
    else:
        warnings.append("일정 정보 페이지 미발견")

    # qualification (자격 + 소득자산 합산)
    qual_pages = sorted(set(
        page_groups.get("qualification", []) +
        page_groups.get("income_asset", [])
    ))
    if qual_pages:
        ctx = _combine_pages(pages, qual_pages[:8], max_chars=10000)
        extracted["qualification"] = _llm_extract("qualification", ctx)
        print(f"    🏠 qualification 추출 완료")
    else:
        warnings.append("자격 기준 페이지 미발견")

    # decision_points — 핵심 페이지 종합
    key_pages = sorted(set(
        sched_pages[:3] +
        page_groups.get("qualification", [])[:3] +
        page_groups.get("income_asset", [])[:2]
    ))
    if key_pages:
        # 추출된 데이터 + 텍스트 컨텍스트 합산
        dp_context = (
            f"공고명: {notice_name}\n공급유형: {supply_type}\n\n"
            f"가격 요약: {json.dumps(extracted.get('prices', {}), ensure_ascii=False)}\n"
            f"일정: {json.dumps(extracted.get('schedule', {}), ensure_ascii=False)}\n"
            f"자격: {json.dumps(extracted.get('qualification', {}), ensure_ascii=False)}\n\n"
            + _combine_pages(pages, key_pages, max_chars=4000)
        )
        extracted["decision_points"] = _llm_extract("decision_points", dp_context)
        print(f"    ✅ decision_points 생성 완료")

    # ── confidence 및 저장 ────────────────────────────────────
    confidence = _calc_confidence(page_groups, warnings)
    content    = _build_enriched_content(meta, body, page_groups, extracted, confidence, warnings)

    if dry_run:
        print(f"    [DRY-RUN] enriched 저장 생략 (confidence={confidence})")
        print(content[:500] + "...")
        return True

    paths["enriched"].mkdir(parents=True, exist_ok=True)
    enriched_path.write_text(content, encoding="utf-8")
    print(f"    ✅ enriched 저장 (confidence={confidence}): {enriched_path.name}")
    return True


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────

def run(blog: str, task_id: Optional[str] = None, dry_run: bool = False):
    print("=" * 50)
    print(f"PDF Reader Agent — {blog}" + (" [DRY-RUN]" if dry_run else ""))
    print("=" * 50)

    paths = _get_paths(blog)

    if task_id:
        # 특정 task만 처리
        target = paths["planned"] / f"{task_id}.md"
        if not target.exists():
            # test/ 폴더도 확인
            target = Path(f"blogs/{blog}/tasks/test/{task_id}.md")
        if not target.exists():
            print(f"❌ Task 파일 없음: {task_id}")
            return
        process_task(target, blog, paths, dry_run=dry_run)
    else:
        tasks = sorted(paths["planned"].glob("*.md"))
        if not tasks:
            print("처리할 planned task 없음")
            return
        # has_pdf: true 인 것만
        targets = [t for t in tasks if "has_pdf: true" in t.read_text(encoding="utf-8")]
        print(f"대상: {len(targets)}개 (has_pdf=true)")
        for t in targets:
            process_task(t, blog, paths, dry_run=dry_run)

    print(f"\n✅ 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog",    required=True)
    parser.add_argument("--task-id", dest="task_id", default=None,
                        help="특정 task ID (예: 20260605_001 또는 test_0000061094)")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일 저장 없이 결과만 출력")
    args = parser.parse_args()
    run(args.blog, args.task_id, args.dry_run)
