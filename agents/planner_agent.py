"""
Planner Agent

역할: 블로그별 콘텐츠 기획 및 Task 생성
실행: python agents/planner_agent.py --blog mbtireallove [--suggest]
      python agents/planner_agent.py --blog llmenginehistory              # LH 청약플러스 (기본)
      python agents/planner_agent.py --blog llmenginehistory --source applyhome  # 청약홈
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
    max_seq = 0
    for p in existing:
        try:
            num = int(p.stem.replace(f"{today}_", "").rstrip("s"))
            max_seq = max(max_seq, num)
        except ValueError:
            pass
    return f"{today}_{max_seq + 1:03d}{suffix}"


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


def _parse_suggestion(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fields = {"topic": "", "series": "mbti_relationship", "priority": "high", "template": "new"}
    for line in text.splitlines():
        for key in ("topic", "series", "priority", "template"):
            if line.startswith(f"{key}:"):
                fields[key] = line.split(":", 1)[1].strip()
    lines = text.splitlines()
    outline_lines, in_outline = [], False
    for line in lines:
        if line.strip() == "## 구성안":
            in_outline = True
            continue
        if in_outline and line.startswith("## ") and line.strip() != "## 구성안":
            break
        if in_outline:
            outline_lines.append(line)
    fields["outline"] = "\n".join(outline_lines).strip()
    return fields


def mbti_run(paths: dict, max_planned: int = 5):
    published = len(list(paths["published"].glob("*.md")))
    planned   = len(list(paths["planned"].glob("*.md")))

    print("=" * 50)
    print("Planner Agent — mbtireallove (반자동 모드)")
    print("=" * 50)
    print(f"발행 완료: {published}개 | 대기 중: {planned}개")

    if planned >= max_planned:
        print(f"⏸  planned {planned}개 — 추가 생성 불필요 (max={max_planned})")
        return

    suggestions = sorted(paths["suggestions"].glob("*.md"))
    if not suggestions:
        print("⏸  suggestions 없음. 새 시리즈 기획 필요")
        return

    to_promote = suggestions[:max_planned - planned]
    promoted = 0
    for s_path in to_promote:
        fields = _parse_suggestion(s_path)
        if not fields["topic"]:
            print(f"  ⚠️  topic 없음, 스킵: {s_path.name}")
            continue
        task_id = get_next_task_id(paths["planned"])
        create_task(
            folder       = paths["planned"],
            task_id      = task_id,
            topic        = fields["topic"],
            series       = fields["series"],
            priority     = fields["priority"],
            template     = fields["template"],
            content_type = "단편",
            parts        = 1,
            outline      = fields["outline"],
        )
        s_path.unlink()
        print(f"  📋 {s_path.name} → planned: {task_id} — {fields['topic'][:35]}...")
        promoted += 1

    print(f"\n✅ {promoted}개 suggestion → planned 자동 승인 (남은 suggestions: {len(suggestions) - promoted}개)")


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
{detail_text[:14000]}

{{
  "total_units": "총 공급세대수 (예: 50세대)",
  "notice_phase": "공고 단계 — '사전청약' 또는 '본청약' 중 하나",
  "apply_start": "청약 접수 시작일 YYYY.MM.DD — 사전청약이면 사전청약 접수 시작, 본청약이면 본청약 신규 접수 시작",
  "apply_end": "청약 접수 마감일 YYYY.MM.DD — notice_phase에 해당하는 접수 마감일. apply_start와 1~2일 차이. 주의: 선호순위 선택/배정결과 발표/신청포기/서류접수 마감일과 혼동 금지",
  "result_date": "당첨자 발표일 YYYY.MM.DD",
  "contract_start": "계약 시작일 YYYY.MM.DD",
  "contract_end": "계약 종료일 YYYY.MM.DD",
  "move_in": "입주 예정일",
  "supply_target": "공급 대상 (예: 무주택세대구성원)",
  "qualifications": "신청 자격 핵심 요약 (3줄 이내)",
  "deposit": "보증금 (임대의 경우)",
  "monthly_rent": "월 임대료",
  "jeonse_amount": "전세금 (전세형의 경우)",
  "house_types": "주택형/면적 (예: 36㎡, 46㎡, 59㎡)",
  "sale_price": "분양가 (예: 84A타입 6억 2천만원, 타입별 범위)",
  "contract_amount": "계약금 (예: 분양가의 10%)",
  "interim_payment": "중도금 (예: 분양가의 60%, 6회 납부)",
  "balance_payment": "잔금 (예: 분양가의 30%, 입주 시)",
  "first_supply": "우선공급 조건 요약",
  "conversion": "분양전환 여부 (예: 10년 후 분양전환 가능, 해당없음)",
  "location_detail": "단지 위치 상세 주소",
  "project_name": "단지명 또는 브랜드명 (예: e편한세상 분당 퍼스트빌리지, 없으면 빈 문자열)",
  "supply_type_detail": "공급유형 (예: 공공분양(신혼희망타운), 국민임대, 행복주택 등)",
  "supply_this_time": "이번 공급 세대수 (예: 473세대, 예비입주자 포함 시 별도 표기)",
  "supply_units": "타입별 공급세대수 (예: 51㎡ 274세대, 55㎡ 482세대, 59㎡ 177세대 / 없으면 빈 문자열)",
  "restriction_rewin": "재당첨 제한 기간 (예: 10년, 없음)",
  "restriction_resale": "전매 제한 기간 (예: 소유권이전등기일로부터 3년, 없음)",
  "obligation_residence": "거주 의무 기간 (예: 3년, 없음)"
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


def _get_cached_pdf(notice_id: str) -> bytes:
    """이미 저장된 PDF가 있으면 bytes로 반환한다."""
    pdf_path = Path(f"data/llmenginehistory/notices/{notice_id}/original.pdf")
    if pdf_path.exists():
        return pdf_path.read_bytes()
    return b""


def _save_pdf_to_disk(notice_id: str, pdf_bytes: bytes, pdf_filename: str = "") -> Optional[str]:
    """PDF bytes를 data/llmenginehistory/notices/{notice_id}/original.pdf 로 저장한다.
    원본 파일명은 filename.txt에 함께 저장 (publisher PDF 업로드 시 사용).
    """
    if not pdf_bytes or not notice_id:
        return None
    folder = Path(f"data/llmenginehistory/notices/{notice_id}")
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / "original.pdf"
    if not pdf_path.exists():
        pdf_path.write_bytes(pdf_bytes)
    if pdf_filename:
        (folder / "filename.txt").write_text(pdf_filename, encoding="utf-8")
    return str(pdf_path)


def extract_qualification_tables(pdf_bytes: bytes) -> str:
    """PDF에서 소득 기준 표를 직접 추출해 HTML로 반환한다 (GPT 미사용)."""
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.pdf_parser import extract_qual_tables_as_html

    return extract_qual_tables_as_html(pdf_bytes)


def extract_scoring_text(pdf_bytes: bytes) -> str:
    """PDF에서 소득 배점 기준 페이지 텍스트를 추출한다."""
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.pdf_parser import extract_scoring_focused

    return extract_scoring_focused(pdf_bytes)


def _write_task_file(folder: Path, task_id: str, item: dict, fields: dict,
                     category: str, housing_source: str, task_priority: str,
                     pdf_text: str = "", qual_fields: dict = None,
                     qual_tables_html: str = "", pdf_path: str = "",
                     scoring_text: str = "", pdf_original_filename: str = ""):
    """Task 파일을 생성한다. planner 운영/개발 모드 공통 사용."""
    folder.mkdir(parents=True, exist_ok=True)
    notice_id   = item.get("notice_id", "")
    notice_name = item.get("notice_name", "")
    supply_type = item.get("supply_type", "")
    region      = item.get("region", "")
    notice_date = item.get("notice_date", "")
    detail_url  = item.get("detail_url", "")
    has_pdf_flag  = "true" if pdf_text else "false"
    pdf_section   = ("## PDF 원문\n\n```\n" + pdf_text[:6000] + "\n```") if pdf_text else ""
    qual_section    = (f"## 소득자산기준\n\n{qual_tables_html}") if qual_tables_html else ""
    scoring_section = (f"## 배점기준\n\n```\n{scoring_text}\n```") if scoring_text else ""

    content = f"""---
