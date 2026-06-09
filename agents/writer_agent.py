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
import json
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
        "tasks_enriched": base / "tasks/enriched",
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

    # 소득자산기준 HTML 섹션 추출
    qual_m = re.search(r"## 소득자산기준\n\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
    parsed["_qual_tables_html"] = qual_m.group(1).strip() if qual_m else ""

    # 배점기준 텍스트 섹션 추출
    score_m = re.search(r"## 배점기준\n\n```\n(.*?)\n```", body, re.DOTALL)
    parsed["_scoring_text"] = score_m.group(1).strip() if score_m else ""

    # enriched JSON 섹션 파싱 (없으면 빈 값 — planned task도 정상 동작)
    def _parse_json_section(name: str, default):
        m = re.search(rf"## {name}\n+```json\n(.*?)\n```", body, re.DOTALL)
        if not m:
            return default
        try:
            return json.loads(m.group(1))
        except Exception:
            return default

    parsed["_prices"]          = _parse_json_section("prices", {})
    parsed["_schedule"]        = _parse_json_section("schedule", {})
    parsed["_qualification"]   = _parse_json_section("qualification", {})
    parsed["_decision_points"] = _parse_json_section("decision_points", [])

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


TABLE_STYLE = "border-collapse:collapse; width:100%; text-align:center;"
TH_STYLE    = "background:#f5f5f5; border:1px solid #ddd; padding:8px; text-align:center;"
TD_STYLE    = "border:1px solid #ddd; padding:8px; text-align:center;"


def _parse_kor_price_man(text):
    # type: (str) -> int
    """'6억8210만원' → 68210 (만원 단위)"""
    text = text.strip()
    eok_m = re.search(r"(\d+)억", text)
    man_m = re.search(r"억(\d+)만|^(\d+)만", text)
    result = 0
    if eok_m:
        result += int(eok_m.group(1)) * 10000
    if man_m:
        val = man_m.group(1) or man_m.group(2)
        if val:
            result += int(val)
    return result


def _parse_sale_info(sale_price, house_types):
    # type: (str, str) -> Optional[dict]
    """sale_price/house_types에서 대표 타입의 면적·가격 추출."""
    if not sale_price or not house_types:
        return None
    first_type = house_types.split(",")[0].strip()
    area_m = re.match(r"(\d+)", first_type)
    if not area_m:
        return None
    area_m2 = float(area_m.group(1))

    # 해당 타입의 가격 범위 추출
    escaped = re.escape(first_type)
    price_m = re.search(escaped + r"\s+([^\s,]+)", sale_price)
    price_str = price_m.group(1) if price_m else sale_price.split(",")[0]

    parts = price_str.split("~")
    min_price = _parse_kor_price_man(parts[0])
    max_price = _parse_kor_price_man(parts[-1])
    if min_price <= 0:
        return None
    return {
        "type_name":     first_type,
        "area_m2":       area_m2,
        "min_price_man": min_price,
        "max_price_man": max_price,
    }


def _fmt_man(v):
    # type: (int) -> str
    """68210 → '6억 8,210만원'"""
    if v >= 10000:
        eok = v // 10000
        rem = v % 10000
        return "{}억 {:,}만원".format(eok, rem) if rem else "{}억원".format(eok)
    return "{:,}만원".format(v)


def _build_safety_margin_html(task, market_data):
    # type: (dict, Optional[dict]) -> str
    """안전마진 분석 HTML 섹션 생성. 데이터 없으면 빈 문자열."""
    if not market_data:
        return ""
    sale_price  = task.get("sale_price", "")
    house_types = task.get("house_types", "")
    sale_info   = _parse_sale_info(sale_price, house_types)
    if not sale_info:
        return ""

    area_m2         = sale_info["area_m2"]
    pyeong          = area_m2 * 0.3025
    market_pyeong   = market_data["avg_per_pyeong"]
    sale_min_pyeong = round(sale_info["min_price_man"] / pyeong)
    margin_pyeong   = market_pyeong - sale_min_pyeong
    margin_pct      = (margin_pyeong / market_pyeong * 100) if market_pyeong else 0
    market_total    = round(market_pyeong * pyeong)
    margin_total    = market_total - sale_info["min_price_man"]

    if margin_pyeong >= 0:
        color = "#2e7d32"
        sign  = "+"
        bg    = "#e8f5e9"
    else:
        color = "#c62828"
        sign  = "-"
        bg    = "#ffebee"

    region          = market_data["region_name"]
    count           = market_data["count"]
    area_range      = market_data["area_range"]
    build_year_from = market_data.get("build_year_from", 0)
    type_name  = sale_info["type_name"]
    min_total  = sale_info["min_price_man"]

    th = "background:#f5f5f5; border:1px solid #ddd; padding:10px; text-align:center;"
    td = "border:1px solid #ddd; padding:10px; text-align:center;"
    td_color = td + " color:{};".format(color)

    return (
        "<h2>📊 안전마진 분석</h2>\n"
        "<p style=\"color:#666; font-size:14px; margin:4px 0 12px;\">"
        "{region} 전용 {area_range}{build_year_str} 최근 12개월 실거래 {count}건 기준</p>\n"
        "<table style=\"border-collapse:collapse; width:100%; text-align:center;\">\n"
        "  <thead><tr>\n"
        "    <th style=\"{th}\">구분</th>\n"
        "    <th style=\"{th}\">평당가</th>\n"
        "    <th style=\"{th}\">전용 {area_m2:.0f}㎡ 기준 총액</th>\n"
        "  </tr></thead>\n"
        "  <tbody>\n"
        "    <tr>\n"
        "      <td style=\"{td}\">주변 시세 (실거래 평균)</td>\n"
        "      <td style=\"{td}\"><strong>{market_pyeong:,}만원</strong></td>\n"
        "      <td style=\"{td}\">{market_total_fmt}</td>\n"
        "    </tr>\n"
        "    <tr>\n"
        "      <td style=\"{td}\">분양가 최저 ({type_name})</td>\n"
        "      <td style=\"{td}\"><strong>{sale_min_pyeong:,}만원</strong></td>\n"
        "      <td style=\"{td}\">{min_total_fmt}</td>\n"
        "    </tr>\n"
        "    <tr style=\"background:{bg}; font-weight:bold;\">\n"
        "      <td style=\"{td}\">안전마진</td>\n"
        "      <td style=\"{td_color}\">{sign}{margin_pyeong:,}만원/평</td>\n"
        "      <td style=\"{td_color}\">"
        "{sign}{margin_total_fmt} ({sign}{margin_pct:.1f}%)</td>\n"
        "    </tr>\n"
        "  </tbody>\n"
        "</table>\n"
    ).format(
        region=region,
        area_range=area_range,
        build_year_str=" {}년 이후 신축".format(build_year_from) if build_year_from else "",
        count=count,
        area_m2=area_m2,
        market_pyeong=market_pyeong,
        market_total_fmt=_fmt_man(market_total),
        type_name=type_name,
        sale_min_pyeong=sale_min_pyeong,
        min_total_fmt=_fmt_man(min_total),
        bg=bg,
        sign=sign,
        margin_pyeong=abs(margin_pyeong),
        margin_total_fmt=_fmt_man(abs(margin_total)),
        margin_pct=abs(margin_pct),
        th=th,
        td=td,
        td_color=td_color,
    )


def _build_map_html(location: str) -> str:
    """위치 지도 링크 버튼 HTML 생성 (네이버 지도 + 카카오 지도).

    신규 택지는 지구/블록 주소가 지도에 없으므로 동 단위까지만 잘라서 사용.
    """
    if not location:
        return ""
    from urllib.parse import quote as _quote

    # 동/읍/면 단위까지만 추출 (지구명·블록명 제거)
    import re as _re
    m = _re.search(r"(.+?(?:동|읍|면|리))\b", location)
    query = m.group(1).strip() if m else location
    enc = _quote(query)
    naver = f"https://map.naver.com/v5/search/{enc}"
    kakao = f"https://map.kakao.com/?q={enc}"
    return (
        f'<p style="margin:10px 0;">'
        f'<a href="{naver}" target="_blank" rel="noopener" '
        f'style="display:inline-block;padding:6px 14px;background:#03c75a;color:#fff;'
        f'border-radius:4px;text-decoration:none;font-size:14px;margin-right:8px;">📍 네이버 지도</a>'
        f'<a href="{kakao}" target="_blank" rel="noopener" '
        f'style="display:inline-block;padding:6px 14px;background:#fee500;color:#3c1e1e;'
        f'border-radius:4px;text-decoration:none;font-size:14px;">📍 카카오 지도</a>'
        f'</p>'
    )


def _build_qual_html(income_limit: str, asset_limit: str,
                     qual_tables_html: str = "", scoring_text: str = "") -> str:
    """소득/자산 기준을 최소 조건 표 + 배점표 + 소득 금액 표로 재구성.

    토큰 초과 방지를 위해 두 번 호출로 분리:
    - 호출 1: 신청 최소 조건 + 우선공급/일반공급 배점표 (텍스트 위주)
    - 호출 2: 소득별 배점 + 가구원수별 금액 표 (숫자 위주)
    """
    source = qual_tables_html or ((income_limit or "") + "\n" + (asset_limit or ""))
    if not source.strip() and not scoring_text:
        return ""

    STYLE = f"table: {TABLE_STYLE} / th: {TH_STYLE} / td: {TD_STYLE}"

    # ── 호출 1: 최소 조건 + 배점표 ──────────────────────────────
    prompt1 = f"""아래 데이터를 HTML 표로 재정리하세요. HTML만 출력하세요.

소득 기준 데이터 (금액 숫자에 콤마 천단위 구분 반드시 적용 예: 9,793,892):
{source[:1500]}

배점 기준 원문:
{scoring_text[:2500]}

출력 규칙:

[표 1] <h3>신청 소득 최소 조건</h3> + <table>
- 칼럼: 구분 | 3인 이하 | 4인 | 5인 | 6인 | 7인
- 행: 가장 완화된 소득 상한 기준 (단독소득 / 맞벌이 구분)
- 구분 열: "단독소득 (130% 이하)" / "맞벌이 (140% 이하)"
- 나머지 셀: 금액 숫자만, 설명 텍스트 혼합 금지

[표 2] <h3>우선공급 배점표 (총 9점)</h3> + <table> (우선공급 배점 데이터 있는 경우에만)
- 칼럼: 배점 항목 | 평가요소 | 점수
- 항목명: 첫 번째 행에만, 이후 같은 항목은 빈 셀

[표 3] <h3>일반공급 배점표 (총 12점)</h3> + <table> (일반공급 배점 데이터 있는 경우에만)
- 칼럼: 배점 항목 | 평가요소 | 점수
- 항목명: 첫 번째 행에만, 이후 같은 항목은 빈 셀

표 스타일: {STYLE}
줄글·설명 문장 금지, HTML만 출력"""

    parts = []
    for prompt in (prompt1,):
        try:
            resp = azure_client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_completion_tokens=3500,
            )
            result = resp.choices[0].message.content.strip()
            if result:
                parts.append(result)
        except Exception:
            pass

    return "\n\n".join(parts)


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
    deposit          = task.get("deposit", "")
    monthly_rent     = task.get("monthly_rent", "")
    jeonse_amount    = task.get("jeonse_amount", "")
    house_types      = task.get("house_types", "")
    sale_price       = task.get("sale_price", "")
    contract_amount  = task.get("contract_amount", "")
    interim_payment  = task.get("interim_payment", "")
    balance_payment  = task.get("balance_payment", "")
    first_supply         = task.get("first_supply", "")
    conversion           = task.get("conversion", "")
    location_detail      = task.get("location_detail", "")
    supply_this_time     = task.get("supply_this_time", "")
    restriction_rewin    = task.get("restriction_rewin", "")
    restriction_resale   = task.get("restriction_resale", "")
    obligation_residence = task.get("obligation_residence", "")
    supply_units         = task.get("supply_units", "")
    notice_phase         = task.get("notice_phase", "")
    contract_start       = task.get("contract_start", "")
    contract_end         = task.get("contract_end", "")
    income_limit         = task.get("income_limit", "")
    asset_limit          = task.get("asset_limit", "")

    blog_name = "llmenginehistory"
    guide = _load_category_guide(blog_name, category)
    focus = CATEGORY_FOCUS.get(category, CATEGORY_FOCUS["general"])

    system_prompt = f"""당신은 청약 정보를 전문적으로 해설하는 블로그 작가입니다.

독자: 청약에 이미 관심 있는 사람. 기본 개념은 안다.
목표: 독자가 "나는 신청해야 해? 말아야 해?"를 판단할 수 있도록.

절대 금지:
- 공고명을 제목으로 그대로 사용
- "이번 공고는..." 으로 시작
- LH·청약·국민임대 등 기본 개념 설명
- "공고문을 확인하세요", "알아보겠습니다", "살펴보겠습니다"
- 의미 없는 반복, 뻔한 마무리
- 소득 기준·자산 기준을 <p> 태그 줄글로 나열하는 것 (반드시 <table> 태그로 출력)
- 데이터가 없을 때 그 사실을 본문에 언급하는 것 ("데이터가 확인되지 않습니다", "제공된 데이터에 없어", "별도 확인 필요" 등 일체 금지 — 없으면 그냥 해당 항목 생략)

이 공고 유형({supply_type})의 핵심 포인트: {focus}

작성 가이드:
{guide}"""

    # 공고 데이터 정리
    basic_info = {
        "단지명": notice_name.split("(")[0].strip() if "(" in notice_name else notice_name,
        "위치": location_detail or region,
        "총 세대수": total_units,
        "이번 공급": supply_this_time,
        "입주 예정일": move_in,
        "재당첨 제한": restriction_rewin,
        "전매 제한": restriction_resale,
        "거주 의무": obligation_residence,
    }
    price_info = {
        "분양가": sale_price,
        "계약금": contract_amount,
        "중도금": interim_payment,
        "잔금": balance_payment,
        "보증금": deposit,
        "월 임대료": monthly_rent,
        "전세금": jeonse_amount,
        "주택형": house_types,
        "타입별 공급세대수": supply_units,
    }
    contract_period = f"{contract_start} ~ {contract_end}" if contract_start and contract_end else contract_start
    apply_label = f"{notice_phase} 신청 시작" if notice_phase else "신청 시작"
    apply_end_label = f"{notice_phase} 신청 마감" if notice_phase else "신청 마감"
    schedule_info = {
        apply_label: apply_start,
        apply_end_label: apply_end,
        "당첨 발표": result_date,
        "계약": contract_period,
        "입주 예정": move_in,
    }
    region_short = region.replace("특별시","").replace("광역시","").replace("도","").strip()

    # enriched 구조화 데이터 (있는 경우 우선 사용)
    _prices        = task.get("_prices", {})
    _schedule      = task.get("_schedule", {})
    _qualification = task.get("_qualification", {})
    _dp            = task.get("_decision_points", [])

    enriched_block = ""
    if any([_prices, _schedule, _qualification]):
        enriched_block = f"""
## PDF 구조화 추출 데이터 (아래 데이터 우선 사용)
가격: {json.dumps(_prices, ensure_ascii=False)}
일정: {json.dumps(_schedule, ensure_ascii=False)}
자격/소득/자산: {json.dumps(_qualification, ensure_ascii=False)}
판단포인트: {json.dumps(_dp, ensure_ascii=False)}
"""

    user_prompt = f"""아래 LH 청약 공고를 해설하는 블로그 글을 HTML로 작성하세요.

## 공고 원본 정보
- 공고명: {notice_name}
- 공급유형: {supply_type}
- 지역: {region}
- 공고일: {notice_date}
- 원문: {detail_url}

## 추출된 데이터
기본정보: {basic_info}
분양/임대 가격: {price_info}
자격: {qualifications or supply_target}
우선공급: {first_supply}
공고단계: {notice_phase or "본청약"}
일정: {schedule_info}
분양전환: {conversion}
소득기준: {income_limit}
자산기준: {asset_limit}{enriched_block}

---

출력 형식 (순서 고정, 아래 그대로):

맨 첫 줄: <!-- TITLE: [SEO 제목] -->
- 공고명 통째 복사 금지 (블록번호·괄호·"입주자모집공고" 제거)
- 단지명·브랜드명이 있으면 반드시 포함 (독자가 그 이름으로 검색함)
  예: "e편한세상 분당 퍼스트빌리지 신혼희망타운 청약 신청 조건"
- 단지명 없는 경우만: "{region_short} {supply_type} 신청 조건 총정리"

---

[섹션 1] 기본 정보 표
- <table> style: border-collapse:collapse; width:100%; text-align:center;
- <th> style: background:#f5f5f5; border:1px solid #ddd; padding:10px; text-align:center; width:30%;
- <td> style: border:1px solid #ddd; padding:10px; text-align:center;
- 행 항목 (데이터 있는 것만): 단지명 / 위치 / 총 세대수 / 이번 공급 / 입주 예정일 / 재당첨 제한 / 전매 제한 / 거주 의무

[섹션 2] 사업 개요 (<h2>사업 개요</h2>)
- 단지·지역 특성 (교통, 생활권, 입지) 2~3문장
- 이 공고를 주목해야 하는 이유 1~2문장
- "이번 공고는..." 시작 금지

[섹션 3] 분양정보 (<h2>분양정보</h2>) — 임대 타입이면 "임대 조건"으로 대체
- 타입별 공급 정보 표: 공급면적(㎡) / 사전청약 / 본청약 / 합계 / 분양가 / 평당가
  - 사전청약·본청약 세대수 데이터 없으면 세대수(합계) 1열로 대체
  - 평당가 = 분양가 ÷ (공급면적㎡ × 0.3025), 반드시 계산해서 명시
- 계약금 / 중도금 / 잔금 납부 방법
- 데이터 없는 항목은 해당 줄 생략, 억측 금지

[섹션 4] 청약 조건 (<h2>청약 조건</h2>)
- 신청 자격 1~2문장, 우선공급 조건 1문장
- 소득 기준·자산 기준: 본문에 직접 쓰지 말고 {{QUAL_TABLES}} 플레이스홀더만 삽입
- 데이터 없는 항목 생략

[섹션 5] 청약 일정 (<h2>청약 일정</h2>)
- <table> 형태 (리스트 금지)
- 칼럼: 구분 | 일정
- 행 레이블은 위 "공고단계" 값을 앞에 붙여서 표기 (예: 공고단계가 "본청약"이면 "본청약 신청 시작", "사전청약"이면 "사전청약 신청 시작")
- 행 순서: 신청 시작 / 신청 마감 / 당첨 발표 / 계약 / 입주 예정 (데이터 있는 것만)
- 마감일 셀은 <strong> 처리
- 표 스타일: border-collapse:collapse; width:100%; text-align:center;
- th 스타일: background:#f5f5f5; border:1px solid #ddd; padding:10px; text-align:center; width:30%;
- td 스타일: border:1px solid #ddd; padding:10px; text-align:center;"""

    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=3500,
        timeout=90,
    )
    raw = resp.choices[0].message.content.strip()

    # TITLE 추출 (GPT가 전체 제목 생성)
    m     = re.search(r"<!--\s*TITLE:\s*(.+?)\s*-->", raw)
    title = m.group(1).strip() if m else notice_name
    if not title.startswith("🏠"):
        title = f"🏠 {title}"
    html  = re.sub(r"<!--\s*TITLE:\s*.+?\s*-->\n?", "", raw)

    # 위치 지도 링크 주입 (기본 정보 표 바로 다음)
    map_html = _build_map_html(location_detail or region)
    if map_html:
        html = re.sub(r"(</table>)", r"\1" + "\n" + map_html, html, count=1)

    # 소득자산기준 표 주입 (항상 GPT로 재구성 — task body HTML이 있으면 source로 활용)
    qual_html = _build_qual_html(
        income_limit, asset_limit,
        qual_tables_html=task.get("_qual_tables_html", ""),
        scoring_text=task.get("_scoring_text", ""),
    )
    has_placeholder = "{{QUAL_TABLES}}" in html or "{QUAL_TABLES}" in html
    if has_placeholder:
        html = html.replace("{{QUAL_TABLES}}", qual_html)
        html = html.replace("{QUAL_TABLES}", qual_html)
    elif qual_html:
        html = re.sub(r"(<h2>청약 일정</h2>)", f"{qual_html}\n\\1", html, count=1)

    # 안전마진 분석 주입 (분양가 있는 경우만)
    if sale_price:
        sale_info = _parse_sale_info(sale_price, house_types)
        if sale_info:
            print("  시세 조회 중... (국토교통부 실거래가)")
            import sys as _sys, os as _os
            _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            from tools.market_price import get_market_price
            market_data = get_market_price(
                location_detail or region, sale_info["area_m2"]
            )
            safety_html = _build_safety_margin_html(task, market_data)
            if safety_html:
                html = re.sub(
                    r"(<h2>청약 조건</h2>)",
                    safety_html + r"\1",
                    html,
                    count=1,
                )
                print("  안전마진 섹션 추가 완료")
            else:
                print("  시세 데이터 없음 — 안전마진 섹션 생략")

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


