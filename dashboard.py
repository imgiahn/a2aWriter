"""
대시보드 — a2aWriter 편집국 현황판

EC2에서 실행: python dashboard.py
접속: http://<EC2_IP>:5001
"""

import math
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template_string

app = Flask(__name__)

TASKS_PLANNED   = Path("tasks/planned")
TASKS_WRITING   = Path("tasks/writing")
TASKS_PUBLISHED = Path("tasks/published")
TASKS_FAILED    = Path("tasks/failed")
DAILY_RATE      = 10  # 크론탭 08~17시 정각마다 = 하루 최대 10개


def parse_task(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = {"task_id": path.stem, "topic": path.stem, "series": "-", "created_at": "-"}
    for line in text.splitlines():
        for key in ("task_id", "topic", "series", "created_at", "priority"):
            if line.startswith(f"{key}:"):
                data[key] = line.split(":", 1)[1].strip()
    return data


def load_tasks(folder: Path) -> list:
    if not folder.exists():
        return []
    return sorted([parse_task(p) for p in folder.glob("*.md")], key=lambda x: x["task_id"])


TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>a2aWriter 편집국</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }

  header { background: #1a1d27; border-bottom: 1px solid #2d3148; padding: 20px 32px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.3rem; font-weight: 700; color: #fff; }
  header .dot { width: 10px; height: 10px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 8px #22c55e; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }

  /* 상단 KPI 카드 */
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .kpi { background: #1a1d27; border: 1px solid #2d3148; border-radius: 12px; padding: 20px 24px; }
  .kpi .label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
  .kpi .value { font-size: 2.2rem; font-weight: 800; line-height: 1; }
  .kpi .sub { font-size: 0.8rem; color: #64748b; margin-top: 6px; }
  .kpi.danger .value { color: #f87171; }
  .kpi.warn   .value { color: #fbbf24; }
  .kpi.ok     .value { color: #34d399; }
  .kpi.blue   .value { color: #60a5fa; }

  /* 진행률 바 */
  .progress-wrap { background: #1a1d27; border: 1px solid #2d3148; border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; }
  .progress-wrap .label { font-size: 0.8rem; color: #94a3b8; margin-bottom: 10px; }
  .bar-bg { background: #2d3148; border-radius: 99px; height: 10px; }
  .bar-fill { background: linear-gradient(90deg, #6366f1, #8b5cf6); height: 10px; border-radius: 99px; transition: width .5s; }
  .progress-wrap .stats { display: flex; justify-content: space-between; font-size: 0.8rem; color: #64748b; margin-top: 8px; }

  /* 섹션 */
  .section { margin-bottom: 32px; }
  .section h2 { font-size: 0.9rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 14px; border-bottom: 1px solid #2d3148; padding-bottom: 10px; }

  /* 테이블 */
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th { text-align: left; color: #64748b; font-weight: 500; padding: 8px 12px; font-size: 0.75rem; text-transform: uppercase; }
  td { padding: 10px 12px; border-top: 1px solid #1e2235; }
  tr:hover td { background: #1e2235; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
  .badge-mbti { background: #1e3a5f; color: #60a5fa; }
  .badge-pub  { background: #14532d; color: #4ade80; }
  .idx { color: #475569; font-size: 0.75rem; }
  .dday { font-size: 0.75rem; color: #94a3b8; }
  .dday.soon { color: #fbbf24; }

  footer { text-align: center; color: #334155; font-size: 0.75rem; padding: 24px; }
</style>
</head>
<body>

<header>
  <div class="dot"></div>
  <h1>a2aWriter 편집국 대시보드</h1>
  <span style="margin-left:auto;font-size:.75rem;color:#475569">매 60초 자동 갱신 · {{ now }}</span>
</header>

<div class="container">

  <!-- KPI -->
  <div class="kpi-grid">
    <div class="kpi {{ dday_class }}">
      <div class="label">소재 소멸까지</div>
      <div class="value">D-{{ dday }}</div>
      <div class="sub">{{ planned_count }}개 잔여 · 하루 최대 {{ daily_rate }}개</div>
    </div>
    <div class="kpi blue">
      <div class="label">대기 중인 소재</div>
      <div class="value">{{ planned_count }}</div>
      <div class="sub">planned</div>
    </div>
    <div class="kpi ok">
      <div class="label">발행 완료</div>
      <div class="value">{{ published_count }}</div>
      <div class="sub">총 {{ total_count }}개 중</div>
    </div>
    <div class="kpi {% if failed_count > 0 %}warn{% else %}ok{% endif %}">
      <div class="label">실패 / 작성 중</div>
      <div class="value">{{ failed_count }} / {{ writing_count }}</div>
      <div class="sub">failed / writing</div>
    </div>
  </div>

  <!-- 진행률 -->
  <div class="progress-wrap">
    <div class="label">전체 발행 진행률</div>
    <div class="bar-bg"><div class="bar-fill" style="width:{{ progress_pct }}%"></div></div>
    <div class="stats">
      <span>{{ published_count }}개 발행 완료</span>
      <span>{{ progress_pct }}%</span>
      <span>{{ planned_count }}개 남음</span>
    </div>
  </div>

  <!-- 대기 소재 목록 -->
  <div class="section">
    <h2>대기 중인 소재 ({{ planned_count }}개) — 예상 소멸일 {{ depletion_date }}</h2>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>주제</th>
          <th>시리즈</th>
          <th>예상 발행일</th>
        </tr>
      </thead>
      <tbody>
        {% for i, t in planned_tasks %}
        <tr>
          <td class="idx">{{ i }}</td>
          <td>{{ t.topic }}</td>
          <td><span class="badge badge-mbti">{{ t.series }}</span></td>
          <td class="dday {% if i <= daily_rate %}soon{% endif %}">
            +{{ ((i-1) // daily_rate) }}일 후
            ({{ (today + timedelta(days=(i-1)//daily_rate)).strftime('%m/%d') }})
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- 최근 발행 -->
  <div class="section">
    <h2>최근 발행 완료 ({{ published_count }}개)</h2>
    <table>
      <thead>
        <tr><th>#</th><th>주제</th><th>시리즈</th><th>Task ID</th></tr>
      </thead>
      <tbody>
        {% for t in published_tasks[-10:]|reverse %}
        <tr>
          <td><span class="badge badge-pub">발행</span></td>
          <td>{{ t.topic }}</td>
          <td><span class="badge badge-mbti">{{ t.series }}</span></td>
          <td class="idx">{{ t.task_id }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>

<footer>a2aWriter · EC2 {{ now }} KST</footer>
</body>
</html>
"""


@app.route("/")
def index():
    planned   = load_tasks(TASKS_PLANNED)
    published = load_tasks(TASKS_PUBLISHED)
    writing   = load_tasks(TASKS_WRITING)
    failed    = load_tasks(TASKS_FAILED)

    total = len(planned) + len(published) + len(writing) + len(failed)
    progress_pct = round(len(published) / total * 100) if total else 0

    dday = math.ceil(len(planned) / DAILY_RATE)
    today = datetime.now().date()
    depletion_date = (datetime.now() + timedelta(days=dday)).strftime("%Y년 %m월 %d일")

    if dday <= 3:
        dday_class = "danger"
    elif dday <= 7:
        dday_class = "warn"
    else:
        dday_class = "ok"

    return render_template_string(
        TEMPLATE,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        today=today,
        timedelta=timedelta,
        planned_tasks=list(enumerate(planned, 1)),
        published_tasks=published,
        planned_count=len(planned),
        published_count=len(published),
        writing_count=len(writing),
        failed_count=len(failed),
        total_count=total,
        progress_pct=progress_pct,
        dday=dday,
        dday_class=dday_class,
        depletion_date=depletion_date,
        daily_rate=DAILY_RATE,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