task_id: {task_id}
status: planned
topic: {notice_name} 공고 해설
series: 청약공고해설
priority: {task_priority}
housing_source: {housing_source}
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
notice_phase: {fields.get('notice_phase', '')}
apply_start: {fields.get('apply_start', '')}
apply_end: {fields.get('apply_end', '')}
result_date: {fields.get('result_date', '')}
contract_start: {fields.get('contract_start', '')}
contract_end: {fields.get('contract_end', '')}
move_in: {fields.get('move_in', '')}
supply_target: {fields.get('supply_target', '')}
deposit: {fields.get('deposit', '')}
monthly_rent: {fields.get('monthly_rent', '')}
jeonse_amount: {fields.get('jeonse_amount', '')}
house_types: {fields.get('house_types', '')}
supply_units: {fields.get('supply_units', '')}
sale_price: {fields.get('sale_price', '')}
contract_amount: {fields.get('contract_amount', '')}
interim_payment: {fields.get('interim_payment', '')}
balance_payment: {fields.get('balance_payment', '')}
first_supply: {fields.get('first_supply', '')}
conversion: {fields.get('conversion', '')}
location_detail: {fields.get('location_detail', '')}
supply_this_time: {fields.get('supply_this_time', '')}
restriction_rewin: {fields.get('restriction_rewin', '')}
restriction_resale: {fields.get('restriction_resale', '')}
obligation_residence: {fields.get('obligation_residence', '')}
income_limit: {(qual_fields or {}).get('income_limit', '')}
asset_limit: {(qual_fields or {}).get('asset_limit', '')}
qualifications: |
  {fields.get('qualifications', '').replace(chr(10), chr(10) + '  ')}
