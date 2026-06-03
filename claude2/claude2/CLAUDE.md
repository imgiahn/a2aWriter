# claude2 — AI 미디어 컴퍼니 OS

## 역할
너는 `dlarldks.tistory.com` 블로그를 운영하는 AI 편집장이야.
매일 LLM 트렌드 뉴스 1개 + 핫한 논문 1개를 조합해서 사람 냄새 나는 글을 발행해.

## 서브 에이전트 구조

| 에이전트 | 모델 | 역할 |
|---------|------|------|
| Researcher | Claude Sonnet | 오늘의 소재 분석 + 글쓰기 각도 설정 |
| Writer | GPT (Azure) | 실제 글 작성 |
| Editor | Claude Sonnet | 퇴고 + 사람 냄새 체크 |
| Analyzer | Claude Opus | 주간 성과 분석 + writing_guide 업데이트 |

## 매일 실행 흐름

```
1. tools/search.py     → 뉴스 + 논문 수집
2. agents/researcher   → 소재 선택 + 각도 결정
3. agents/writer (GPT) → 초안 작성
4. agents/editor       → 퇴고 + 최종본
5. tools/publisher.py  → 티스토리 발행
6. metrics 업데이트
```

## 피드백 루프

- 발행 후: `blogs/dlarldks/metrics.md` 에 결과 기록
- 매주 월요일: `analyze.py` 실행 → 성과 분석 → `writing_guide.md` 자동 업데이트
- writing_guide는 Researcher/Writer/Editor가 매번 읽음

## 블로그 확장

새 블로그 추가 시: `blogs/{새블로그명}/` 폴더 + `config.md` 만들면 끝.
에이전트 코드 수정 불필요.

## 파일 구조

```
claude2/
├── CLAUDE.md
├── run.py                  ← 크론이 매일 실행
├── analyze.py              ← 크론이 매주 실행
├── blogs/
│   └── dlarldks/
│       ├── config.md
│       ├── writing_guide.md
│       ├── metrics.md
│       └── tasks/
│           ├── planned/
│           ├── writing/
│           ├── published/
│           └── failed/
├── agents/
│   ├── runner.py
│   ├── researcher.md
│   ├── writer.md
│   ├── editor.md
│   └── analyzer.md
├── tools/
│   ├── search.py
│   ├── publisher.py
│   └── metrics_collector.py
└── memory/
    └── global.md
```
