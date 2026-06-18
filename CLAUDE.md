# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**a2aWriter** — Planner → Writer → Publisher 3개 Agent가 협업하는 AI 자동 블로그 발행 시스템.

EC2 서버: `13.61.144.167` (Amazon Linux, KST)  
접속: `ssh -i giahn.pem ec2-user@13.61.144.167`  
대시보드: `http://13.61.144.167:5001` (Flask, 포트 5001)

### 운영 블로그 3개

| 블로그 | URL | 주제 | 수집 소스 |
|--------|-----|------|-----------|
| `llmenginehistory` | https://llmenginehistory.tistory.com | 서울/경기/인천 청약 인사이트 | LH 청약플러스 + 청약홈 |
| `mbtireallove` | https://mbtireallove.tistory.com | MBTI 궁합 시리즈 | LLM 자체 생성 |
| `startupgrantnote` | https://startupgrantnote.tistory.com | K-Startup 창업지원금 공고 분석 | K-Startup OpenAPI |

## 핵심 명령어

```bash
# 패키지 설치
pip install -r requirements.txt
playwright install chromium

# 파이프라인 단계별 실행
python agents/planner_agent.py --blog llmenginehistory                     # LH 청약플러스 수집
python agents/planner_agent.py --blog llmenginehistory --source applyhome  # 청약홈 수집
python agents/planner_agent.py --blog startupgrantnote                     # K-Startup OpenAPI 수집
python agents/planner_agent.py --blog mbtireallove                         # MBTI suggestions → planned 승인
python agents/planner_agent.py --blog mbtireallove --suggest               # MBTI 새 주제 제안만

python agents/writer_agent.py --blog {blog}             # 글 초안 생성 (1건)
python agents/writer_agent.py --blog {blog} --dry-run   # 미리보기만 (발행 X)
SERVER_MODE=1 python agents/publisher_agent.py --blog {blog}  # 티스토리 발행

# 대시보드 (EC2)
source venv/bin/activate && nohup python dashboard.py > dashboard.log 2>&1 &

# 카카오 로그인 세션 갱신 (로컬에서 실행 → browser_data 생성 후 EC2 업로드)
python setup_browser.py
```

## 아키텍처

### 파이프라인 흐름

```
[수집] lh_scraper.py / applyhome_scraper.py / kstartup_scraper.py
    ↓ notice_id, notice_name, PDF, 상세텍스트
[기획] planner_agent.py
    → blogs/{blog}/tasks/planned/{task_id}.md  (YAML frontmatter + 마크다운 본문)
[집필] writer_agent.py
    → articles/{blog}/draft/{task_id}.html     (<!-- TITLE: ... --> + HTML)
    → blogs/{blog}/tasks/writing/{task_id}.md  (planned → writing 이동)
[발행] publisher_agent.py (Playwright + Tistory)
    → blogs/{blog}/tasks/published/{task_id}.md
    → articles/{blog}/published/{task_id}.html
```

Task 파일은 `planned → writing → published/failed` 폴더를 이동하며 상태를 추적한다.

### Task 파일 포맷

`blogs/{blog}/tasks/planned/*.md`:
```
---
task_id: 20260615_001
status: planned
notice_id: 0000012345
notice_name: OO지구 분양
housing_source: LH  # 또는 청약홈, K-Startup
supply_type: 분양
region: 서울
apply_end: 2026-07-14
...
---
## 소득자산기준
(HTML 표)

## 배점기준
```텍스트```
```

### 주요 모듈

| 파일 | 역할 |
|------|------|
| `agents/planner_agent.py` | 스크래퍼 호출 → LLM 분석 → Task 생성, 중복 제거 |
| `agents/writer_agent.py` | Task 읽기 → LLM HTML 생성, `--dry-run`으로 미리보기만 생성 |
| `agents/publisher_agent.py` | Playwright로 티스토리 발행 (썸네일 업로드, PDF 첨부) |
| `tools/lh_scraper.py` | LH 청약플러스 Playwright 스크래퍼. **분양(mi=1027)만** 수집 |
| `tools/applyhome_scraper.py` | 청약홈 — 목록은 Playwright, 상세는 requests AJAX API |
| `tools/kstartup_scraper.py` | K-Startup OpenAPI 스크래퍼. 사업화·서울/경기만 수집 |
| `tools/tistory_client.py` | 티스토리 CRUD 클라이언트. PUT 시 `PROTECTED_HTML_MARKERS` 보존 필수 |
| `tools/market_price.py` | 국토교통부 실거래가 API (`MOLIT_API_KEY` 없으면 조용히 None 반환) |
| `tools/thumbnail_gen.py` | 썸네일 이미지 생성 |
| `tools/pdf_parser.py` | PDF 배점 기준 페이지 텍스트 추출 |
| `dashboard.py` | Flask 대시보드 (포트 5001), `--dry-run` 미리보기 트리거 포함 |

