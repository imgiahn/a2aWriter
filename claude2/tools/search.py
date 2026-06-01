"""
Search Tool — LLM 뉴스 수집 + 특정 토픽 기사 추가 검색
"""

import re
import requests
import feedparser

LLM_KEYWORDS = [
    "llm", "gpt", "claude", "gemini", "llama", "mistral",
    "openai", "anthropic", "deepmind", "ai model", "language model",
    "transformer", "fine-tuning", "rag", "agent", "reasoning",
    "chatgpt", "copilot", "sora", "diffusion", "multimodal"
]

NEWS_SOURCES = [
    "https://hnrss.org/frontpage",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.marktechpost.com/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theregister.com/headlines.atom",
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
