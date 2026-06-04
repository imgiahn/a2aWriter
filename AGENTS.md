# AGENTS.md — AI 협업 핸드오프 파일

> Claude Code와 Codex가 공유하는 프로젝트 컨텍스트.
> 작업 후 반드시 이 파일을 업데이트하고 커밋할 것.

---

## 프로젝트 개요

**a2aWriter** — Planner → Writer → Publisher 3-Agent 자동 블로그 발행 시스템

- **EC2 서버:** 13.61.144.167 (Amazon Linux, KST)
- **GitHub:** https://github.com/imgiahn/a2aWriter
- **운영 블로그 2개:**
  - `mbtireallove` — MBTI 궁합 시리즈 (티스토리)
  - `llmenginehistory` — 서울/경기 청약 인사이트 (티스토리)

---

## 폴더 구조 요약

```
~/a2aWriter/
├── agents/
│   ├── planner_agent.py   # LH 공고 수집 → task 파일 생성
│   ├── writer_agent.py    # task → 초안 작성
│   └── publisher_agent.py # 초안 → 티스토리 발행
├── blogs/
│   ├── mbtireallove/tasks/planned|writing|published|failed|suggestions/
│   └── llmenginehistory/tasks/planned|writing|published|failed/
├── tools/
│   ├── lh_scraper.py      # LH 청약플러스 Playwright 스크래퍼
│   └── pdf_parser.py      # pdfplumber 기반 금액 추출
├── articles/              # 초안/발행 HTML (git 미추적)
├── browser_data/          # 카카오 쿠키 (git 미추적)
└── .env
```

---

## 현재 상태 (2026-06-05 기준)

### mbtireallove
- planned 잔여: **20개**
- 크론: 하루 5개 자동 발행 (08,10,12,14,16시)
- 특이사항: 없음

### llmenginehistory
- planned 잔여: **5개**
- published: 1개
- 크론: 06시 planner 수집, 09~12시 하루 4개 발행
- **주의: 티스토리 무료 15개 제한** → 초과 시 임시저장으로 저장됨

---

## 진행 중인 작업

| 작업 | 담당 | 상태 | 비고 |
|------|------|------|------|
| - | - | - | 현재 없음 |

---

## 결정사항 (변경 금지)

- PDF 파싱: `pdfplumber` 사용, `extract_price_focused()` 10000자 추출
- LH 상세 접근: 목록 클릭 방식만 허용 (URL 직접 접근 불가)
- task `priority` 필드 = 작업 우선순위 / `first_supply` 필드 = 우선공급 조건 (혼동 주의)
- `get_next_task_id()`: 파일 수가 아닌 최대 번호 기준
- Writer: Playwright 재크롤링 없음, task 데이터만 사용
- 제목: 공고명 복사 금지, SEO 검색어 기반 생성

---

## 주요 파일 & 역할

| 파일 | 역할 |
|------|------|
| `blogs/*/config.md` | 블로그별 설정 |
| `blogs/*/writing_guide.md` | 글쓰기 가이드 |
| `blogs/llmenginehistory/guides/{category}.md` | 공급유형별 작성 가이드 |
| `blogs/mbtireallove/memory/` | MBTI 발행 이력/결정사항/지표 |

---

## 환경

```
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4-mini
Python: 3.9 (서버 venv)
```

---

## 핸드오프 로그

> 작업 완료 후 아래에 한 줄 추가: `YYYY-MM-DD [담당AI] 작업내용`

- 2026-06-05 [Claude] AGENTS.md 초안 작성, 프로젝트 컨텍스트 정리