### 블로그 설정 구조

```
blogs/{blog}/
├── config.md          # blog_url, series_default, title_prefix 등 YAML
├── writing_guide.md   # 글쓰기 가이드 (LLM 프롬프트에 삽입)
├── guides/            # supply_type별 가이드 (llmenginehistory만 보유)
├── memory/            # history.md, decisions.md, metrics.md (mbtireallove만 보유)
└── tasks/
    ├── planned/       # 기획 완료, 집필 대기
    ├── writing/       # 집필 중
    ├── published/     # 발행 완료
    ├── failed/        # 발행 실패
    └── suggestions/   # 주제 제안 (mbtireallove만 사용, planner가 planned로 승인)
```

## EC2 크론탭

```
# mbtireallove — 하루 5개 (08,10,12,14,16시 writer+publisher)
0 8-16/2 * * *  git pull && writer --blog mbtireallove && publisher --blog mbtireallove && git_sync

# mbtireallove planner — 07:30 (suggestions → planned 자동 승인)
30 7 * * *      planner --blog mbtireallove && git_sync

# llmenginehistory — 06시 LH planner, 07시 청약홈 planner, 09-12시 writer+publisher
0 6 * * *       planner --blog llmenginehistory
0 7 * * *       planner --blog llmenginehistory --source applyhome
0 9-12 * * *    writer + publisher --blog llmenginehistory && git_sync

# startupgrantnote — 06:30 planner, 09:30/11:30/13:30/15:30 writer+publisher (하루 4개)
30 6 * * *      planner --blog startupgrantnote && git_sync
30 9,11,13,15 * * *  writer + publisher --blog startupgrantnote && git_sync
```

모든 크론은 `git pull` 선행 → 작업 → `bash git_sync.sh` 후행 패턴.

## 핵심 주의사항

### 티스토리 PUT 시 보호 요소
본문 수정(`update_post`) 시 아래 HTML이 반드시 보존되어야 한다:
- `공고문 원본 PDF` — PDF 다운로드 버튼
- `안전마진 분석` — 안전마진 분석 섹션

소급 스크립트(`apply_*.py`) 작성 전 `tools/tistory_client.py`의 `PROTECTED_HTML_MARKERS` 확인.

### 수집 범위 제한
- LH 스크래퍼: **임대 공고(mi=1026) 절대 수집 금지**. 행복주택·국민임대·영구임대·매입임대 모두 제외.
- 청약홈 APT 분양: **민영만** (국민/공공주택은 LH에서 처리).
- llmenginehistory 대상 지역: 서울, 경기, 인천.
- startupgrantnote(`kstartup_scraper.py`): **서울·경기만** (`TARGET_REGIN_KW`). 전국 제외.

### 중복 제거
`notice_id` 또는 `notice_name` 중 하나라도 기존에 있으면 스킵 (소스가 달라도 크로스 중복 방지).  
`get_next_task_id()`: 파일 수가 아닌 **최대 번호 기준**으로 채번.

### 카카오 로그인 세션
`browser_data/` 폴더에 Playwright persistent context 쿠키 저장. 세션 만료 시 로컬에서 `setup_browser.py` 실행 후 EC2에 자동 업로드됨. `SERVER_MODE=1` 환경변수 없으면 publisher가 headed 브라우저로 실행 시도함.

### 티스토리 15개 제한
무료 블로그는 공개 글 15개 초과 시 임시저장됨. publisher는 "완료" 출력하지만 실제 발행 안 될 수 있음.

### Python 버전
서버는 Python 3.9. walrus operator(`:=`), `dict | dict` 병합 연산자 사용 금지.

### data/ 폴더
`.gitignore` 대상. PDF 원본 저장 경로: `data/{blog}/notices/{notice_id}/original.pdf`. 이미 있으면 상세 페이지 접속 자체 스킵.

### 서버 Playwright 옵션
서버에서 Playwright 실행 시 `--disable-dev-shm-usage --disable-gpu` 플래그 필수.

## 환경변수 (.env)

```
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4-mini
KAKAO_EMAIL=...
KAKAO_PASSWORD=...
MOLIT_API_KEY=...   # 국토교통부 실거래가 API (없으면 안전마진 분석 생략)
```