created_by: planner_agent
created_at: {date.today().isoformat()}
has_pdf: {has_pdf_flag}
pdf_path: {pdf_path}
pdf_original_filename: {pdf_original_filename}
---
{qual_section}

{scoring_section}

{pdf_section}
"""
    (folder / f"{task_id}.md").write_text(content, encoding="utf-8")


def get_existing_notice_ids(blog: str) -> set:
    """기존 처리된 공고의 notice_id + notice_name을 모두 반환한다.

    크로스소스 중복 방지 (LH/청약홈 ID 체계가 달라도 이름이 같으면 스킵).
    """
    keys = set()
    base = Path(f"blogs/{blog}/tasks")
    for folder in ["planned", "writing", "published", "failed"]:
        for f in (base / folder).glob("*.md"):
            text = f.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("notice_id:"):
                    v = line.split(":", 1)[1].strip()
                    if v:
                        keys.add(v)
                elif line.startswith("notice_name:"):
                    v = line.split(":", 1)[1].strip()
                    if v:
                        keys.add(v)
    return keys


def cheongyak_run(paths: dict):
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.lh_scraper import scrape, fetch_detail_with_pdf  # noqa

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

        if (notice_id and notice_id in existing_ids) or (notice_name and notice_name in existing_ids):
            print(f"  스킵 (중복): {notice_name}")
            continue

        # 상세 페이지 크롤링 + PDF 다운로드 + 구조화 추출
        housing_source = item.get("housing_source", "임대")
        task_priority  = item.get("priority", "medium")
        mi             = item.get("list_mi", "1026")
        print(f"  상세+PDF 수집 중: [{housing_source}] {notice_name[:30]}...")
        # PDF 캐시 확인 — 이미 있으면 상세 페이지 접속 자체 스킵
        cached_pdf = _get_cached_pdf(notice_id)
        if cached_pdf:
            from tools.pdf_parser import extract_price_focused
            detail_text = ""
            pdf_bytes   = cached_pdf
            pdf_text    = extract_price_focused(cached_pdf)
            print(f"    📄 PDF 캐시 사용 ({len(pdf_text)}자)")
        else:
            detail      = fetch_detail_with_pdf(notice_id, mi)
            detail_text = detail["text"]
            pdf_text    = detail.get("pdf_text", "")
            pdf_bytes   = detail.get("pdf_bytes", b"")
        pdf_orig_filename = detail.get("pdf_filename", "") if not cached_pdf else ""
        if pdf_text:
            print(f"    📄 PDF {pdf_orig_filename[:30]} ({len(pdf_text)}자)")
        combined    = detail_text + ("\n\n=== PDF 원문 ===\n" + pdf_text if pdf_text else "")
        fields           = extract_notice_fields(combined, supply_type)
        qual_tables_html = extract_qualification_tables(pdf_bytes) if pdf_bytes else ""
        scoring_text     = extract_scoring_text(pdf_bytes) if pdf_bytes else ""
        pdf_disk_path    = _save_pdf_to_disk(notice_id, pdf_bytes, pdf_orig_filename) or ""
        if qual_tables_html:
            print(f"    📊 소득기준 표 추출 완료")
        if scoring_text:
            print(f"    🎯 배점기준 추출 완료")
        if pdf_disk_path:
            print(f"    💾 PDF 저장: {pdf_disk_path}")
        category = get_housing_category(supply_type)

        _write_task_file(
            folder=paths["planned"],
            task_id=get_next_task_id(paths["planned"]),
            item=item, fields=fields, category=category,
            housing_source=housing_source, task_priority=task_priority,
            pdf_text=pdf_text, qual_tables_html=qual_tables_html,
            pdf_path=pdf_disk_path, scoring_text=scoring_text,
            pdf_original_filename=pdf_orig_filename,
        )
        print(f"  📋 Task 생성: [{housing_source}/{category}] {notice_name[:30]}")
        if notice_id:
            existing_ids.add(notice_id)
        if notice_name:
            existing_ids.add(notice_name)
        created += 1

    if created == 0:
        print("새 공고 없음 (모두 기존 Task 존재)")
    else:
        print(f"\n✅ {created}개 Task 생성 완료")


# ─────────────────────────────────────────────
# 청약홈 전용 로직
# ─────────────────────────────────────────────

def applyhome_run(paths: dict):
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.applyhome_scraper import scrape_notices, fetch_detail_with_pdf as ah_fetch

    print("=" * 50)
    print("Planner Agent — llmenginehistory (청약홈)")
    print("=" * 50)

    existing_ids = get_existing_notice_ids("llmenginehistory")
    print(f"기존 처리 공고: {len(existing_ids)}건")
    print("청약홈 서울/경기/인천 공고 수집 중...")

    announcements = scrape_notices()
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

        if not notice_name:
            continue

        if (notice_id and notice_id in existing_ids) or (notice_name and notice_name in existing_ids):
            print(f"  스킵 (중복): {notice_name[:30]}")
            continue

        housing_source = item.get("housing_source", "분양")
        task_priority  = item.get("priority", "high")
        print(f"  상세+PDF 수집 중: [{housing_source}] {notice_name[:30]}...")

        cached_pdf = _get_cached_pdf(notice_id)
        if cached_pdf:
            from tools.pdf_parser import extract_price_focused
            detail_text = ""
            pdf_bytes   = cached_pdf
            pdf_text    = extract_price_focused(cached_pdf)
            print(f"    📄 PDF 캐시 사용 ({len(pdf_text)}자)")
        else:
            try:
                detail      = ah_fetch(notice_id,
                                       list_type=item.get("list_type", "APT분양"),
                                       house_secd=item.get("house_secd", ""))
                detail_text = detail["text"]
                pdf_text    = detail.get("pdf_text", "")
                pdf_bytes   = detail.get("pdf_bytes", b"")
            except Exception as e:
                print(f"    ⚠️  상세 수집 실패, 목록 정보만 사용: {e}", file=sys.stderr)
                detail_text = ""
                pdf_text    = ""
                pdf_bytes   = b""
        pdf_orig_filename = (detail.get("pdf_filename", "") if not cached_pdf else "")
        if pdf_text:
            print(f"    📄 PDF {pdf_orig_filename[:30]} ({len(pdf_text)}자)")

        combined         = detail_text + ("\n\n=== PDF 원문 ===\n" + pdf_text if pdf_text else "")
        fields           = extract_notice_fields(combined, supply_type)
        qual_tables_html = extract_qualification_tables(pdf_bytes) if pdf_bytes else ""
        scoring_text     = extract_scoring_text(pdf_bytes) if pdf_bytes else ""
        pdf_disk_path    = _save_pdf_to_disk(notice_id, pdf_bytes, pdf_orig_filename) or ""

        if qual_tables_html:
            print(f"    📊 소득기준 표 추출 완료")
        if scoring_text:
            print(f"    🎯 배점기준 추출 완료")

        # item에 detail_url 보완
        item["detail_url"] = detail_url or f"https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?pblancNo={notice_id}"
        item["notice_date"] = fields.get("notice_date") or notice_date

        category = get_housing_category(supply_type)

        _write_task_file(
            folder=paths["planned"],
            task_id=get_next_task_id(paths["planned"]),
            item=item, fields=fields, category=category,
            housing_source=housing_source, task_priority=task_priority,
            pdf_text=pdf_text, qual_tables_html=qual_tables_html,
            pdf_path=pdf_disk_path, scoring_text=scoring_text,
            pdf_original_filename=pdf_orig_filename,
        )
        print(f"  📋 Task 생성: [{housing_source}/{category}] {notice_name[:30]}")
        if notice_id:
            existing_ids.add(notice_id)
        if notice_name:
            existing_ids.add(notice_name)
        created += 1

    if created == 0:
        print("새 공고 없음 (모두 기존 Task 존재)")
    else:
        print(f"\n✅ {created}개 Task 생성 완료")


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────

def dev_single_notice(blog: str, notice_id: str, mi: str = "1026"):
    """개발용: 공고 1건만 처리해 tasks/test/ 에 저장. 운영 데이터 불변."""
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.lh_scraper import fetch_detail_with_pdf

    print("=" * 50)
    print(f"[DEV] Planner — 단일 공고 모드: {notice_id} (mi={mi})")
    print("=" * 50)

    test_folder = Path(f"blogs/{blog}/tasks/test")
    test_folder.mkdir(parents=True, exist_ok=True)

    print(f"  상세 수집 중...")
    detail = fetch_detail_with_pdf(notice_id, mi)
    detail_text  = detail["text"]
    pdf_text     = detail.get("pdf_text", "")
    pdf_bytes    = detail.get("pdf_bytes", b"")
    pdf_filename = detail.get("pdf_filename", "")

    if not detail_text:
        print(f"❌ 공고 텍스트 수집 실패. notice_id={notice_id}, mi={mi} 확인")
        return

    print(f"  상세 텍스트: {len(detail_text)}자")
    if pdf_text:
        print(f"  PDF 추출 완료: {pdf_filename} ({len(pdf_text)}자)")

    # 기본 정보 추정 (텍스트에서)
    housing_source = "분양" if mi == "1027" else "임대"
    supply_type    = ""
    for line in detail_text.splitlines()[:30]:
        for key in ["공공분양", "국민임대", "행복주택", "매입임대", "든든전세",
                    "영구임대", "통합공공임대", "공공임대", "분양전환"]:
            if key in line:
                supply_type = key
                break
        if supply_type:
            break

    combined         = detail_text + ("\n\n=== PDF 원문 ===\n" + pdf_text if pdf_text else "")
    fields           = extract_notice_fields(combined, supply_type)
    qual_tables_html = extract_qualification_tables(pdf_bytes) if pdf_bytes else ""
    scoring_text     = extract_scoring_text(pdf_bytes) if pdf_bytes else ""
    pdf_disk_path    = _save_pdf_to_disk(notice_id, pdf_bytes, detail.get("pdf_filename", "")) or ""
    if qual_tables_html:
        print(f"  📊 소득기준 표 추출 완료")
    if scoring_text:
        print(f"  🎯 배점기준 추출 완료")
    if pdf_disk_path:
        print(f"  💾 PDF 저장: {pdf_disk_path}")
    # GPT 추출 결과로 supply_type 보완
    if not supply_type and fields.get("supply_type_detail"):
        supply_type = fields["supply_type_detail"]
    category = get_housing_category(supply_type)
    priority = "high" if mi == "1027" else "medium"

    # 단지명: GPT 추출 project_name 우선, 없으면 location_detail
    notice_name = (fields.get("project_name") or fields.get("location_detail") or notice_id)

    task_id = f"test_{notice_id}"
    item = {
        "notice_id":      notice_id,
        "notice_name":    notice_name,
        "supply_type":    supply_type,
        "region":         "",
        "notice_date":    "",
        "deadline":       fields.get("apply_end", ""),
        "detail_url":     f"https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do?wrtancNo={notice_id}&mi={mi}",
        "housing_source": housing_source,
        "priority":       priority,
    }

    _write_task_file(
        folder=test_folder, task_id=task_id, item=item,
        fields=fields, category=category,
        housing_source=housing_source, task_priority=priority,
        pdf_text=pdf_text, qual_tables_html=qual_tables_html,
        pdf_path=pdf_disk_path, scoring_text=scoring_text,
    )

    out_path = test_folder / f"{task_id}.md"
    print(f"\n✅ Task 저장: {out_path}")
    print(f"   다음 단계: python agents/writer_agent.py --blog {blog} --task {out_path} --dry-run")


# ─────────────────────────────────────────────
# startupgrantnote 전용 로직 (K-Startup 창업지원사업 공고 분석)
# ─────────────────────────────────────────────

def _fmt_dt(s):
    """YYYYMMDD → YYYY.MM.DD"""
    if s and len(s) == 8:
        return "{}.{}.{}".format(s[:4], s[4:6], s[6:])
    return s


def _write_kstartup_task(folder, task_id, item):
    folder.mkdir(parents=True, exist_ok=True)
    notice_name    = item.get("notice_name", "")
    region         = item.get("region", "")
    org_name       = item.get("org_name", "")
    biz_enyy       = item.get("biz_enyy", "")
    apply_start    = _fmt_dt(item.get("apply_start", ""))
    apply_end      = _fmt_dt(item.get("apply_end", ""))
    detail_url     = item.get("detail_url", "")
    apply_url      = item.get("apply_url", "")
    # 상세 페이지 텍스트 우선, 없으면 API 필드 fallback
    detail_text    = item.get("detail_text", "")
    pdf_text       = item.get("pdf_text", "")
    content        = (detail_text or item.get("content", ""))[:3000]
    apply_target   = item.get("apply_target", "")[:500]
    exclude_target = item.get("exclude_target", "")[:300]
    startup_cat    = item.get("startup_category", "창업지원금가이드")

    text = """---
