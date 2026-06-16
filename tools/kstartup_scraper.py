"""
tools/kstartup_scraper.py — K-Startup 창업지원사업 OpenAPI 스크래퍼

인증 불필요 (공개 API). 지역/분류 필터는 서버가 무시하므로 클라이언트에서 처리.
API: https://nidapi.k-startup.go.kr/api/kisedKstartupService/v1/getAnnouncementInformation
"""

import requests
from datetime import date, datetime
from xml.etree import ElementTree as ET

KSTARTUP_API = (
    "https://nidapi.k-startup.go.kr/api/kisedKstartupService/v1"
    "/getAnnouncementInformation"
)

TARGET_CLSFC        = {"사업화"}
TARGET_REGIN_KW     = {"서울", "경기", "전국"}


def _parse_date(s):
    if not s or len(s) < 8:
        return None
    try:
        return datetime.strptime(s[:8], "%Y%m%d").date()
    except Exception:
        return None


def _map_category(biz_enyy):
    """창업업력(biz_enyy) → startupgrantnote 카테고리명."""
    if not biz_enyy:
        return "창업지원금가이드"
    tags = {t.strip() for t in biz_enyy.split(",")}
    has_pre    = "예비창업자" in tags
    has_early  = bool(tags & {"1년미만", "2년미만", "3년미만"})
    has_growth = bool(tags & {"5년미만", "7년미만", "10년미만"})

    if has_pre and not has_early and not has_growth:
        return "예비창업자"
    if has_growth:
        return "도약기창업자"
    if has_early or has_pre:
        return "초기창업자"
    return "창업지원금가이드"


def scrape_notices(max_pages=5, per_page=100):
    """K-Startup 사업화 공고 수집.

    필터 (클라이언트):
    - supt_biz_clsfc == '사업화'
    - supt_regin 에 서울/경기/전국 포함
    - pbanc_rcpt_end_dt >= 오늘 (마감 미경과)

    반환: list of dict (notice_id, notice_name, region, apply_end, ...)
    """
    today   = date.today()
    results = []

    for page in range(1, max_pages + 1):
        try:
            r = requests.get(KSTARTUP_API, params={
                "page":        page,
                "perPage":     per_page,
                "rcrt_prgs_yn": "Y",
            }, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"  [K-Startup API] 오류 (page={page}): {e}")
            break

        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            print(f"  [K-Startup API] XML 파싱 오류 (page={page}): {e}")
            break

        items = root.findall(".//item")
        if not items:
            break

        has_future = False
        for item in items:
            d = {col.attrib["name"]: (col.text or "").strip()
                 for col in item.findall("col")}

            end_dt = _parse_date(d.get("pbanc_rcpt_end_dt", ""))
            if end_dt:
                if end_dt < today:
                    continue
                has_future = True

            # 사업화 필터
            if d.get("supt_biz_clsfc", "") not in TARGET_CLSFC:
                continue

            # 서울/경기/전국 필터
            regin = d.get("supt_regin", "")
            if not any(kw in regin for kw in TARGET_REGIN_KW):
                continue

            notice_id   = d.get("pbanc_sn", "")
            notice_name = d.get("biz_pbanc_nm", "")
            biz_enyy    = d.get("biz_enyy", "")

            results.append({
                "notice_id":        notice_id,
                "notice_name":      notice_name,
                "housing_source":   "K-Startup",
                "supply_type":      d.get("supt_biz_clsfc", "사업화"),
                "region":           regin,
                "org_name":         d.get("sprv_inst") or d.get("pbanc_ntrp_nm", ""),
                "apply_start":      d.get("pbanc_rcpt_bgng_dt", ""),
                "apply_end":        d.get("pbanc_rcpt_end_dt", ""),
                "biz_enyy":         biz_enyy,
                "detail_url":       d.get("detl_pg_url", ""),
                "apply_url":        d.get("biz_aply_url", ""),
                "content":          d.get("pbanc_ctnt", ""),
                "apply_target":     d.get("aply_trgt_ctnt", ""),
                "exclude_target":   d.get("aply_excl_trgt_ctnt", ""),
                "aply_trgt":        d.get("aply_trgt", ""),
                "startup_category": _map_category(biz_enyy),
                "priority":         "high",
            })

        # 현재 페이지에 유효 공고가 하나도 없으면 이후 페이지도 불필요
        if not has_future and page > 1:
            break

    return results
