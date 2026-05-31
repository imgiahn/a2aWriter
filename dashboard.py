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


@app.route("/api/status")
def api_status():
    def count(folder):
        return len(list(folder.glob("*.md"))) if folder.exists() else 0
    return jsonify({
        "planned":     count(TASKS_PLANNED),
        "published":   count(TASKS_PUBLISHED),
        "writing":     count(TASKS_WRITING),
        "failed":      count(TASKS_FAILED),
        "suggestions": count(TASKS_SUGGESTIONS),
    })


@app.route("/api/run_writer", methods=["POST"])
def api_run_writer():
    try:
        result = subprocess.run(
            ["venv/bin/python", "agents/writer_agent.py"],
            capture_output=True, text=True, timeout=120,
            cwd=Path(__file__).parent,
        )
        ok = result.returncode == 0
        return jsonify({"ok": ok, "output": result.stdout, "error": result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/run_publisher", methods=["POST"])
def api_run_publisher():
    try:
        result = subprocess.run(
            ["venv/bin/python", "agents/publisher_agent.py"],
            capture_output=True, text=True, timeout=180,
            cwd=Path(__file__).parent,
            env={**__import__("os").environ, "SERVER_MODE": "1"},
        )
        ok = result.returncode == 0
        return jsonify({"ok": ok, "output": result.stdout, "error": result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


DESK_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>편집국 에이전트</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d1117;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  min-height: 100vh;
  font-family: 'Courier New', monospace;
  color: #e2e8f0;
}
header {
  width: 100%; max-width: 960px;
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px;
}
.logo { font-size: 15px; font-weight: 800; color: #6366f1; }
.back-btn {
  margin-left: auto;
  background: #1e293b; color: #94a3b8;
  border: 1px solid #334155; border-radius: 6px;
  padding: 5px 12px; font-size: 12px; cursor: pointer;
  text-decoration: none;
}
.back-btn:hover { color: #e2e8f0; }
canvas {
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  border: 2px solid #1e293b;
  border-radius: 4px;
  cursor: pointer;
  max-width: 100%;
}
.hint { font-size: 11px; color: #334155; margin-top: 8px; }

/* Dialog */
.dialog-overlay {
  display: none;
  position: fixed; inset: 0;
  background: rgba(0,0,0,.5);
  z-index: 50;
  align-items: center; justify-content: center;
}
.dialog-overlay.open { display: flex; }
.dialog {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  padding: 24px;
  width: 340px;
  animation: pop .15s ease;
}
@keyframes pop { from { transform: scale(.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.dialog-avatar { font-size: 36px; margin-bottom: 8px; }
.dialog-name { font-size: 18px; font-weight: 800; }
.dialog-status { font-size: 12px; color: #64748b; margin-bottom: 16px; }
.dialog-stats {
  background: #0f172a; border-radius: 8px;
  padding: 12px; margin-bottom: 16px;
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
.stat-item .label { font-size: 10px; color: #64748b; text-transform: uppercase; }
.stat-item .val { font-size: 20px; font-weight: 800; color: #e2e8f0; }
.dialog-actions { display: flex; flex-direction: column; gap: 8px; }
.action-btn {
  width: 100%; padding: 10px;
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 700;
  cursor: pointer; transition: all .15s;
  font-family: inherit;
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-indigo { background: #6366f1; color: #fff; }
.btn-indigo:hover:not(:disabled) { background: #4f46e5; }
.btn-green  { background: #059669; color: #fff; }
.btn-green:hover:not(:disabled)  { background: #047857; }
.btn-ghost  { background: #1e293b; color: #64748b; border: 1px solid #334155; }
.btn-ghost:hover  { color: #e2e8f0; }
.dialog-output {
  background: #0f172a; border-radius: 6px;
  padding: 10px; margin-top: 10px;
  font-size: 11px; color: #94a3b8;
  max-height: 120px; overflow-y: auto;
  white-space: pre-wrap; display: none;
}
.spinner-inline {
  display: inline-block; width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .5s linear infinite;
  vertical-align: middle; margin-right: 4px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<header>
  <span class="logo">a2aWriter 편집국</span>
  <span style="color:#334155;font-size:12px;">— 에이전트 현황</span>
  <a href="/" class="back-btn">← 대시보드</a>
</header>

<canvas id="c" width="960" height="480"></canvas>
<p class="hint">캐릭터를 클릭하면 대화할 수 있습니다</p>

<!-- Dialog -->
<div class="dialog-overlay" id="overlay" onclick="closeDialog(event)">
  <div class="dialog" id="dialog">
    <div class="dialog-avatar" id="d-avatar">🧠</div>
    <div class="dialog-name" id="d-name">기획 Agent</div>
    <div class="dialog-status" id="d-status">대기 중</div>
    <div class="dialog-stats" id="d-stats"></div>
    <div class="dialog-actions" id="d-actions"></div>
    <pre class="dialog-output" id="d-output"></pre>
  </div>
</div>

<script>
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

const S = 3; // pixel scale (game px → screen px)
const W = canvas.width  / S; // 320 game px wide
const H = canvas.height / S; // 160 game px tall

// ── Palette ──────────────────────────────────────────
const P = {
  sky:   '#0d1117', ceil:  '#161b22', wallL: '#1a1f2e',
  floor: '#21262d', floorB:'#30363d', desk:  '#7c6f64',
  deskD: '#5a4a3a', paper: '#fffbf0', book1: '#ef4444',
  book2: '#3b82f6', book3: '#22c55e', plant: '#166534',
  plantL:'#22c55e', lamp:  '#fbbf24', windowB:'#1e3a5f',
  windowG:'#93c5fd', wall2: '#0d1117',
  // Planner
  pHat: '#4f46e5', pBody:'#6366f1', pSkin:'#fde68a',
  pPant:'#1e293b', pShoe:'#0f172a', pGlass:'#94a3b8',
  // Writer
  wHair:'#78350f', wBody:'#059669', wSkin:'#fde68a',
  wPant:'#1e40af', wShoe:'#0f172a', wPen: '#fbbf24',
  // Shared
  white:'#ffffff', _: null,
};

// ── Pixel sprite renderer ─────────────────────────────
function px(x, y, c) {
  if (!c) return;
  ctx.fillStyle = c;
  ctx.fillRect(x * S, y * S, S, S);
}
function rect(x, y, w, h, c) {
  ctx.fillStyle = c;
  ctx.fillRect(x * S, y * S, w * S, h * S);
}
function text(str, x, y, size, c, align) {
  ctx.fillStyle = c; ctx.font = `${size}px monospace`;
  ctx.textAlign = align || 'left';
  ctx.fillText(str, x * S, y * S);
}

// ── Sprite definitions (10w × 14h) ───────────────────
// _ = transparent
function plannerFrame(f) {
  const {pHat:H,pBody:B,pSkin:S,pPant:T,pShoe:E,pGlass:G,_:_} = P;
  const base = [
    [_,_,H,H,H,H,H,_,_,_], // 0 hat
    [_,H,H,H,H,H,H,H,_,_], // 1 hat brim
    [_,_,S,S,S,S,S,_,_,_], // 2 face
    [_,_,S,G,S,G,S,_,_,_], // 3 eyes+glasses
    [_,_,S,S,S,S,S,_,_,_], // 4 lower face
    [_,B,B,B,B,B,B,B,_,_], // 5 shirt
    [_,_,B,B,B,B,B,_,_,_], // 6 body
    [_,_,B,B,B,B,B,_,_,_], // 7 body
  ];
  const legs = f === 0 ? [
    [_,_,T,T,_,T,T,_,_,_], // 8 legs
    [_,_,T,T,_,T,T,_,_,_], // 9
    [_,_,E,E,_,T,T,_,_,_], // 10 left shoe forward
    [_,_,_,_,_,E,E,_,_,_], // 11
  ] : [
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,T,T,_,E,E,_,_,_], // right shoe forward
    [_,_,E,E,_,_,_,_,_,_],
  ];
  return [...base, ...legs];
}

function writerFrame(f) {
  const {wHair:H,wBody:B,wSkin:S,wPant:T,wShoe:E,wPen:Y,_:_} = P;
  const base = [
    [_,_,H,H,H,H,H,_,_,_], // 0 hair
    [_,_,S,S,S,S,S,_,_,_], // 1 face
    [_,_,S,'#000',S,'#000',S,_,_,_], // 2 eyes
    [_,_,S,S,'#d97706',S,S,_,_,_],   // 3 smile
    [_,_,S,S,S,S,S,_,_,_], // 4 face lower
    [_,B,B,B,B,B,B,B,Y,_], // 5 shirt + pencil held up
    [_,_,B,B,B,B,B,_,_,_], // 6 body
    [_,_,B,B,B,B,B,_,_,_], // 7
  ];
  const legs = f === 0 ? [
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,E,E,_,T,T,_,_,_],
    [_,_,_,_,_,E,E,_,_,_],
  ] : [
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,T,T,_,T,T,_,_,_],
    [_,_,T,T,_,E,E,_,_,_],
    [_,_,E,E,_,_,_,_,_,_],
  ];
  return [...base, ...legs];
}

function drawSprite(sprite, gx, gy, flipX) {
  const cols = sprite[0].length;
  sprite.forEach((row, ry) => {
    row.forEach((color, rx) => {
      if (!color) return;
      const drawX = flipX ? gx + (cols - 1 - rx) : gx + rx;
      px(drawX, gy + ry, color);
    });
  });
}

// ── Office background ─────────────────────────────────
function drawBg() {
  // Sky/ceiling
  rect(0, 0, W, 12, P.ceil);
  // Ceiling trim
  rect(0, 12, W, 2, '#0d2137');

  // Floor
  for (let x = 0; x < W; x += 4) {
    rect(x, 120, 4, H - 120, x % 8 === 0 ? P.floor : P.floorB);
  }
  // Floor highlight
  rect(0, 120, W, 1, '#30363d');

  // Back wall
  rect(0, 14, W, 106, P.wallL);

  // ── Left room: Planner ────────────────────────────
  // Room label
  text('[ PLANNER ROOM ]', 8, 9, 6, '#6366f1');

  // Window (left)
  rect(8, 20, 24, 18, P.windowB);
  rect(9, 21, 22, 16, P.windowG);
  rect(19, 21, 1, 16, P.windowB); // center bar
  rect(9, 29, 22, 1, P.windowB);  // horiz bar
  // Window glow
  ctx.fillStyle = 'rgba(147,197,253,0.07)';
  ctx.fillRect(9*S, 21*S, 22*S, 16*S);

  // Whiteboard
  rect(50, 20, 36, 22, '#e2e8f0');
  rect(51, 21, 34, 20, '#f8fafc');
  // Board lines (writing)
  rect(53, 25, 20, 1, '#94a3b8');
  rect(53, 28, 28, 1, '#94a3b8');
  rect(53, 31, 16, 1, '#94a3b8');
  rect(53, 34, 24, 1, '#94a3b8');
  // Board text hint
  text('decisions.md', 53, 24, 5, '#6366f1');

  // Desk (planner)
  rect(10, 100, 60, 6, P.desk);
  rect(10, 100, 60, 2, P.deskD);
  rect(11, 106, 4, 14, P.deskD); // leg L
  rect(64, 106, 4, 14, P.deskD); // leg R

  // Items on desk
  rect(13, 96, 10, 4, P.paper); // paper stack
  rect(15, 94, 8, 2, P.paper);
  rect(25, 97, 6, 3, '#c7d2fe');   // sticky note
  // Lamp
  rect(55, 87, 4, 13, '#475569'); // lamp stand
  rect(50, 84, 12, 4, P.lamp);    // lamp shade
  ctx.fillStyle = 'rgba(251,191,36,0.15)';
  ctx.fillRect(46*S, 87*S, 20*S, 20*S);

  // ── Divider wall ──────────────────────────────────
  rect(155, 14, 5, 106, '#0d1117');
  // Door frame
  rect(155, 75, 5, 45, '#1a1f2e');
  rect(156, 76, 3, 43, '#21262d'); // door opening

  // ── Right room: Writer ───────────────────────────
  text('[ WRITER ROOM ]', 168, 9, 6, '#059669');

  // Bookshelf
  rect(165, 20, 30, 55, '#5a4a3a');
  rect(166, 21, 28, 8, P.book1);
  rect(166, 30, 8, 8, P.book2);
  rect(175, 30, 9, 8, P.book3);
  rect(185, 30, 8, 8, P.book2);
  rect(166, 39, 10, 8, P.book3);
  rect(177, 39, 7, 8, P.book1);
  rect(166, 48, 28, 8, '#fbbf24');
  rect(166, 57, 9, 8, P.book1);
  rect(176, 57, 8, 8, P.book2);
  rect(185, 57, 8, 8, '#fbbf24');
  // Shelf dividers
  rect(166, 29, 28, 1, '#3d2e20');
  rect(166, 38, 28, 1, '#3d2e20');
  rect(166, 47, 28, 1, '#3d2e20');
  rect(166, 56, 28, 1, '#3d2e20');

  // Desk (writer)
  rect(200, 100, 70, 6, P.desk);
  rect(200, 100, 70, 2, P.deskD);
  rect(201, 106, 4, 14, P.deskD);
  rect(264, 106, 4, 14, P.deskD);

  // Items on writer's desk
  rect(203, 96, 12, 4, P.paper);
  rect(205, 94, 10, 2, P.paper);
  rect(219, 96, 8, 4, '#fca5a5');  // red paper
  rect(230, 94, 6, 2, P.wPen);     // pencil
  rect(250, 90, 8, 10, '#334155'); // monitor
  rect(251, 91, 6, 8, '#1e3a5f');
  rect(252, 92, 4, 6, '#93c5fd');  // screen glow
  rect(253, 105, 4, 2, '#334155'); // monitor stand

  // Plant (corner)
  rect(300, 95, 8, 5, '#374151'); // pot
  rect(302, 88, 4, 7, P.plant);
  rect(300, 82, 3, 7, P.plantL);
  rect(305, 80, 3, 9, P.plantL);
}

// ── Name bubble ───────────────────────────────────────
function drawBubble(gx, gy, name, color) {
  const w = name.length * 5 + 6;
  rect(gx - 1, gy - 10, w, 9, '#0d1117');
  ctx.fillStyle = color;
  ctx.font = '8px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(name, (gx + 2) * S, (gy - 3) * S);
}

// ── Agent state ───────────────────────────────────────
const agents = [
  {
    id: 'planner', name: '기획 Agent', emoji: '🧠', color: '#6366f1',
    x: 40, y: 106, vx: 0.3, frame: 0, ftimer: 0,
    patrol: [12, 130], facingL: false,
    w: 10, h: 12,
  },
  {
    id: 'writer', name: '작가 Agent', emoji: '✍️', color: '#059669',
    x: 220, y: 106, vx: -0.3, frame: 0, ftimer: 0,
    patrol: [162, 295], facingL: true,
    w: 10, h: 12,
  },
];

let status = { planned: 0, published: 0, writing: 0, failed: 0, suggestions: 0 };
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    status = await r.json();
  } catch(e) {}
}
fetchStatus();
setInterval(fetchStatus, 10000);

// ── Game loop ─────────────────────────────────────────
let last = 0;
function loop(ts) {
  const dt = Math.min(ts - last, 50); last = ts;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBg();

  agents.forEach(a => {
    // Move
    a.x += a.vx * (dt / 16);

    if (a.x <= a.patrol[0])      { a.x = a.patrol[0]; a.vx =  Math.abs(a.vx); }
    if (a.x >= a.patrol[1] - 10) { a.x = a.patrol[1] - 10; a.vx = -Math.abs(a.vx); }

    a.facingL = a.vx < 0;

    // Animate legs
    a.ftimer += dt;
    if (a.ftimer > 220) { a.ftimer = 0; a.frame ^= 1; }

    // Draw
    const sprite = a.id === 'planner'
      ? plannerFrame(a.frame)
      : writerFrame(a.frame);

    drawSprite(sprite, Math.round(a.x), a.y - 12, a.facingL);
    drawBubble(Math.round(a.x), a.y - 12, a.name, a.color);
  });

  // Status bar bottom
  rect(0, H - 10, W, 10, '#161b22');
  text(`대기: ${status.planned}  발행: ${status.published}  작성중: ${status.writing}  제안: ${status.suggestions}`, 6, H - 3, 6, '#64748b');
  text(new Date().toLocaleTimeString('ko-KR'), W - 46, H - 3, 6, '#334155');

  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

// ── Click detection ───────────────────────────────────
canvas.addEventListener('click', e => {
  const r   = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / r.width;
  const scaleY = canvas.height / r.height;
  const cx = (e.clientX - r.left) * scaleX / S;
  const cy = (e.clientY - r.top)  * scaleY / S;

  for (const a of agents) {
    const ax = Math.round(a.x), ay = a.y - 12;
    if (cx >= ax && cx <= ax + a.w && cy >= ay && cy <= ay + a.h + 12) {
      openDialog(a);
      return;
    }
  }
});

// ── Dialog ────────────────────────────────────────────
function openDialog(agent) {
  document.getElementById('d-avatar').textContent = agent.emoji;
  document.getElementById('d-name').textContent   = agent.name;
  document.getElementById('d-output').style.display = 'none';
  document.getElementById('d-output').textContent = '';

  if (agent.id === 'planner') {
    document.getElementById('d-status').textContent =
      `대기 중 · 제안 ${status.suggestions}개`;
    document.getElementById('d-stats').innerHTML = `
      <div class="stat-item"><div class="label">대기 소재</div><div class="val">${status.planned}</div></div>
      <div class="stat-item"><div class="label">AI 제안</div><div class="val">${status.suggestions}</div></div>
    `;
    document.getElementById('d-actions').innerHTML = `
      <button class="action-btn btn-indigo" onclick="runAction('suggest')">✨ 새 주제 기획 요청 (5개)</button>
      <button class="action-btn btn-ghost"  onclick="closeDialog()">✕ 닫기</button>
    `;
  } else {
    document.getElementById('d-status').textContent =
      `대기 중 · 발행 ${status.published}개 완료`;
    document.getElementById('d-stats').innerHTML = `
      <div class="stat-item"><div class="label">발행 완료</div><div class="val">${status.published}</div></div>
      <div class="stat-item"><div class="label">작성 중</div><div class="val">${status.writing}</div></div>
    `;
    document.getElementById('d-actions').innerHTML = `
      <button class="action-btn btn-green"  onclick="runAction('write_publish')">📝 지금 글 쓰고 발행하기</button>
      <button class="action-btn btn-ghost"  onclick="closeDialog()">✕ 닫기</button>
    `;
  }

  document.getElementById('overlay').classList.add('open');
}

function closeDialog(e) {
  if (e && e.target !== document.getElementById('overlay')) return;
  document.getElementById('overlay').classList.remove('open');
}

async function runAction(type) {
  const btns = document.querySelectorAll('.action-btn');
  btns.forEach(b => b.disabled = true);
  const outEl = document.getElementById('d-output');
  outEl.style.display = 'block';
  outEl.textContent = '실행 중...\n';

  try {
    if (type === 'suggest') {
      const r = await fetch('/api/suggest', { method: 'POST' });
      const d = await r.json();
      outEl.textContent = d.ok
        ? '✅ 기획 완료! 대시보드 [편집장 승인] 탭에서 확인하세요.'
        : '❌ 오류: ' + (d.error || '알 수 없는 오류');
    } else if (type === 'write_publish') {
      outEl.textContent = '📝 글 작성 중...\n';
      const r1 = await fetch('/api/run_writer', { method: 'POST' });
      const d1 = await r1.json();
      outEl.textContent += d1.output || d1.error || '';
      if (d1.ok) {
        outEl.textContent += '\n🚀 발행 중...\n';
        const r2 = await fetch('/api/run_publisher', { method: 'POST' });
        const d2 = await r2.json();
        outEl.textContent += d2.output || d2.error || '';
      }
    }
  } catch(e) {
    outEl.textContent += '오류: ' + e.message;
  } finally {
    btns.forEach(b => b.disabled = false);
    await fetchStatus();
  }
}
</script>
</body>
</html>"""


@app.route("/desk")
def desk():
    return render_template_string(DESK_TEMPLATE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
