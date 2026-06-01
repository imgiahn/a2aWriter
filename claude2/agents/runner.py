"""
Agent Runner — 모든 서브 에이전트를 Azure OpenAI로 호출
"""

import os
import json
import re
from pathlib import Path

from openai import AzureOpenAI


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-15-preview",
    )


def _model() -> str:
    return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")


def _load_prompt(name: str) -> str:
    return (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    return json.loads(raw)


def _chat(system: str, user: str, max_tokens: int = 2000) -> str:
    response = _client().chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def run_researcher(news_list: list, paper: dict, writing_guide: str, metrics: str, published: list = None) -> dict:
    """소재 선택 + 글쓰기 각도 결정"""
    published_section = ""
    if published:
        published_section = f"\n## 이미 발행된 글 목록 (중복 금지)\n{json.dumps(published, ensure_ascii=False, indent=2)}\n"

    user = f"""## 오늘 수집된 LLM 뉴스
{json.dumps(news_list, ensure_ascii=False, indent=2)}

## 오늘의 트렌딩 논문
{json.dumps(paper, ensure_ascii=False, indent=2)}

## 현재 Writing Guide
{writing_guide}

## 최근 성과 Metrics
{metrics}
{published_section}"""
    result = _chat(_load_prompt("researcher"), user, max_tokens=2000)
    return _extract_json(result)


def run_writer(research_result: dict, writing_guide: str) -> str:
    """실제 글 작성"""
    system = _load_prompt("writer") + f"\n\n---\n## Writing Guide\n{writing_guide}"
    user = f"다음 소재로 블로그 글을 작성해줘:\n\n{json.dumps(research_result, ensure_ascii=False, indent=2)}"
    return _chat(system, user, max_tokens=3000)


def run_editor(draft: str, writing_guide: str) -> dict:
    """퇴고 + 사람 냄새 체크"""
    user = f"## Writing Guide\n{writing_guide}\n\n## 초안\n{draft}"
    result = _chat(_load_prompt("editor"), user, max_tokens=4000)
    return _extract_json(result)


def run_analyzer(metrics: str, writing_guide: str, published_articles: list) -> dict:
    """주간 성과 분석 + writing_guide 업데이트"""
    articles_summary = "\n".join(
        f"- {a['date']} | {a['title']} | 조회수: {a.get('views', '미수집')}"
        for a in published_articles
    )
    user = f"""## 이번 주 발행 목록
{articles_summary}

## 전체 Metrics
{metrics}

## 현재 Writing Guide
{writing_guide}
"""
    result = _chat(_load_prompt("analyzer"), user, max_tokens=3000)
    return _extract_json(result)
