"""
market_price.py

국토교통부 아파트 매매 실거래가 API 조회.
MOLIT_API_KEY 없으면 조용히 None 반환.
"""

import os
import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import quote
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# 법정동코드 5자리 매핑 (시/구 단위)
# "시 구" 조합 키를 단일 키보다 먼저 매핑해야 정확히 매칭됨
LAWD_CD_MAP = {
    # 서울특별시 25구
    "종로구": "11110", "용산구": "11170",
    "성동구": "11200", "광진구": "11215", "동대문구": "11230",
    "중랑구": "11260", "성북구": "11290", "강북구": "11305",
    "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470",
    "강서구": "11500", "구로구": "11530", "금천구": "11545",
    "영등포구": "11560", "동작구": "11590", "관악구": "11620",
    "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
    # 서울 중구는 인천 중구와 충돌 방지용 별도 처리
    "서울 중구": "11140",
    # 인천광역시 (법정동코드 앞 5자리, 28xxx)
    "미추홀구": "28177", "연수구": "28185", "남동구": "28200",
    "부평구": "28237", "계양구": "28245",
    "인천 중구": "28110", "인천 동구": "28140", "인천 서구": "28260",
    # 경기도 — 구 있는 시 (시+구 조합 키)
    "수원시 장안구": "41111", "수원시 권선구": "41113",
    "수원시 팔달구": "41115", "수원시 영통구": "41117",
    "성남시 수정구": "41131", "성남시 중원구": "41133", "성남시 분당구": "41135",
    "안양시 만안구": "41171", "안양시 동안구": "41173",
    "안산시 상록구": "41271", "안산시 단원구": "41273",
    "고양시 덕양구": "41281", "고양시 일산동구": "41285", "고양시 일산서구": "41287",
    "용인시 처인구": "41461", "용인시 기흥구": "41463", "용인시 수지구": "41465",
    # 경기도 — 단일 시/군
    "의정부시": "41150", "광명시": "41210",
    "평택시": "41220", "동두천시": "41250", "과천시": "41290",
    "구리시": "41310", "남양주시": "41360", "오산시": "41370",
    "시흥시": "41390", "군포시": "41410", "의왕시": "41430",
    # 부천시 단독 매칭용 (구 명시 없을 때 원미구 코드로 폴백)
    "부천시": "41194",
    "하남시": "41450", "파주시": "41480", "이천시": "41500",
    "안성시": "41550", "김포시": "41570", "화성시": "41597",
    "광주시": "41610", "양주시": "41630", "포천시": "41650",
    "여주시": "41670",
    # 부천시: 법정구 코드 사용 (41190은 데이터 없음)
    "부천시 원미구": "41194", "부천시 소사구": "41195", "부천시 오정구": "41196",
}

# 시+구 조합 키 (더 긴 것 먼저 매핑해야 정확)
_COMPOUND_KEYS = [k for k in LAWD_CD_MAP if " " in k]
_SIMPLE_KEYS   = [k for k in LAWD_CD_MAP if " " not in k]


def _normalize_location(location):
    # type: (str) -> str
    """주소에서 광역시/특별시/도 등 불필요한 접미사 제거해 매칭 용이하게 정규화."""
    loc = location
    loc = loc.replace("인천광역시", "인천")
    loc = loc.replace("서울특별시", "서울")
    loc = loc.replace("경기도", "경기")
    loc = loc.replace("광역시", "")   # 대구·부산·울산·광주·대전 등
    loc = re.sub(r"(\w+)특례시", r"\1시", loc)  # 화성특례시 → 화성시
    return loc


def _extract_lawd_cd(location):
    # type: (str) -> tuple
    """주소에서 법정동코드와 지역명 추출. 못 찾으면 ("", "") 반환."""
    loc = _normalize_location(location)
    for key in _COMPOUND_KEYS:
        if key in loc:
            return LAWD_CD_MAP[key], key
    # 서울 중구 / 인천 중구 충돌 처리
    if "서울" in loc and "중구" in loc:
        return "11140", "서울 중구"
    if "인천" in loc and "중구" in loc:
        return LAWD_CD_MAP["인천 중구"], "인천 중구"
    for key in _SIMPLE_KEYS:
        if key in loc:
            return LAWD_CD_MAP[key], key
    return "", ""


