# a2aWriter — AI 청약 인사이트 자동 발행 시스템

> **Planner → Writer → Publisher** 3개 Agent가 협업하는 AI 블로그 자동화 시스템.  
> 서울/경기/인천 분양 청약 공고를 수집·해설하여 티스토리에 자동 발행한다.

---

## 운영 현황

| 항목 | 내용 |
|------|------|
| 블로그 | [서울/경기 청약 인사이트](https://llmenginehistory.tistory.com) |
| 수집 소스 | LH 청약플러스(분양 mi=1027) + 청약홈(APT분양·오피스텔·잔여세대) |
| 대상 지역 | 서울 / 경기 / 인천 |
| 발행 글 형식 | AI 썸네일 + PDF 다운로드 버튼 + 공고 해설 본문 |
| EC2 서버 | 13.61.144.167 (Amazon Linux, Asia/Seoul KST) |

---

## 시스템 구조

```
[Planner Agent]  — agents/planner_agent.py
  ├─ LH 청약플러스 / 청약홈 공고 수집 (Playwright + requests)
  ├─ 중복 제거 후 Task 파일 생성
  └─ → blogs/llmenginehistory/tasks/planned/*.md

[Writer Agent]   — agents/writer_agent.py
  ├─ planned Task 소비
  ├─ Azure OpenAI로 HTML 해설 글 생성
  └─ → articles/llmenginehistory/draft/{task_id}.html

[Publisher Agent] — agents/publisher_agent.py
  ├─ AI 썸네일 생성 (gpt-image-2)
  ├─ 발행 모달에서 대표이미지 설정
  ├─ 티스토리 공개 발행 (Playwright)
  ├─ PDF 공고문 업로드 + 본문 다운로드 버튼 삽입
  └─ → tasks/published/ (성공) | tasks/failed/ (실패)
```

---

## 폴더 구조

```
a2aWriter/
├── agents/
│   ├── planner_agent.py      # 공고 수집 + Task 생성
│   ├── writer_agent.py       # 해설 글 생성 (HTML)
│   └── publisher_agent.py    # 티스토리 발행 + 썸네일 + PDF
│
├── tools/
│   ├── lh_scraper.py         # LH 청약플러스 스크래퍼 (분양만)
│   ├── applyhome_scraper.py  # 청약홈 스크래퍼
│   ├── pdf_parser.py         # PDF 파싱
│   ├── thumbnail_gen.py      # gpt-image-2 썸네일 생성
│   └── tistory_client.md     # 티스토리 연동 노하우 문서
│
├── blogs/llmenginehistory/
│   ├── config.md             # 블로그 설정 (URL 등)
│   ├── writing_guide.md      # 작성 규칙
│   ├── guides/
│   │   ├── sale.md           # 공공분양 가이드
│   │   └── general.md        # 일반 공고 가이드
│   └── tasks/
│       ├── planned/          # 발행 대기 Task
│       ├── writing/          # Writer 처리 중
│       ├── published/        # 발행 완료
│       └── failed/           # 발행 실패
│
├── articles/llmenginehistory/
│   ├── draft/                # Writer 초안 HTML (gitignore)
│   ├── published/            # 발행본 HTML
│   └── summary/              # 본문 요약 텍스트
│
├── data/                     # PDF 원본 + 썸네일 캐시 (gitignore)
│   └── llmenginehistory/
│       ├── notices/{id}/     # 공고별 PDF + filename.txt
│       └── thumbnails/       # 생성된 썸네일 PNG 캐시
│
├── browser_data/             # Playwright 카카오 세션 쿠키 (gitignore)
├── dashboard.py              # Flask 대시보드 (포트 5001)
├── apply_thumbnails.py       # 기존 글 대표이미지 소급 적용
├── apply_pdf_attachments.py  # 기존 글 PDF 소급 업로드
└── .env                      # 환경변수 (gitignore)
```

---

## 크론탭 (EC2 서버)

```bash
# LH 청약플러스 수집 — 매일 06시
0 6 * * * cd ~/a2aWriter && source venv/bin/activate && python agents/planner_agent.py --blog llmenginehistory >> cron.log 2>&1 && bash git_sync.sh >> cron.log 2>&1

# 청약홈 수집 — 매일 07시
0 7 * * * cd ~/a2aWriter && source venv/bin/activate && python agents/planner_agent.py --blog llmenginehistory --source applyhome >> cron.log 2>&1 && bash git_sync.sh >> cron.log 2>&1

# Writer + Publisher — 매일 09~12시 (시간당 1개)
0 9-12 * * * cd ~/a2aWriter && source venv/bin/activate && python agents/writer_agent.py --blog llmenginehistory >> cron.log 2>&1 && SERVER_MODE=1 python agents/publisher_agent.py --blog llmenginehistory >> cron.log 2>&1 && bash git_sync.sh >> cron.log 2>&1
```

---

## 실행 방법

```bash
# 환경 활성화
source venv/bin/activate          # 서버 (Linux)
venv\Scripts\activate             # 로컬 (Windows)

# 공고 수집 (Task 생성)
python agents/planner_agent.py --blog llmenginehistory
python agents/planner_agent.py --blog llmenginehistory --source applyhome

# 글 작성 (1건)
python agents/writer_agent.py --blog llmenginehistory

# 발행 (썸네일 + PDF 포함)
SERVER_MODE=1 python agents/publisher_agent.py --blog llmenginehistory

# 대시보드
python dashboard.py   # http://localhost:5001
```

---

## 발행 글 구조

```
[썸네일 이미지]          ← gpt-image-2 생성, 대표이미지 자동 설정
[PDF 다운로드 버튼]      ← 공고문 원본 PDF
[기본 정보 표]
[사업 개요]
[분양가 + 평당가]
[청약 조건 + 소득기준 표]
[청약 일정 표]
```

---

## 카카오 세션 갱신 (만료 시)

```powershell
# 로컬에서 실행
cd C:\Users\user\Downloads\claude
python setup_browser.py
git add browser_data/ && git push
```

---

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `KAKAO_EMAIL` | 카카오 로그인 이메일 |
| `KAKAO_PASSWORD` | 카카오 비밀번호 |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 엔드포인트 |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API 키 |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | 텍스트 모델명 (gpt-5.4-mini 등) |

---

## 주의사항

- **티스토리 무료 15개 제한**: 초과 시 임시저장됨
- **임대 공고 수집 안 함**: LH mi=1026(임대) 완전 제외, 분양(mi=1027)만
- **data/ gitignore**: PDF, 썸네일 캐시는 서버 로컬에만 존재
- **browser_data/ gitignore**: 카카오 쿠키 포함, 공개 금지
