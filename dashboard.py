"""
대시보드 — a2aWriter 편집국 현황판

EC2에서 실행: python dashboard.py
접속: http://<EC2_IP>:5001
"""

import re
import math
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

TASKS_PLANNED     = Path("tasks/planned")
TASKS_WRITING     = Path("tasks/writing")
TASKS_PUBLISHED   = Path("tasks/published")
TASKS_FAILED      = Path("tasks/failed")
TASKS_SUGGESTIONS = Path("tasks/suggestions")
ARTICLES_SUMMARY  = Path("articles/summary")
DAILY_RATE        = 10


def parse_task(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = {
        "task_id": path.stem, "topic": path.stem,
        "series": "-", "created_at": "-",
        "priority": "medium", "template": "default",
        "type": "단편", "parts": "1", "intention": "",
    }
    parts = text.split("---")
    if len(parts) >= 3:
        for line in parts[1].strip().splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                data[k.strip()] = v.strip()
        body = "---".join(parts[2:]).strip()
        data["intention"] = re.sub(r"^#+\s*.*$", "", body, flags=re.MULTILINE).strip()
    return data


def load_tasks(folder: Path) -> list:
    if not folder.exists():
        return []
    return sorted([parse_task(p) for p in folder.glob("*.md")], key=lambda x: x["task_id"])


def get_summary(task_id: str) -> str:
    f = ARTICLES_SUMMARY / f"{task_id}.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>a2aWriter 편집국</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
  background: #f8fafc;
  color: #0f172a;
  min-height: 100vh;
  font-size: 14px;
}