def _fetch_month_transactions(lawd_cd, deal_ymd, service_key):
    # type: (str, str, str) -> list
    """특정 월 실거래 목록 반환 (XML 파싱). 실패 시 빈 리스트."""
    # Decoding 키는 URL에 직접 넣을 때 반드시 quote 처리
    encoded_key = quote(service_key, safe="")
    url = (
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        "?serviceKey={key}&LAWD_CD={lawd}&DEAL_YMD={ymd}&pageNo=1&numOfRows=1000"
    ).format(key=encoded_key, lawd=lawd_cd, ymd=deal_ymd)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        result_code = root.findtext(".//resultCode", "")
        if not result_code.startswith("0"):
            return []
        items = []
        for item in root.findall(".//item"):
            row = {child.tag: (child.text or "").strip() for child in item}
            items.append(row)
        return items
    except Exception:
        return []


def get_market_price(location, area_m2, months=12, min_build_year=2010):
    # type: (str, float, int, int) -> Optional[dict]
    """주변 시세 조회.

    Args:
        location:       주소 (예: "경기도 용인시 처인구 역북동 811번지")
        area_m2:        전용면적 (m²)
        months:         최근 몇 개월 기준
        min_build_year: 이 연도 이후 건축된 아파트만 포함 (구축 오염 방지)

    Returns dict or None:
        avg_per_m2      int  m²당 평균가 (만원)
        avg_per_pyeong  int  평당 평균가 (만원)
        count           int  사용 거래 건수
        region_name     str  지역명
        area_range      str  면적 검색 범위
        build_year_from int  적용된 건축년도 하한
    """
    service_key = os.getenv("MOLIT_API_KEY", "").strip()
    if not service_key:
        return None

    lawd_cd, region_name = _extract_lawd_cd(location)
    if not lawd_cd:
        return None

    # 최근 N개월 YYYYMM 목록 생성
    today = date.today()
    year = today.year
    month = today.month
    ym_list = []
    for _ in range(months):
        ym_list.append("{}{:02d}".format(year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    # API 호출
    all_txns = []
    for ym in ym_list:
        txns = _fetch_month_transactions(lawd_cd, ym, service_key)
        all_txns.extend(txns)
        time.sleep(0.1)

    if not all_txns:
        return None

    def _filter(txns, build_year_from):
        area_low  = area_m2 - 15
        area_high = area_m2 + 15
        result = []
        for t in txns:
            try:
                t_area = float(str(t.get("excluUseAr", "0")).strip())
                if not (area_low <= t_area <= area_high):
                    continue
                # 건축년도 필터
                build_yr = int(str(t.get("buildYear", "0")).strip() or "0")
                if build_yr and build_yr < build_year_from:
                    continue
                price_str = str(t.get("dealAmount", "0")).replace(",", "").strip()
                price_man = int(price_str)
                if price_man > 0:
                    result.append(price_man / t_area)
            except (ValueError, TypeError):
                continue
        return result

    # 건축년도 하한 적용 → 데이터 부족하면 단계적으로 완화
    applied_year = min_build_year
    per_m2_list = _filter(all_txns, min_build_year)
    if len(per_m2_list) < 5:
        applied_year = 2000
        per_m2_list = _filter(all_txns, 2000)
    if len(per_m2_list) < 3:
        applied_year = 0
        per_m2_list = _filter(all_txns, 0)
    if len(per_m2_list) < 3:
        return None

    avg_per_m2     = sum(per_m2_list) / len(per_m2_list)
    avg_per_pyeong = avg_per_m2 * 3.30579

    area_low  = area_m2 - 15
    area_high = area_m2 + 15
    return {
        "avg_per_m2":      round(avg_per_m2),
        "avg_per_pyeong":  round(avg_per_pyeong),
        "count":           len(per_m2_list),
        "region_name":     region_name,
        "area_range":      "{:.0f}~{:.0f}㎡".format(area_low, area_high),
        "build_year_from": applied_year,
    }