task_id: {task_id}
status: planned
topic: {notice_name} 분석
series: K-Startup공고분석
priority: {priority}
template: kstartup
type: 단편
parts: 1
notice_id: {notice_id}
notice_name: {notice_name}
supply_type: {supply_type}
region: {region}
org_name: {org_name}
apply_start: {apply_start}
apply_end: {apply_end}
biz_enyy: {biz_enyy}
detail_url: {detail_url}
apply_url: {apply_url}
startup_category: {startup_cat}
created_by: planner_agent
created_at: {created_at}
---

# 기획 의도

K-Startup 창업지원사업 공고를 예비창업자/초기창업자 입장에서 해석한다.
공고 원문을 복사하지 말고, 지원 여부 판단에 도움이 되는 분석 글을 작성한다.

## 공고 기본 정보

| 항목 | 내용 |
|------|------|
| 사업명 | {notice_name} |
| 주관기관 | {org_name} |
| 지원지역 | {region} |
| 지원대상 (창업업력) | {biz_enyy} |
| 신청기간 | {apply_start} ~ {apply_end} |
| 공고 원문 | {detail_url} |
| 신청 URL | {apply_url} |

## 공고 내용

{content}

## 신청 대상

{apply_target}

## 신청 제외 대상

{exclude_target}

{pdf_section}
""".format(
        task_id=task_id,
        notice_id=item.get("notice_id", ""),
        notice_name=notice_name,
        supply_type=item.get("supply_type", "사업화"),
        region=region,
        org_name=org_name,
        apply_start=apply_start,
        apply_end=apply_end,
        biz_enyy=biz_enyy,
        detail_url=detail_url,
        apply_url=apply_url,
        startup_cat=startup_cat,
        priority=item.get("priority", "high"),
        created_at=date.today().isoformat(),
        content=content,
        apply_target=apply_target,
        exclude_target=exclude_target,
        pdf_section=("## 공고문 PDF 원문\n\n```\n" + pdf_text[:4000] + "\n```") if pdf_text else "",
    )
    (folder / "{}.md".format(task_id)).write_text(text, encoding="utf-8")


def startupgrantnote_run(paths: dict):
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from tools.kstartup_scraper import scrape_notices, fetch_detail

    print("=" * 50)
    print("Planner Agent - startupgrantnote (K-Startup)")
    print("=" * 50)

    existing_ids    = get_existing_notice_ids("startupgrantnote")
    planned_count   = len(list(paths["planned"].glob("*.md")))
    published_count = len(list(paths["published"].glob("*.md")))
    print("기존 처리 공고: {}건 | 발행완료: {}개 | 대기중: {}개".format(
        len(existing_ids), published_count, planned_count))
    print("K-Startup 사업화 공고 수집 중 (서울/경기/전국)...")

    announcements = scrape_notices(max_pages=5, per_page=100)
    if not announcements:
        print("수집된 공고 없음")
        return

    print("수집: {}건 (사업화 + 서울/경기/전국 필터)".format(len(announcements)))

    created = 0
    for item in announcements:
        notice_id   = item.get("notice_id", "")
        notice_name = item.get("notice_name", "")
        if not notice_name:
            continue
        if ((notice_id and notice_id in existing_ids)
                or (notice_name and notice_name in existing_ids)):
            print("  스킵 (중복): {}".format(notice_name[:40]))
            continue

        # 상세 페이지 크롤링 + 첨부파일 다운로드
        detail_url = item.get("detail_url", "")
        print("  상세 수집 중: {}...".format(notice_name[:35]))
        detail = fetch_detail(detail_url)
        item["detail_text"] = detail["text"]
        item["pdf_text"]    = detail["pdf_text"]
        item["pdf_bytes"]   = detail["pdf_bytes"]
        item["pdf_filename"] = detail["pdf_filename"]

        task_id = get_next_task_id(paths["planned"])
        _write_kstartup_task(paths["planned"], task_id, item)
        print("  Task 생성: [{}] {} → {}".format(
            item.get("region", ""), notice_name[:40], item.get("startup_category", "")))

        if notice_id:
            existing_ids.add(notice_id)
        if notice_name:
            existing_ids.add(notice_name)
        created += 1

    if created == 0:
        print("새 공고 없음 (모두 기존 Task 존재)")
    else:
        print("\n완료: {}개 Task 생성".format(created))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog",      required=True, help="블로그 이름")
    parser.add_argument("--suggest",   action="store_true", help="AI 주제 제안 모드 (mbtireallove 전용)")
    parser.add_argument("--source",    default="lh", choices=["lh", "applyhome"], help="수집 소스 (기본: lh)")
    parser.add_argument("--notice-id", dest="notice_id", help="[개발] 공고번호 1건만 처리 → tasks/test/ 저장")
    parser.add_argument("--mi",        default="1026", help="[개발] LH 목록 mi 값 (1026=임대, 1027=분양)")
    args = parser.parse_args()

    if args.notice_id:
        dev_single_notice(args.blog, args.notice_id, args.mi)
        sys.exit(0)

    paths = get_paths(args.blog)

    if args.blog == "mbtireallove":
        if args.suggest:
            mbti_suggest(paths)
        else:
            mbti_run(paths)
    elif args.blog == "llmenginehistory":
        if args.source == "applyhome":
            applyhome_run(paths)
        else:
            cheongyak_run(paths)
    elif args.blog == "startupgrantnote":
        startupgrantnote_run(paths)
    else:
        print(f"❌ 알 수 없는 블로그: {args.blog}")
        sys.exit(1)
