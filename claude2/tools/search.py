"""
Search Tool — LLM 뉴스 + 트렌딩 논문 수집
"""

import requests
import feedparser
from datetime import datetime, timedelta


LLM_KEYWORDS = [
    "llm", "gpt", "claude", "gemini", "llama", "mistral",
    "openai", "anthropic", "deepmind", "ai model", "language model",
    "transformer", "fine-tuning", "rag", "agent", "reasoning"
]

NEWS_SOURCES = [
    "https://hnrss.org/frontpage",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.marktechpost.com/feed/",
]


def _is_llm_related(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in LLM_KEYWORDS)


def fetch_llm_news(limit: int = 5) -> list:
    """RSS 피드에서 최신 LLM 뉴스 수집"""
    articles = []

    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source)
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if _is_llm_related(title, summary):
                    articles.append({
                        "title": title,
                        "url": entry.get("link", ""),
                        "summary": summary[:400],
                        "published": entry.get("published", ""),
                        "source": feed.feed.get("title", source),
                    })
                if len(articles) >= limit * 2:
                    break
        except Exception as e:
            print(f"  뉴스 수집 오류 ({source}): {e}")

    # 중복 제거 후 최신 순 반환
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique[:limit]


def fetch_trending_paper() -> dict:
    """arxiv API에서 최신 LLM 관련 논문 수집"""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": "cat:cs.LG OR cat:cs.CL",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 10,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        feed = feedparser.parse(response.text)

        for entry in feed.entries:
            title = entry.get("title", "").replace("\n", " ").strip()
            abstract = entry.get("summary", "").replace("\n", " ")[:600]
            authors = [a.get("name", "") for a in entry.get("authors", [])[:3]]

            # LLM 관련 논문 우선
            if _is_llm_related(title, abstract):
                return {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                }

        # LLM 관련 없으면 그냥 최신 것
        if feed.entries:
            e = feed.entries[0]
            return {
                "title": e.get("title", "").replace("\n", " ").strip(),
                "abstract": e.get("summary", "").replace("\n", " ")[:600],
                "authors": [a.get("name", "") for a in e.get("authors", [])[:3]],
                "url": e.get("link", ""),
                "published": e.get("published", ""),
            }

    except Exception as e:
        print(f"  논문 수집 오류: {e}")

    return {}


if __name__ == "__main__":
    print("=== LLM 뉴스 ===")
    for news in fetch_llm_news(3):
        print(f"  - {news['title']}")
        print(f"    {news['url']}")

    print("\n=== 트렌딩 논문 ===")
    paper = fetch_trending_paper()
    if paper:
        print(f"  - {paper['title']}")
        print(f"    {paper['url']}")