def run(blog: str, task_file: Optional[Path] = None, dry_run: bool = False):
    print("=" * 50)
    label = f"Writer Agent — {blog}" + (" [DRY-RUN]" if dry_run else "")
    print(label)
    print("=" * 50)

    paths = get_paths(blog)

    # ── task 파일 결정 ────────────────────────────
    if task_file:
        # --task 지정: 해당 파일만 처리
        if not task_file.exists():
            print(f"❌ Task 파일 없음: {task_file}")
            return
    else:
        paths["articles_draft"].mkdir(parents=True, exist_ok=True)
        paths["tasks_writing"].mkdir(parents=True, exist_ok=True)

        # llmenginehistory: enriched/ 우선, 없으면 planned/ fallback
        if blog == "llmenginehistory":
            enriched_dir = paths["tasks_enriched"]
            task_file = get_next_task(enriched_dir) if enriched_dir.exists() else None
            if task_file:
                print(f"  (enriched task 사용)")
            else:
                task_file = get_next_task(paths["tasks_planned"])
        else:
            task_file = get_next_task(paths["tasks_planned"])

        if not task_file:
            print(f"처리할 Task 없음")
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

    if dry_run:
        # ── 개발 모드: preview 저장, 운영 데이터 불변 ──
        preview_dir = Path(f"articles/{blog}/preview")
        preview_dir.mkdir(parents=True, exist_ok=True)
        out_path = preview_dir / f"{task_id}.html"
        out_path.write_text(f"<!-- TITLE: {title} -->\n{html}", encoding="utf-8")
        print(f"  [DRY-RUN] Preview 저장: {out_path}")
        print(f"  [DRY-RUN] Task 이동 없음, 발행 없음")
        print(f"\n✅ 완료 (dry-run): {task_id}")
    else:
        # ── 운영 모드 ──────────────────────────────
        paths["articles_draft"].mkdir(parents=True, exist_ok=True)
        paths["tasks_writing"].mkdir(parents=True, exist_ok=True)
        draft_path = paths["articles_draft"] / f"{task_id}.html"
        draft_path.write_text(f"<!-- TITLE: {title} -->\n{html}", encoding="utf-8")
        print(f"  초안 저장: {draft_path}")
        writing_path = paths["tasks_writing"] / task_file.name
        shutil.move(str(task_file), str(writing_path))
        print(f"  Task 이동: planned/ → writing/")
        print(f"\n✅ 완료: {task_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog",    required=True,        help="블로그 이름")
    parser.add_argument("--task",    type=Path, default=None,
                        help="[개발] 특정 task 파일 경로 (예: blogs/llmenginehistory/tasks/test/test_xxx.md)")
    parser.add_argument("--dry-run", action="store_true",
                        help="[개발] 글 생성 후 articles/preview/ 저장. 발행/task 이동 없음")
    args = parser.parse_args()
    run(args.blog, task_file=args.task, dry_run=args.dry_run)
