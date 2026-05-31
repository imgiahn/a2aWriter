# a2aWriter — Agent-to-Agent 자동 블로그 시스템

> **기획자 Agent**가 주제를 설계하고, **작가 Agent**가 글을 쓰고 발행하는 자율 운영 블로그 시스템

---

## 현재 상태 (v1 — 작가 Agent)

MBTI 궁합 120개 조합을 Azure OpenAI로 생성해 티스토리에 자동 포스팅.

```
[작가 Agent]
  └─ MBTI 조합 목록에서 미발행 주제 선택
  └─ GPT로 궁합 분석 글 생성 (HTML)
  └─ Playwright로 티스토리 자동 발행 (공개)
  └─ 발행 기록 저장 (posted_combos.json)
```

**한계:** 120개 조합이 소진되면 더 이상 동작하지 않음.

---

## 목표 아키텍처 (v2 — Agent-to-Agent)

```
[기획자 Agent]  ──────────────────────────────────────────
  └─ 현재 블로그 성과 분석 (조회수, 댓글, 트렌드)
  └─ 새 콘텐츠 시리즈/주제 설계
       예) MBTI × 직업궁합 / MBTI × 연령대 / 별자리 × MBTI ...
  └─ 작업 큐에 새 주제 추가 (content_queue.json)
        │
        ▼
[작가 Agent]  ────────────────────────────────────────────
  └─ 큐에서 주제 꺼내기
  └─ GPT로 글 생성
  └─ 티스토리 자동 발행
  └─ 발행 완료 기록
```

**목표:** 기획자가 주제를 계속 공급 → 작가가 끊임없이 발행 → 사람 개입 없이 블로그 운영

---

## 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| v1.0 | 작가 Agent — MBTI 120 조합 자동 발행 | ✅ 완료 |
| v1.1 | EC2 서버 배포 + GitHub 연동 | ✅ 완료 |
| v1.2 | 크론탭으로 1시간 1개 자동 스케줄 | 🔜 다음 |
| v2.0 | 기획자 Agent — 콘텐츠 큐 설계 및 주제 생성 | 📋 예정 |
| v2.1 | 기획자-작가 Agent 연동 (content_queue.json) | 📋 예정 |
| v2.2 | 성과 분석 → 기획자 피드백 루프 | 📋 예정 |

---

## 프로젝트 구조

```
a2aWriter/
├── mbti_playwright_poster.py  # 작가 Agent (현재)
├── mbti_auto_poster.py        # 초기 버전 (레거시)
├── writing_guide.md           # 글 작성 가이드 (작가 프롬프트)
├── posted_combos.json         # 발행 완료 기록
├── requirements.txt
├── .env.example               # 환경변수 템플릿
└── .gitignore
```

### 앞으로 추가될 파일

```
a2aWriter/
├── planner_agent.py           # 기획자 Agent
├── content_queue.json         # 기획자 → 작가 작업 큐
└── analytics/                 # 성과 분석 모듈
```

---

## 환경 설정

`.env.example`을 복사해 `.env` 생성 후 키 입력:

```bash
cp .env.example .env
```

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

---

## 서버 업데이트 방법

```bash
cd ~/a2aWriter
git pull
source venv/bin/activate
```

---

## 실행

```bash
# 로컬 (수동)
python mbti_playwright_poster.py

# 서버 (헤드리스 모드)
SERVER_MODE=1 python mbti_playwright_poster.py
```

> 쿠키가 만료되면 로컬에서 재로그인 후 `tistory_cookies.json`을 서버에 업로드해야 함.
> ```bash
> scp -i giahn.pem tistory_cookies.json ec2-user@13.61.144.167:~/a2aWriter/
> ```
