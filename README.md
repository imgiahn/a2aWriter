# a2aWriter — AI 편집국 자동 블로그 시스템

> **편집장(사람) + AI Agent**가 함께 운영하는 블로그 자동화 시스템.  
> Planner가 기획하고, Writer가 쓰고, Publisher가 발행한다.

---

## 시스템 구조

```
[편집장 (사람)]
  └─ 시리즈 승인 → memory/decisions.md
  └─ 성과 피드백 → memory/history.md

[Planner Agent]  → agents/planner_agent.py
  └─ memory/*.md 분석
  └─ 승인된 시리즈 기반 Task 생성
  └─ → tasks/planned/*.md

[Writer Agent]   → agents/writer_agent.py
  └─ tasks/planned/*.md 소비
  └─ Azure OpenAI로 글 생성
  └─ → articles/draft/{task_id}.html
  └─ → tasks/writing/ (이동)

[Publisher Agent] → agents/publisher_agent.py
  └─ articles/draft/*.html 발행
  └─ Playwright로 티스토리 공개 발행
  └─ → tasks/published/ (성공) | tasks/failed/ (실패)
```

**절대 원칙:** Agent끼리 직접 대화하지 않는다. 모든 협업은 Task 파일을 통한다.

---

## 폴더 구조

```
a2aWriter/
├── agents/
│   ├── planner_agent.py      # 기획 Agent (편집장 승인 기반 Task 생성)
│   ├── writer_agent.py       # 작성 Agent (Task → 초안 HTML)
│   └── publisher_agent.py    # 발행 Agent (초안 → 티스토리)
│
├── memory/
│   ├── history.md            # 장기 기억 (콘텐츠 반응 패턴)
│   ├── decisions.md          # 편집장 승인 기록
│   └── metrics.md            # 성과 데이터
│
├── tasks/
│   ├── planned/              # 대기 중인 Task
│   ├── writing/              # Writer 작업 중
│   ├── published/            # 발행 완료
│   └── failed/               # 발행 실패
│
├── articles/
│   ├── draft/                # 초안 HTML (git 미추적)
│   └── published/            # 발행본 HTML (git 미추적)
│
├── writing_guide.md          # Writer 기본 작성 가이드
└── .env.example              # 환경변수 템플릿
```

---

## Task 파일 형식

파일명: `tasks/planned/YYYYMMDD_NNN.md`

```markdown
---
task_id: 20260531_001
status: planned
topic: INTP ENFP 커플 궁합
series: mbti_relationship
priority: high
template: relationship_v1
created_by: planner_agent
created_at: 2026-05-31
---

# 기획 의도

ENFP 관련 콘텐츠 반응 좋음. 권태기 주제로 확장.
```

---

## 실행 방법

```bash
# 환경 활성화
source venv/bin/activate  # 서버
venv\Scripts\activate     # 로컬 Windows

# 1. Planner: Task 생성 (편집장 승인 후 planner_agent.py 내 approved_tasks 작성)
python agents/planner_agent.py

# 2. Writer: 초안 생성
python agents/writer_agent.py

# 3. Publisher: 티스토리 발행
SERVER_MODE=1 python agents/publisher_agent.py
```

---

## 서버 자동화

**크론탭:** 매일 08:00 ~ 17:00 KST, 정각마다 Writer → Publisher 자동 실행

```
0 8-17 * * * cd ~/a2aWriter && source venv/bin/activate && python agents/writer_agent.py >> cron.log 2>&1 && SERVER_MODE=1 python agents/publisher_agent.py >> cron.log 2>&1
```

**서버 코드 업데이트:**
```bash
cd ~/a2aWriter && git pull
```

**쿠키 만료 시** 로컬에서 갱신 후 재업로드:
```bash
scp -i giahn.pem tistory_cookies.json ec2-user@13.61.144.167:~/a2aWriter/
```

---

## 현재 상태 (2026-05-31 기준)

| 시리즈 | 전체 | 발행 완료 | 대기 중 |
|--------|------|-----------|---------|
| mbti_relationship | 120 | 63 | 58 |

---

## 로드맵

| 버전 | 내용 | 상태 |
|------|------|------|
| v1.0 | 작가 Agent — MBTI 120 조합 자동 발행 | ✅ 완료 |
| v1.1 | EC2 서버 배포 + GitHub 연동 + 크론탭 | ✅ 완료 |
| v2.0 | Agent-to-Agent 구조 설계 및 구현 | ✅ 완료 |
| v2.1 | Planner Agent — 트렌드 기반 자동 기획 | 📋 예정 |
| v2.2 | 성과 분석 → Planner 피드백 루프 | 📋 예정 |

---

## 환경 설정

```bash
cp .env.example .env
# .env 에 실제 키 입력
```

| 변수 | 설명 |
|------|------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 엔드포인트 |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API 키 |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | 배포 모델명 |
