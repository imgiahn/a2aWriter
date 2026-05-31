import os
import re
import time
import json
from datetime import date
from itertools import combinations

import requests
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ──────────────────────────────────────────────
TISTORY_ACCESS_TOKEN = os.getenv("TISTORY_ACCESS_TOKEN")
TISTORY_BLOG_NAME    = "mbtireallove"
POSTS_PER_DAY        = 10

azure_client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

# ── Tistory API ────────────────────────────────────────
def get_all_posts() -> list[dict]:
    posts, page = [], 1
    while True:
        resp = requests.get(
            "https://www.tistory.com/apis/post/list",
            params={
                "access_token": TISTORY_ACCESS_TOKEN,
                "output": "json",
                "blogName": TISTORY_BLOG_NAME,
                "page": page,
            },
            timeout=10,
        )
        data = resp.json().get("tistory", {})
        if data.get("status") != "200":
            break
        items = data.get("item", {}).get("posts", [])
        if not items:
            break
        posts.extend(items)
        if len(posts) >= int(data["item"].get("totalCount", 0)):
            break
        page += 1
        time.sleep(0.3)
    return posts


def get_category_id() -> str | None:
    resp = requests.get(
        "https://www.tistory.com/apis/category/list",
        params={
            "access_token": TISTORY_ACCESS_TOKEN,
            "output": "json",
            "blogName": TISTORY_BLOG_NAME,
        },
        timeout=10,
    )
    cats = resp.json().get("tistory", {}).get("item", {}).get("categories", [])
    for cat in cats:
        name = cat.get("name", "")
        if "썸" in name or "MBTI" in name:
            return cat.get("id")
    return None


def write_post(title: str, content: str, category_id: str | None) -> dict:
    params = {
        "access_token": TISTORY_ACCESS_TOKEN,
        "output": "json",
        "blogName": TISTORY_BLOG_NAME,
        "title": title,
        "content": content,
        "visibility": "3",
        "tag": "MBTI,궁합,연애,커플,MBTI궁합",
    }
    if category_id:
        params["category"] = category_id
    resp = requests.post(
        "https://www.tistory.com/apis/post/write",
        data=params,
        timeout=15,
    )
    return resp.json()


# ── 조합 계산 ──────────────────────────────────────────
COMBO_PATTERN = re.compile(
    r"(INTJ|INTP|ENTJ|ENTP|INFJ|INFP|ENFJ|ENFP"
    r"|ISTJ|ISFJ|ESTJ|ESFJ|ISTP|ISFP|ESTP|ESFP)"
    r"\s+"
    r"(INTJ|INTP|ENTJ|ENTP|INFJ|INFP|ENFJ|ENFP"
    r"|ISTJ|ISFJ|ESTJ|ESFJ|ISTP|ISFP|ESTP|ESFP)"
)

def extract_posted(posts: list[dict]) -> set[tuple]:
    done = set()
    for p in posts:
        for m in COMBO_PATTERN.findall(p.get("title", "")):
            done.add(tuple(sorted(m)))
    return done


def count_today_posts(posts: list[dict]) -> int:
    today = date.today().strftime("%Y-%m-%d")
    return sum(1 for p in posts if p.get("date", "").startswith(today))


def remaining_combos(posted: set[tuple]) -> list[tuple]:
    all_combos = {tuple(sorted(c)) for c in combinations(MBTI_TYPES, 2)}
    return list(all_combos - posted)


# ── 글 생성 ────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 MBTI 연애 심리 분석 전문가이자 블로거입니다.
친근하고 재밌는 한국어 대화체로, 이모지를 풍부하게 사용해 글을 씁니다.
HTML 형식으로만 출력합니다."""

def build_user_prompt(mbti1: str, mbti2: str) -> str:
    return f"""
{mbti1}과 {mbti2} 커플 궁합 분석 글을 아래 형식에 맞춰 HTML로 작성해주세요.

맨 첫 줄에 반드시 아래 형식으로 부제목을 넣어주세요:
<!-- SUBTITLE: [부제목] -->
(예시: "전략가와 헌신가의 안정적 케미", "두 이상주의자의 깊은 교감")

이후 HTML 본문:

1. 별점표 (HTML table)
   항목: 첫인상&썸케미 / 감정소통 / 연애지속력 / 갈등해결 / 장기궁합
   각 항목에 ⭐ 별점(5점 만점) + 한 줄 설명
   마지막에 총점 (x.x점 / 5점)

2. 본문 섹션 (h2 + p 태그 사용):
   💡 커플의 기본 특성
   💞 연애 초반 (썸·첫 만남)
   🔥 현실 연애의 주의점
   ⚠️ 갈등 상황과 해결법
   💍 장기 궁합 & 결혼 상성
   ✅ 실용 연애 꿀팁 4가지

3. 한 줄 마무리 요약 (p 태그)

조건:
- 각 MBTI 유형의 실제 특성 반영
- 공감되고 현실적인 분석
- 1500자 이상
""".strip()


def generate_content(mbti1: str, mbti2: str) -> tuple[str, str]:
    """(title, html_content) 반환"""
    resp = azure_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(mbti1, mbti2)},
        ],
        temperature=0.8,
        max_tokens=3000,
    )
    raw = resp.choices[0].message.content.strip()

    subtitle_match = re.search(r"<!--\s*SUBTITLE:\s*(.+?)\s*-->", raw)
    subtitle = subtitle_match.group(1) if subtitle_match else f"{mbti1}과 {mbti2}의 케미"
    content  = re.sub(r"<!--\s*SUBTITLE:\s*.+?\s*-->\n?", "", raw)

    title = f"💘 {mbti1} {mbti2} 커플 궁합 분석 – {subtitle}"
    return title, content


# ── 메인 ───────────────────────────────────────────────
def run():
    print("=" * 50)
    print("MBTI 궁합 자동 포스터 시작")
    print("=" * 50)

    print("기존 포스트 불러오는 중...")
    posts   = get_all_posts()
    posted  = extract_posted(posts)
    remain  = remaining_combos(posted)

    today_count = count_today_posts(posts)
    quota_left  = POSTS_PER_DAY - today_count

    print(f"전체 조합    : 120개")
    print(f"이미 올린 것 : {len(posted)}개")
    print(f"남은 것      : {len(remain)}개")
    print(f"오늘 올린 것 : {today_count}개  (남은 일일 쿼터: {quota_left}개)")

    if not remain:
        print("✅ 모든 조합 완료!")
        return

    if quota_left <= 0:
        print("오늘 일일 제한(10개) 도달. 내일 다시 실행됩니다.")
        return

    category_id = get_category_id()
    to_post = remain[:quota_left]

    for i, (mbti1, mbti2) in enumerate(to_post, 1):
        print(f"\n[{i}/{len(to_post)}] {mbti1} x {mbti2} 생성 중...")
        try:
            title, content = generate_content(mbti1, mbti2)
            print(f"  제목: {title}")

            result = write_post(title, content, category_id)
            status = result.get("tistory", {}).get("status")

            if status == "200":
                post_id = result.get("tistory", {}).get("postId", "?")
                print(f"  ✅ 포스팅 완료 (글 번호: {post_id})")
            else:
                print(f"  ❌ 실패: {json.dumps(result, ensure_ascii=False)}")

        except Exception as e:
            print(f"  ❌ 오류: {e}")

        if i < len(to_post):
            print("  30초 대기 중...")
            time.sleep(30)

    print(f"\n오늘 포스팅 완료! {len(to_post)}개 업로드")


if __name__ == "__main__":
    run()
