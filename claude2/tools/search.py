"""
Search Tool — LLM 뉴스 수집 + 특정 토픽 기사 추가 검색
"""

import re
import requests
import feedparser

LLM_KEYWORDS = [
    # 한국어
    "ai", "인공지능", "챗gpt", "chatgpt", "클로드", "제미나이", "오픈ai", "앤스로픽",
    "생성ai", "거대언어모델", "llm", "에이전트", "자동화", "딥러닝", "머신러닝",
    "구글ai", "메타ai", "gpt", "코파일럿", "sora", "멀티모달",
    # 영어 (한국 매체도 영어 표기 많이 씀)
    "openai", "anthropic", "gemini", "llama", "claude", "deepmind",
]

NEWS_SOURCES = [
    "https://www.aitimes.com/rss/allArticle.xml",       # AI타임스 (AI 전문)
    "https://www.bloter.net/feed",                       # 블로터 (IT/테크)
    "https://zdnet.co.kr/rss.xml",                       # ZDNet Korea
    "https://www.etnews.com/rss/S1N11.xml",              # 전자신문 IT
    "https://www.techm.kr/rss/allArticle.xml",           # 테크M
]


def _is_llm_related(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in LLM_KEYWORDS)


def _fetch_article_body(url: str) -> str:
    """기사 URL에서 본문 텍스트 추출 (최대 2000자)"""
    try:
        class _TextExtractor:
            def __init__(self):
                from html.parser import HTMLParser
                class P(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text, self._skip = [], False
                    def handle_starttag(self, tag, attrs):
                        if tag in ("script","style","nav","footer","header","aside"):
                            self._skip = True
                    def handle_endtag(self, tag):
                        if tag in ("script","style","nav","footer","header","aside"):
                            self._skip = False
                    def handle_data(self, data):
                        if not self._skip and data.strip():
                            self.text.append(data.strip())
                self._p = P()
            def feed(self, html): self._p.feed(html)
            @property
            def text(self): return " ".join(self._p.text)

        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        ex = _TextExtractor()
        ex.feed(resp.text)
        body = re.sub(r"\s+", " ", ex.text).strip()
        return body[:2000]
    except Exception:
        return ""


def fetch_llm_news(limit: int = 15) -> list:
    """여러 RSS 피드에서 LLM 관련 최신 뉴스 수집"""
    articles = []

    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if _is_llm_related(title, summary):
                    url = entry.get("link", "")
                    body = _fetch_article_body(url)
                    articles.append({
                        "title": title,
                        "url": url,
                        "summary": (summary[:300] if summary else body[:300]),
                        "body": body,
                        "published": entry.get("published", ""),
                        "source": feed.feed.get("title", source),
                    })
        except Exception as e:
            print(f"  뉴스 수집 오류 ({source}): {e}")

    seen, unique = set(), []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique[:limit]


if __name__ == "__main__":
    news = fetch_llm_news(10)
    print(f"수집된 뉴스: {len(news)}건")
    for n in news:
        print(f"  - {n['title'][:60]}  ({n['source']})")
