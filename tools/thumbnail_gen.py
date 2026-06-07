"""
tools/thumbnail_gen.py — Azure gpt-image-2로 청약 공고 썸네일 생성

generate_thumbnail(task: dict) -> bytes  (PNG bytes)
"""

import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
API_KEY  = os.getenv("AZURE_OPENAI_API_KEY", "")

# gpt-image-2 사용 (가용 시). 없으면 gpt-image-1 폴백
IMAGE_MODELS = ["gpt-image-2", "gpt-image-1"]

# 주거 유형별 배경 스타일
CATEGORY_STYLE = {
    "sale":                   "고급 아파트 분양, 현대적 건물 외관, 넓은 단지",
    "happy_housing":          "행복주택, 젊고 활기찬 주거 단지, 밝은 분위기",
    "national_rental":        "국민임대 아파트, 안정적인 주거, 따뜻한 분위기",
    "permanent_rental":       "영구임대 아파트, 커뮤니티 중심 주거",
    "public_rental_10y":      "공공임대 아파트, 10년 거주, 안정적인 환경",
    "integrated_public_rental": "통합공공임대, 다양한 계층 공존, 현대 단지",
    "purchase_rental":        "분양전환 임대 아파트, 내 집 마련 기회",
    "jeonse":                 "든든전세, 안심 전세 주택",
    "general":                "오피스텔 분양, 현대적 주거 복합건물",
}

# 지역별 랜드마크 힌트
REGION_HINT = {
    "서울": "서울 도심 스카이라인 배경",
    "경기": "경기 신도시 깔끔한 주거 단지",
    "인천": "인천 도시 전경",
}


def _shorten_title(name: str, max_len: int = 13) -> str:
    """공고명을 10~15자 이내 짧은 제목으로 변환."""
    import re as _re
    # 괄호 내용 제거
    name = _re.sub(r"\([^)]*\)", "", name).strip()
    name = _re.sub(r"\[[^\]]*\]", "", name).strip()
    # 불필요한 접미어 제거
    for suffix in ["입주자모집공고", "예비입주자", "모집공고", "공고", " 신청", " 모집"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    if len(name) <= max_len:
        return name
    # 공백 기준으로 자르기
    parts = name.split()
    result = ""
    for p in parts:
        if len(result) + len(p) + 1 > max_len:
            break
        result = (result + " " + p).strip()
    return result or name[:max_len]


def _build_prompt(task: dict) -> str:
    category = task.get("housing_category", "general")
    region   = task.get("region", "")
    name     = task.get("notice_name", "청약 공고")

    style    = CATEGORY_STYLE.get(category, CATEGORY_STYLE["general"])
    region_h = REGION_HINT.get(region, "한국 도시 전경")
    short_title = _shorten_title(name)

    prompt = (
        f"한국 부동산 청약 블로그 썸네일 이미지. "
        f"{style}. {region_h}. "
        f"파란 하늘과 구름, 황금빛 햇살, 선명한 색감. "
        f"이미지 중앙 하단부에 반투명 어두운 배경 위에 흰색 한글 굵은 텍스트로 "
        f'"{short_title}" 라고 크고 선명하게 적혀 있음. '
        f"전문적이고 신뢰감 있는 분위기. 사진 스타일, 고해상도, 넓은 앵글."
    )
    return prompt


def generate_thumbnail(task: dict, size: str = "1024x1024") -> bytes:
    """청약 공고 task 데이터로 썸네일 PNG bytes 생성.

    gpt-image-2 → gpt-image-1 순서로 시도.
    실패 시 빈 bytes 반환.
    """
    prompt = _build_prompt(task)
    api_ver = "2025-04-01-preview"

    for model in IMAGE_MODELS:
        url = f"{ENDPOINT}/openai/deployments/{model}/images/generations?api-version={api_ver}"
        try:
            resp = requests.post(
                url,
                headers={"api-key": API_KEY, "Content-Type": "application/json"},
                json={"prompt": prompt, "n": 1, "size": size},
                timeout=90,
            )
            if resp.status_code == 200:
                b64 = resp.json()["data"][0]["b64_json"]
                img_bytes = base64.b64decode(b64)
                print(f"  🎨 썸네일 생성 완료 ({model}, {len(img_bytes):,} bytes)", flush=True)
                return img_bytes
            elif resp.status_code == 404:
                continue  # 해당 모델 없으면 다음 시도
            else:
                print(f"  ⚠️  {model} 이미지 생성 실패: HTTP {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  ⚠️  {model} 오류: {e}")

    return b""


def upload_thumbnail_to_tistory(img_bytes: bytes, blog_url: str, cookies: dict) -> str:
    """생성된 이미지를 티스토리에 업로드하고 CDN URL 반환.

    업로드 엔드포인트: POST /manage/post/attach.json
    반환: CDN URL 문자열 (실패 시 빈 문자열)
    """
    if not img_bytes:
        return ""

    url = f"{blog_url}/manage/post/attach.json"
    headers = {
        "Referer":          f"{blog_url}/manage/newpost/",
        "Origin":           blog_url,
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        resp = requests.post(
            url,
            files={"file": ("thumbnail.png", img_bytes, "image/png")},
            cookies=cookies,
            headers=headers,
            timeout=60,
        )
        if resp.status_code == 200:
            cdn_url = resp.json().get("url", "")
            print(f"  🖼️  썸네일 업로드 완료", flush=True)
            return cdn_url
        print(f"  ⚠️  썸네일 업로드 실패: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  ⚠️  썸네일 업로드 오류: {e}")
    return ""
