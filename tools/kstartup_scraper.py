"""
tools/kstartup_scraper.py — K-Startup 창업지원사업 OpenAPI 스크래퍼

인증 불필요 (공개 API). 지역/분류 필터는 서버가 무시하므로 클라이언트에서 처리.
API: https://nidapi.k-startup.go.kr/api/kisedKstartupService/v1/getAnnouncementInformation
"""

import re
import requests
from datetime import date, datetime
from xml.etree import ElementTree as ET

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

KSTARTUP_BASE = "https://www.k-startup.go.kr"

KSTARTUP_API = (
    "https://nidapi.k-startup.go.kr/api/kisedKstartupService/v1"
    "/getAnnouncementInformation"
)

TARGET_CLSFC        = {"사업화"}
TARGET_REGIN_KW     = {"서울", "경기"}


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


# ─────────────────────────────────────────────
# 상세 페이지 크롤링 + 첨부파일 다운로드
# ─────────────────────────────────────────────

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    KSTARTUP_BASE,
}

_SECTION_KW = ["신청방법", "신청기간", "신청대상", "제출서류", "선정절차", "지원내용",
               "지원금액", "지원규모", "평가방법", "우대사항", "문의처"]


def _decode_filename(cd_header):
    """Content-Disposition filename 인코딩 처리 (EUC-KR → UTF-8)."""
    m = re.search(r'filename="([^"]+)"', cd_header)
    if not m:
        return "공고문.pdf"
    raw = m.group(1)
    try:
        return raw.encode("latin-1").decode("euc-kr")
    except Exception:
        return raw


def _extract_detail_text(html):
    """상세 페이지 HTML에서 공고 본문 텍스트 추출."""
    if not _BS4:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]

    # 본문 시작점: 신청방법/지원내용/모집공고 키워드 직전 10줄부터
    start = 0
    for i, line in enumerate(lines):
        if any(kw in line for kw in _SECTION_KW):
            start = max(0, i - 5)
            break

    # 문의처 이후는 불필요한 footer
    end = len(lines)
    for i, line in enumerate(lines[start:], start):
        if "K-Startup사업공고" in line or "기업(기관)정보" in line:
            end = i
            break

    return "\n".join(lines[start:end])


def _find_file_links(html):
    """상세 페이지에서 첨부파일 다운로드 URL 목록 반환."""
    if not _BS4:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "fileDownload" in href:
            url = KSTARTUP_BASE + href if href.startswith("/") else href
            links.append(url)
    return links


def fetch_detail(detail_url):
    """K-Startup 공고 상세 페이지 크롤링 + 첨부 PDF 다운로드.

    반환:
        {
            "text":         상세 페이지 본문 텍스트,
            "pdf_text":     PDF에서 추출한 전체 텍스트,
            "pdf_bytes":    첫 번째 PDF bytes (없으면 b""),
            "pdf_filename": PDF 파일명,
        }
    """
    result = {"text": "", "pdf_text": "", "pdf_bytes": b"", "pdf_filename": ""}

    if not detail_url:
        return result

    # 상세 페이지 크롤링
    try:
        r = requests.get(detail_url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("    상세 페이지 수집 실패: {}".format(e))
        return result

    result["text"] = _extract_detail_text(r.text)

    # 첨부파일 다운로드
    for file_url in _find_file_links(r.text):
        try:
            fr = requests.get(file_url, headers=_HEADERS, timeout=30)
            if fr.status_code != 200:
                continue
            filename = _decode_filename(fr.headers.get("Content-Disposition", ""))
            content  = fr.content

            # 첫 번째 PDF만 파싱 (이후 파일은 건너뜀)
            if not result["pdf_bytes"] and (
                filename.lower().endswith(".pdf")
                or "pdf" in fr.headers.get("Content-Type", "").lower()
            ):
                result["pdf_bytes"]   = content
                result["pdf_filename"] = filename
                result["pdf_text"]    = _extract_pdf_text(content)
                print("    PDF 첨부: {} ({:,}자)".format(filename[:40], len(result["pdf_text"])))
        except Exception as e:
            print("    파일 다운로드 실패: {}".format(e))

    return result


def _extract_pdf_text(pdf_bytes):
    """PDF bytes에서 전체 텍스트 추출 (pdfplumber 사용)."""
    if not pdf_bytes:
        return ""
    try:
        import io
        import pdfplumber
        texts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
        return "\n".join(texts)
    except Exception as e:
        print("    PDF 텍스트 추출 실패: {}".format(e))
        return ""