/* ── Header ── */
header {
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  padding: 0 32px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.logo { font-size: 17px; font-weight: 800; color: #6366f1; letter-spacing: -.5px; }
.logo em { color: #0f172a; font-style: normal; }
.live { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; animation: blink 2s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }
.header-right { margin-left: auto; color: #94a3b8; font-size: 12px; }

/* ── Layout ── */
.container { max-width: 1080px; margin: 0 auto; padding: 28px 20px; }

/* ── KPI ── */
.kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 16px; }
@media(max-width:700px){ .kpi-grid{ grid-template-columns:repeat(2,1fr); } }
.kpi {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 18px 20px;
}
.kpi-label { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
.kpi-value { font-size: 30px; font-weight: 900; line-height: 1; }
.kpi-sub { font-size: 11px; color: #94a3b8; margin-top: 5px; }
.kpi.danger .kpi-value { color: #ef4444; }
.kpi.warn   .kpi-value { color: #f59e0b; }
.kpi.ok     .kpi-value { color: #22c55e; }
.kpi.blue   .kpi-value { color: #6366f1; }

/* ── Progress ── */
.progress-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 24px;
}
.prog-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.prog-title { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: .06em; }
.prog-pct { font-size: 22px; font-weight: 800; color: #6366f1; }
.bar-bg { background: #f1f5f9; border-radius: 99px; height: 7px; }
.bar-fill { background: linear-gradient(90deg,#a5b4fc,#6366f1); height: 7px; border-radius: 99px; transition: width .6s ease; }
.prog-foot { display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; margin-top: 6px; }

/* ── Tabs ── */
.tabs { display: flex; gap: 2px; border-bottom: 1.5px solid #e2e8f0; margin-bottom: 20px; }
.tab-btn {
  padding: 10px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1.5px;
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: color .15s;
  white-space: nowrap;
}
.tab-btn:hover { color: #475569; }
.tab-btn.active { color: #6366f1; border-bottom-color: #6366f1; }
.cnt {
  background: #f1f5f9; color: #64748b;
  font-size: 11px; font-weight: 700;
  padding: 1px 8px; border-radius: 99px;
}
.tab-btn.active .cnt { background: #e0e7ff; color: #6366f1; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ── Card/Table ── */
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th {
  text-align: left;
  font-size: 11px; font-weight: 600;
  color: #94a3b8; text-transform: uppercase; letter-spacing: .05em;
  padding: 11px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}
tbody td { padding: 11px 16px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: #fafbff; cursor: default; }

.badge { display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.b-series  { background: #e0e7ff; color: #6366f1; }
.b-pub     { background: #dcfce7; color: #16a34a; }
.b-high    { background: #fef3c7; color: #b45309; }
.b-medium  { background: #f1f5f9; color: #64748b; }
.b-low     { background: #f1f5f9; color: #94a3b8; }
.num { color: #cbd5e1; font-size: 12px; }
.dday-ok   { font-size: 12px; color: #94a3b8; }
.dday-soon { font-size: 12px; color: #f59e0b; font-weight: 600; }

/* ── Summary row ── */
.sum-row { display: none; }
.sum-row.open { display: table-row; }
.sum-row td { padding: 10px 16px 14px 36px; background: #f8fafc; }
.sum-text {
  font-size: 12px; color: #475569; line-height: 1.75;
  border-left: 3px solid #c7d2fe;
  padding-left: 12px;
}
.expand-btn {
  background: none; border: none; cursor: pointer;
  color: #94a3b8; font-size: 12px;
  padding: 2px 7px; border-radius: 5px;
  transition: all .12s;
}
.expand-btn:hover { background: #f1f5f9; color: #6366f1; }

/* ── Suggest tab ── */
.sugg-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 16px;
  border-bottom: 1px solid #e2e8f0;
}
.sugg-toolbar-title { font-size: 13px; font-weight: 600; color: #475569; }
.btn-primary {
  background: #6366f1; color: #fff;
  border: none; border-radius: 8px;
  padding: 7px 16px; font-size: 13px; font-weight: 600;
  cursor: pointer; display: flex; align-items: center; gap: 6px;
  transition: background .15s;
}
.btn-primary:hover { background: #4f46e5; }
.btn-primary:disabled { background: #a5b4fc; cursor: not-allowed; }
.btn-ok  { background: #dcfce7; color: #16a34a; border: none; border-radius: 7px; padding: 5px 13px; font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-ok:hover { background: #bbf7d0; }
.btn-no  { background: #fee2e2; color: #ef4444; border: none; border-radius: 7px; padding: 5px 13px; font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-no:hover { background: #fecaca; }
.intent { font-size: 11px; color: #64748b; max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty { padding: 52px 20px; text-align: center; color: #94a3b8; font-size: 13px; line-height: 2; }

.spinner { display: inline-block; width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.5); border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<header>
  <div class="logo">a2a<em>Writer</em></div>
  <div class="live"></div>
  <span style="color:#94a3b8;font-size:12px;">편집국 대시보드</span>
  <span class="header-right">{{ now }} KST</span>
</header>

<div class="container">

  <!-- KPI -->
  <div class="kpi-grid">
    <div class="kpi {{ dday_class }}">
      <div class="kpi-label">소재 소멸까지</div>
      <div class="kpi-value">D-{{ dday }}</div>
      <div class="kpi-sub">{{ depletion_date }} 예상</div>
    </div>
    <div class="kpi blue">
      <div class="kpi-label">대기 소재</div>
      <div class="kpi-value">{{ planned_count }}</div>
      <div class="kpi-sub">하루 {{ daily_rate }}개 발행</div>
    </div>
    <div class="kpi ok">
      <div class="kpi-label">발행 완료</div>
      <div class="kpi-value">{{ published_count }}</div>
      <div class="kpi-sub">총 {{ total_count }}개 중</div>
    </div>
    <div class="kpi {% if failed_count > 0 %}warn{% else %}ok{% endif %}">
      <div class="kpi-label">실패 / 작성 중</div>
      <div class="kpi-value">{{ failed_count }}/{{ writing_count }}</div>
      <div class="kpi-sub">failed / writing</div>
    </div>
  </div>

  <!-- Progress -->
  <div class="progress-card">
    <div class="prog-header">
      <span class="prog-title">전체 발행 진행률</span>
      <span class="prog-pct">{{ progress_pct }}%</span>
    </div>
    <div class="bar-bg"><div class="bar-fill" style="width:{{ progress_pct }}%"></div></div>
    <div class="prog-foot">
      <span>{{ published_count }}개 발행</span>
      <span>{{ planned_count }}개 남음</span>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab-btn active" data-tab="planned">대기 소재 <span class="cnt">{{ planned_count }}</span></button>
    <button class="tab-btn" data-tab="published">발행 완료 <span class="cnt">{{ published_count }}</span></button>
    <button class="tab-btn" data-tab="suggest">편집장 승인 <span class="cnt">{{ suggestions|length }}</span></button>
  </div>

  <!-- Tab: 대기 소재 -->
  <div id="tab-planned" class="tab-pane active">
    <div class="card">
      <table>
        <thead><tr><th width="40">#</th><th>주제</th><th>시리즈</th><th>예상 발행일</th></tr></thead>
        <tbody>
          {% for i, t in planned_tasks %}
          <tr>
            <td class="num">{{ i }}</td>
            <td>{{ t.topic }}</td>
            <td><span class="badge b-series">{{ t.series }}</span></td>
            <td class="{{ 'dday-soon' if i <= daily_rate else 'dday-ok' }}">
              +{{ (i-1)//daily_rate }}일
              ({{ (today + timedelta(days=(i-1)//daily_rate)).strftime('%m/%d') }})
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab: 발행 완료 -->
  <div id="tab-published" class="tab-pane">
    <div class="card">
      <table>
        <thead><tr><th>상태</th><th>주제</th><th>시리즈</th><th>ID</th><th width="80"></th></tr></thead>
        <tbody>
          {% for t in published_tasks %}
          <tr>
            <td><span class="badge b-pub">발행</span></td>
            <td>{{ t.topic }}</td>
            <td><span class="badge b-series">{{ t.series }}</span></td>
            <td style="color:#94a3b8;font-size:12px;">{{ t.task_id }}</td>
            <td>
              {% if t.summary %}
              <button class="expand-btn" onclick="toggleSummary('{{ t.task_id }}')">▼ 요약</button>
              {% else %}<span style="color:#e2e8f0;font-size:11px;">-</span>{% endif %}
            </td>
          </tr>
          {% if t.summary %}
          <tr class="sum-row" id="sum-{{ t.task_id }}">
            <td colspan="5"><div class="sum-text">{{ t.summary }}</div></td>
          </tr>
          {% endif %}
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab: 편집장 승인 -->
  <div id="tab-suggest" class="tab-pane">
    <div class="card">
      <div class="sugg-toolbar">
        <span class="sugg-toolbar-title">AI 기획 제안 — 승인하면 대기열에 추가됩니다</span>
        <button class="btn-primary" id="suggest-btn" onclick="requestSuggest()">
          ✨ 새 주제 기획 요청
        </button>
      </div>
      <table>
        <thead>
          <tr><th>주제</th><th>시리즈</th><th>형태</th><th>우선순위</th><th width="140"></th></tr>
        </thead>
        <tbody id="suggest-body">
          {% if suggestions %}
            {% for t in suggestions %}
            <tr id="sugg-{{ t.task_id }}" style="cursor:pointer;" onclick="toggleOutline('{{ t.task_id }}')">
              <td>
                <strong>{{ t.topic }}</strong>
                <div style="font-size:11px;color:#94a3b8;margin-top:2px;">▼ 클릭해서 개요 보기</div>
              </td>
              <td><span class="badge b-series">{{ t.series }}</span></td>
              <td>
                {% set ctype = t.get('type', '단편') %}
                {% set parts = t.get('parts', 1)|int %}
                <span class="badge {{ 'b-high' if ctype == '시리즈' else 'b-medium' }}">
                  {{ ctype }}{% if ctype == '시리즈' and parts > 1 %} {{ parts }}부작{% endif %}
                </span>
              </td>
              <td><span class="badge b-{{ t.priority }}">{{ t.priority }}</span></td>
              <td onclick="event.stopPropagation()" style="display:flex;gap:6px;padding:10px 16px;">
                <button class="btn-ok" onclick="approve('{{ t.task_id }}')">✅ 승인</button>
                <button class="btn-no" onclick="reject('{{ t.task_id }}')">✕</button>
              </td>
            </tr>
            <tr class="sum-row" id="outline-{{ t.task_id }}">
              <td colspan="5">
                <div class="sum-text" style="white-space:pre-wrap;">{{ t.intention }}</div>
              </td>
            </tr>
            {% endfor %}
          {% else %}
          <tr id="empty-row">
            <td colspan="5" class="empty">
              제안된 주제가 없습니다.<br>위 버튼을 눌러 AI에게 새 주제 기획을 요청해보세요.
            </td>
          </tr>
          {% endif %}
        </tbody>
      </table>
    </div>
  </div>

</div>

<script>
// 탭 전환
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// 요약 / 개요 펼치기
function toggleSummary(id) {
  const row = document.getElementById('sum-' + id);
  if (row) row.classList.toggle('open');
}
function toggleOutline(id) {
  const row = document.getElementById('outline-' + id);
  if (row) row.classList.toggle('open');
}

// 새 주제 제안 요청
async function requestSuggest() {
  const btn = document.getElementById('suggest-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 생성 중...';
  try {
    const res = await fetch('/api/suggest', { method: 'POST' });
    const data = await res.json();
    if (data.ok) { location.reload(); }
    else { alert('오류: ' + (data.error || '알 수 없는 오류')); }
  } catch(e) {
    alert('요청 실패: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '✨ 새 주제 제안 요청';
  }
}

// 승인
async function approve(id) {
  const res = await fetch('/api/approve/' + id, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('sugg-' + id)?.remove();
    checkEmpty();
  } else { alert('오류: ' + (data.error || '')); }
}

// 거절
async function reject(id) {
  const res = await fetch('/api/reject/' + id, { method: 'POST' });
  if ((await res.json()).ok) {
    document.getElementById('sugg-' + id)?.remove();
    checkEmpty();
  }
}

function checkEmpty() {
  const rows = document.querySelectorAll('#suggest-body tr[id^="sugg-"]');
  if (rows.length === 0) {
    document.getElementById('suggest-body').innerHTML =
      '<tr id="empty-row"><td colspan="5" class="empty">제안된 주제가 없습니다.<br>위 버튼을 눌러 AI에게 새 주제를 제안받아 보세요.</td></tr>';
  }
}

// 60초마다 자동 갱신
setTimeout(() => location.reload(), 60000);
</script>

</body>
</html>
"""


@app.route("/")
def index():
    planned     = load_tasks(TASKS_PLANNED)
    published   = load_tasks(TASKS_PUBLISHED)
    writing     = load_tasks(TASKS_WRITING)
    failed      = load_tasks(TASKS_FAILED)
    suggestions = load_tasks(TASKS_SUGGESTIONS)

    total = len(planned) + len(published) + len(writing) + len(failed)
    progress_pct = round(len(published) / total * 100) if total else 0

    dday = math.ceil(len(planned) / DAILY_RATE) if planned else 0
    today = datetime.now().date()
    depletion_date = (datetime.now() + timedelta(days=dday)).strftime("%Y년 %m월 %d일")
    dday_class = "danger" if dday <= 3 else ("warn" if dday <= 7 else "ok")

    published_with_summary = [
        {**t, "summary": get_summary(t["task_id"])}
        for t in reversed(published)
    ]

    return render_template_string(
        TEMPLATE,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        today=today,
        timedelta=timedelta,
        planned_tasks=list(enumerate(planned, 1)),
        published_tasks=published_with_summary,
        suggestions=suggestions,
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


@app.route("/api/suggest", methods=["POST"])
def api_suggest():
    try:
        result = subprocess.run(
            ["venv/bin/python", "agents/planner_agent.py", "--suggest"],
            capture_output=True, text=True, timeout=90,
            cwd=Path(__file__).parent,
        )
        if result.returncode == 0:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": result.stderr or result.stdout}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/approve/<task_id>", methods=["POST"])
def api_approve(task_id):
    TASKS_SUGGESTIONS.mkdir(exist_ok=True)
    TASKS_PLANNED.mkdir(exist_ok=True)
    src = TASKS_SUGGESTIONS / f"{task_id}.md"
    if not src.exists():
        return jsonify({"ok": False, "error": "파일 없음"}), 404
    content = src.read_text(encoding="utf-8").replace("status: suggestion", "status: planned")
    (TASKS_PLANNED / f"{task_id}.md").write_text(content, encoding="utf-8")
    src.unlink()
    return jsonify({"ok": True})


@app.route("/api/reject/<task_id>", methods=["POST"])
def api_reject(task_id):
    src = TASKS_SUGGESTIONS / f"{task_id}.md"
    if src.exists():
        src.unlink()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
