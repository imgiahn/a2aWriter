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
<title>a2aWriter 편집국</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Noto+Sans+KR:wght@400;700&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #070b14;
  min-height: 100vh;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  font-family: 'Press Start 2P', monospace;
  color: #e2e8f0;
  overflow: hidden;
}

/* Star background */
body::before {
  content: '';
  position: fixed; inset: 0;
  background-image:
    radial-gradient(1px 1px at 10% 20%, #ffffff22, transparent),
    radial-gradient(1px 1px at 80% 10%, #ffffff15, transparent),
    radial-gradient(1px 1px at 60% 70%, #ffffff10, transparent),
    radial-gradient(1px 1px at 30% 80%, #ffffff18, transparent),
    radial-gradient(1px 1px at 90% 60%, #ffffff12, transparent);
  pointer-events: none;
}

header {
  width: 100%;
  max-width: 1000px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px 8px;
}
.logo {
  font-size: 11px;
  color: #a78bfa;
  text-shadow: 0 0 12px #7c3aed, 0 0 24px #7c3aed;
  letter-spacing: 1px;
}
.back-btn {
  margin-left: auto;
  font-family: 'Press Start 2P', monospace;
  font-size: 9px;
  background: transparent;
  color: #475569;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 6px 12px;
  cursor: pointer;
  text-decoration: none;
  transition: all .2s;
}
.back-btn:hover { color: #94a3b8; border-color: #334155; }

canvas {
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  cursor: pointer;
  border: 2px solid #1e293b;
  box-shadow:
    0 0 30px rgba(99,102,241,.15),
    0 0 60px rgba(99,102,241,.08),
    inset 0 0 30px rgba(0,0,0,.3);
  border-radius: 6px;
  max-width: 100vw;
}

.hint {
  font-size: 7px;
  color: #1e293b;
  margin-top: 10px;
  letter-spacing: 2px;
}

/* ── Dialog ── */
.dialog-overlay {
  display: none;
  position: fixed; inset: 0;
  background: rgba(0,0,0,.7);
  backdrop-filter: blur(4px);
  z-index: 100;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 40px;
}
.dialog-overlay.open { display: flex; }

.dialog {
  background: #0d1117;
  border: 2px solid #1e293b;
  border-radius: 0;
  width: 680px;
  max-width: 96vw;
  animation: slideUp .2s cubic-bezier(.16,1,.3,1);
  position: relative;
  overflow: hidden;
}
.dialog::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0;
  height: 2px;
}
.dialog.planner-dialog::before { background: linear-gradient(90deg, #6366f1, #a78bfa, #6366f1); box-shadow: 0 0 12px #6366f1; }
.dialog.writer-dialog::before  { background: linear-gradient(90deg, #10b981, #6ee7b7, #10b981); box-shadow: 0 0 12px #10b981; }

@keyframes slideUp {
  from { transform: translateY(30px); opacity: 0; }
  to   { transform: translateY(0);    opacity: 1; }
}

.dialog-inner { padding: 24px 28px; }

.dialog-top {
  display: flex; gap: 20px; align-items: flex-start;
  margin-bottom: 20px;
}
.dialog-portrait {
  width: 64px; height: 64px;
  border: 2px solid #1e293b;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
  background: #0a0e1a;
}
.dialog-info { flex: 1; }
.dialog-name {
  font-size: 13px;
  margin-bottom: 6px;
  line-height: 1.6;
}
.dialog-name.planner { color: #a78bfa; text-shadow: 0 0 8px #7c3aed; }
.dialog-name.writer  { color: #6ee7b7; text-shadow: 0 0 8px #10b981; }
.dialog-desc {
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 12px; color: #64748b;
  line-height: 1.6;
}

.dialog-stats {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 10px; margin-bottom: 18px;
}
.stat-box {
  background: #0a0e1a;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px 8px;
  text-align: center;
}
.stat-box .s-label {
  font-size: 6px; color: #475569;
  text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 6px; display: block;
}
.stat-box .s-val {
  font-size: 20px; color: #e2e8f0;
  display: block;
}

.dialog-actions { display: flex; gap: 10px; }
.action-btn {
  flex: 1;
  font-family: 'Press Start 2P', monospace;
  font-size: 9px;
  padding: 12px 10px;
  border: none; border-radius: 3px;
  cursor: pointer;
  transition: all .15s;
  line-height: 1.6;
}
.action-btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-indigo {
  background: #6366f1; color: #fff;
  box-shadow: 0 0 12px rgba(99,102,241,.4);
}
.btn-indigo:hover:not(:disabled) {
  background: #818cf8;
  box-shadow: 0 0 20px rgba(99,102,241,.6);
}
.btn-green {
  background: #059669; color: #fff;
  box-shadow: 0 0 12px rgba(5,150,105,.4);
}
.btn-green:hover:not(:disabled) {
  background: #10b981;
  box-shadow: 0 0 20px rgba(5,150,105,.6);
}
.btn-ghost {
  background: transparent; color: #475569;
  border: 1px solid #1e293b; flex: 0 0 auto; padding: 12px 16px;
}
.btn-ghost:hover { color: #94a3b8; }

.dialog-output {
  display: none;
  margin-top: 14px;
  background: #0a0e1a;
  border: 1px solid #1e293b;
  border-radius: 3px;
  padding: 12px;
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 11px; color: #64748b;
  max-height: 100px; overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.6;
}
.dialog-output.success { color: #6ee7b7; border-color: #10b981; }
.dialog-output.error   { color: #fca5a5; border-color: #ef4444; }

/* Spinner */
.spin {
  display: inline-block; width: 10px; height: 10px;
  border: 2px solid rgba(255,255,255,.2);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: rot .5s linear infinite;
  vertical-align: middle; margin-right: 6px;
}
@keyframes rot { to { transform: rotate(360deg); } }
@keyframes scanline {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100vh); }
}
</style>
</head>
<body>

<header>
  <span class="logo">a2aWriter</span>
  <span style="color:#1e293b;font-size:9px;font-family:'Press Start 2P',monospace;">EDITORIAL OFFICE</span>
  <a href="/" class="back-btn">← DASHBOARD</a>
</header>

<canvas id="c" width="960" height="480"></canvas>
<p class="hint">▲ CLICK CHARACTER TO INTERACT ▲</p>

<!-- Dialog -->
<div class="dialog-overlay" id="overlay" onclick="closeDialog(event)">
  <div class="dialog" id="dialog">
    <div class="dialog-inner">
      <div class="dialog-top">
        <div class="dialog-portrait" id="d-portrait">🧠</div>
        <div class="dialog-info">
          <div class="dialog-name" id="d-name">기획 Agent</div>
          <div class="dialog-desc" id="d-desc">대기 중</div>
        </div>
      </div>
      <div class="dialog-stats" id="d-stats"></div>
      <div class="dialog-actions" id="d-actions"></div>
      <pre class="dialog-output" id="d-output"></pre>
    </div>
  </div>
</div>

<script>
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

const S = 4;               // 픽셀 스케일 (게임px → 화면px)
const GW = canvas.width  / S;  // 240 게임px
const GH = canvas.height / S;  // 120 게임px
let   T  = 0;              // 글로벌 타이머 (ms)

// ── 팔레트 ────────────────────────────────────────────
const C = {
  bg:    '#070b14', ceil:  '#0d1117', wall:  '#0f1823',
  wallH: '#131d2b', floor: '#141c28', floorS:'#111825',
  // 네온 악센트
  neonP: '#818cf8', neonPd:'#3730a3', neonG: '#34d399', neonGd:'#065f46',
  neonY: '#fbbf24', neonR: '#f43f5e',
  // 가구
  desk:  '#2a1f15', deskH: '#3d2d1e', deskT: '#1a1410',
  shelf: '#1e1410', book1: '#ef4444', book2: '#3b82f6',
  book3: '#22c55e', book4: '#f59e0b', book5: '#a855f7',
  monitor:'#0f172a', monS: '#1e3a5f', monG: '#60a5fa',
  paper: '#fffbeb', paperB:'#fef3c7',
  lamp:  '#fbbf24', lampS: '#78350f',
  plant: '#14532d', plantL:'#16a34a',
  // 캐릭터 - 기획
  pH:  '#4338ca', pB:  '#6366f1', pBL: '#818cf8',
  pS:  '#fde68a', pSd: '#f59e0b', pG:  '#c7d2fe', pGd: '#4f46e5',
  pT:  '#1e293b', pTL: '#334155', pE:  '#0f172a',
  // 캐릭터 - 작가
  wH:  '#7c2d12', wHL: '#9a3412',
  wB:  '#047857', wBL: '#059669',
  wS:  '#fde68a', wSd: '#f59e0b',
  wT:  '#1e3a8a', wTL: '#1d4ed8', wE:  '#0f172a',
  wPen:'#fbbf24',
  _: null,
};

// ── 렌더러 ────────────────────────────────────────────
function px(x, y, c) {
  if (!c) return;
  ctx.fillStyle = c;
  ctx.fillRect(x * S, y * S, S, S);
}
function rect(x, y, w, h, c) {
  ctx.fillStyle = c;
  ctx.fillRect(x * S, y * S, w * S, h * S);
}
function glow(x, y, w, h, color, blur) {
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur  = blur;
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.18;
  ctx.fillRect(x * S, y * S, w * S, h * S);
  ctx.restore();
}

// ── 스프라이트 (10×14) ────────────────────────────────
function plannerSprite(f, bob) {
  const {pH:H,pB:B,pBL:BL,pS:Sk,pSd:Sd,pG:G,pGd:Gd,pT:T,pTL:TL,pE:E,_} = C;
  const base = [
    [_,_,H,H,H,H,H,_,_,_],
    [_,H,Gd,H,H,H,Gd,H,_,_],
    [_,_,Sk,Sk,Sk,Sk,Sk,_,_,_],
    [_,_,G,Sk,G,Sk,G,_,_,_],
    [_,_,Sk,Sd,Sk,Sd,Sk,_,_,_],
    [_,BL,B,B,B,B,B,BL,_,_],
    [_,_,B,B,B,B,B,_,_,_],
    [_,_,B,B,B,B,B,_,_,_],
  ];
  const legs = f === 0 ? [
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,E,E,_,TL,T,_,_,_],
    [_,_,_,_,_,E,E,_,_,_],
  ] : [
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,TL,T,_,E,E,_,_,_],
    [_,_,E,E,_,_,_,_,_,_],
  ];
  return [...base, ...legs];
}

function writerSprite(f) {
  const {wH:H,wHL:HL,wB:B,wBL:BL,wS:Sk,wSd:Sd,wT:T,wTL:TL,wE:E,wPen:Y,_} = C;
  const base = [
    [_,_,H,H,H,H,H,_,_,_],
    [_,H,HL,H,H,H,HL,H,_,_],
    [_,_,Sk,Sk,Sk,Sk,Sk,_,_,_],
    [_,_,Sk,E,Sk,E,Sk,_,_,_],
    [_,_,Sk,Sd,Sk,Sd,Sk,_,_,_],
    [_,BL,B,B,B,B,B,BL,Y,_],
    [_,_,B,B,B,B,B,_,Y,_],
    [_,_,B,B,B,B,B,_,_,_],
  ];
  const legs = f === 0 ? [
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,E,E,_,TL,T,_,_,_],
    [_,_,_,_,_,E,E,_,_,_],
  ] : [
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,T,TL,_,TL,T,_,_,_],
    [_,_,TL,T,_,E,E,_,_,_],
    [_,_,E,E,_,_,_,_,_,_],
  ];
  return [...base, ...legs];
}

function drawSprite(sprite, gx, gy, flipX) {
  const cols = sprite[0].length;
  sprite.forEach((row, ry) => {
    row.forEach((c, rx) => {
      if (!c) return;
      px(flipX ? gx + (cols - 1 - rx) : gx + rx, gy + ry, c);
    });
  });
}

// ── 배경 ─────────────────────────────────────────────
function drawBg(t) {
  const flicker = 0.85 + Math.sin(t * 0.003) * 0.15;

  // 천장
  rect(0, 0, GW, 10, C.ceil);
  rect(0, 10, GW, 1, '#0a0f1a');

  // 벽
  rect(0, 11, GW, GH - 11, C.wall);

  // 바닥 타일
  for (let x = 0; x < GW; x += 6) {
    rect(x,     GH - 12, 6, 6,  x % 12 === 0 ? C.floor : C.floorS);
    rect(x + 3, GH - 6,  6, 6,  x % 12 === 0 ? C.floorS : C.floor);
  }
  rect(0, GH - 12, GW, 1, '#1e2d40');

  // ── 왼쪽 방 (기획) ──────────────────────────────────

  // 네온 사인 - PLANNER
  ctx.save();
  ctx.shadowColor = C.neonP;
  ctx.shadowBlur  = 14;
  ctx.fillStyle   = C.neonP;
  ctx.font        = 'bold 10px "Press Start 2P"';
  ctx.textAlign   = 'left';
  ctx.globalAlpha = 0.6 + Math.sin(t * 0.002) * 0.2;
  ctx.fillText('PLANNER', 8 * S, 8 * S);
  ctx.restore();

  // 창문
  rect(8, 14, 22, 16, '#0f2035');
  rect(9, 15, 10, 7,  '#1a3a5c');
  rect(20, 15, 10, 7, '#1a3a5c');
  rect(9, 23, 10, 6,  '#152d47');
  rect(20, 23, 10, 6, '#152d47');
  glow(9, 15, 20, 14, '#60a5fa', 20);
  // 창문 테두리
  rect(8, 14, 22, 1, '#1e3a5f');
  rect(8, 30, 22, 1, '#1e3a5f');
  rect(8, 14, 1, 16, '#1e3a5f');
  rect(29, 14, 1, 16, '#1e3a5f');

  // 화이트보드
  rect(40, 13, 50, 30, '#1a2840');
  rect(41, 14, 48, 28, '#0f1e30');
  // 보드 내용 (선)
  ctx.fillStyle = '#1e3a5f';
  for (let i = 0; i < 5; i++) rect(43, 17 + i * 4, 22 + (i % 3) * 8, 1, '#253d5a');
  ctx.save();
  ctx.fillStyle = '#6366f1';
  ctx.font = 'bold 5px "Press Start 2P"';
  ctx.shadowColor = '#6366f1';
  ctx.shadowBlur = 6;
  ctx.fillText('PLAN', 43 * S, 17 * S);
  ctx.restore();

  // 책상 (왼쪽)
  rect(8, GH - 20, 72, 4, C.deskH);
  rect(8, GH - 20, 72, 1, '#4a3728');
  rect(9,  GH - 16, 3, 4, C.deskT);
  rect(76, GH - 16, 3, 4, C.deskT);

  // 책상 위 물건들
  rect(11, GH - 24, 10, 4, C.paperB);  // 서류
  rect(13, GH - 26, 8,  2, C.paper);
  rect(24, GH - 23, 7,  3, '#c7d2fe'); // 포스트잇
  rect(35, GH - 28, 2,  8, C.lampS);   // 조명 스탠드
  rect(31, GH - 30, 10, 3, C.lamp);    // 조명 갓
  glow(28, GH - 30, 16, 14, C.lamp, 24 * flicker);
  rect(58, GH - 26, 9,  6, C.monitor); // 모니터
  rect(59, GH - 25, 7,  4, C.monS);
  rect(60, GH - 24, 5,  2, C.monG);
  glow(59, GH - 25, 7, 4, C.neonP, 16);
  rect(62, GH - 20, 2,  1, C.monitor); // 받침대

  // 화분
  rect(100, GH - 24, 7, 4, '#1a2535');
  rect(101, GH - 30, 3, 6, C.plant);
  rect(99,  GH - 34, 2, 5, C.plantL);
  rect(103, GH - 36, 3, 7, C.plantL);
  rect(100, GH - 38, 2, 4, C.plant);

  // ── 중앙 벽 ──────────────────────────────────────
  rect(118, 11, 4, GH - 11, C.ceil);
  rect(118, GH - 24, 4, 12, '#0a0f1a'); // 문
  rect(119, GH - 23, 2, 11, '#070b14');

  // ── 오른쪽 방 (작가) ────────────────────────────────

  // 네온 사인 - WRITER
  ctx.save();
  ctx.shadowColor = C.neonG;
  ctx.shadowBlur  = 14;
  ctx.fillStyle   = C.neonG;
  ctx.font        = 'bold 10px "Press Start 2P"';
  ctx.textAlign   = 'left';
  ctx.globalAlpha = 0.6 + Math.cos(t * 0.002) * 0.2;
  ctx.fillText('WRITER', 130 * S, 8 * S);
  ctx.restore();

  // 책장
  rect(130, 13, 26, 70, C.shelf);
  const books = [C.book1,C.book2,C.book3,C.book4,C.book5,C.book1,C.book3,C.book2];
  let bx = 131;
  books.forEach((bc, i) => {
    const bw = 2 + (i % 3);
    rect(bx, 14, bw, 14, bc);
    rect(bx, 28, bw, 10, books[(i + 3) % 8]);
    rect(bx, 38, bw, 12, books[(i + 5) % 8]);
    rect(bx, 50, bw, 10, books[(i + 1) % 8]);
    rect(bx, 60, bw, 8,  books[(i + 4) % 8]);
    bx += bw + 1;
  });
  // 책장 선반
  for (let y = 28; y <= 70; y += 10) rect(130, y, 26, 1, C.desk);

  // 책상 (오른쪽)
  rect(160, GH - 20, 70, 4, C.deskH);
  rect(160, GH - 20, 70, 1, '#4a3728');
  rect(161, GH - 16, 3, 4, C.deskT);
  rect(226, GH - 16, 3, 4, C.deskT);

  // 책상 위 물건들
  rect(162, GH - 24, 12, 4, C.paper);   // 원고
  rect(164, GH - 26, 10, 2, C.paperB);
  rect(176, GH - 24, 6,  3, '#fca5a5'); // 빨간 원고
  rect(185, GH - 23, 2,  3, C.wPen);    // 펜
  // 모니터 (큰)
  rect(195, GH - 33, 16, 12, C.monitor);
  rect(196, GH - 32, 14, 10, C.monS);
  rect(197, GH - 31, 12,  8, C.monG);
  glow(196, GH - 32, 14, 10, C.neonG, 18);
  ctx.save();
  ctx.fillStyle = '#34d399';
  ctx.font = 'bold 4px "Press Start 2P"';
  ctx.shadowColor = '#34d399'; ctx.shadowBlur = 8;
  ctx.fillText('WRITING', 197 * S, (GH - 26) * S);
  ctx.restore();
  rect(202, GH - 21, 4, 1, C.monitor); // 받침대

  // 커피잔
  rect(213, GH - 24, 5, 3, '#374151');
  rect(214, GH - 26, 3, 2, '#7c3aed');
  // 커피 연기 (애니메이션)
  const smoke = Math.sin(t * 0.004) * 1;
  ctx.fillStyle = 'rgba(167,139,250,0.3)';
  ctx.fillRect((215 + smoke * 0.5) * S, (GH - 29) * S, S, S);
  ctx.fillRect((215) * S, (GH - 31) * S, S, S);

  // 상태바 (하단)
  rect(0, GH - 6, GW, 6, '#0a0f1a');
  rect(0, GH - 6, GW, 1, '#111825');

  ctx.save();
  ctx.font = '5px "Press Start 2P"';
  ctx.textAlign = 'left';
  // 상태 텍스트
  const st = status;
  const items = [
    { label: 'PLANNED', val: st.planned,   color: C.neonP },
    { label: 'DONE',    val: st.published, color: C.neonG },
    { label: 'WRITING', val: st.writing,   color: C.neonY },
    { label: 'IDEAS',   val: st.suggestions, color: C.neonR },
  ];
  items.forEach((it, i) => {
    ctx.fillStyle = it.color;
    ctx.shadowColor = it.color; ctx.shadowBlur = 6;
    ctx.fillText(`${it.label}:${it.val}`, (4 + i * 58) * S, (GH - 1) * S);
  });
  // 시계
  ctx.textAlign = 'right';
  ctx.fillStyle = '#1e293b';
  ctx.shadowBlur = 0;
  ctx.fillText(new Date().toLocaleTimeString('ko-KR'), (GW - 2) * S, (GH - 1) * S);
  ctx.restore();
}

// ── 이름 뱃지 ──────────────────────────────────────
function drawBadge(gx, gy, name, color) {
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur  = 10;
  ctx.fillStyle   = color;
  ctx.font        = '6px "Press Start 2P"';
  ctx.textAlign   = 'center';
  ctx.fillText(name, (gx + 5) * S, (gy - 3) * S);
  ctx.restore();
}

// ── 에이전트 상태 ─────────────────────────────────
const agents = [
  {
    id: 'planner', name: 'PLANNER', color: C.neonP,
    x: 42, y: GH - 26, vx: 0.25, frame: 0, ftimer: 0,
    patrol: [12, 106], facingL: false, bob: 0,
  },
  {
    id: 'writer', name: 'WRITER', color: C.neonG,
    x: 195, y: GH - 26, vx: -0.3, frame: 0, ftimer: 0,
    patrol: [125, 228], facingL: true, bob: 0,
  },
];

let status = { planned: 0, published: 0, writing: 0, failed: 0, suggestions: 0 };
async function fetchStatus() {
  try { status = await (await fetch('/api/status')).json(); } catch(e) {}
}
fetchStatus();
setInterval(fetchStatus, 8000);

// ── 게임 루프 ──────────────────────────────────────
let last = 0;
function loop(ts) {
  const dt = Math.min(ts - last, 50); last = ts;
  T += dt;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBg(T);

  agents.forEach(a => {
    a.x += a.vx * (dt / 16);
    if (a.x <= a.patrol[0])      { a.x = a.patrol[0]; a.vx =  Math.abs(a.vx); }
    if (a.x >= a.patrol[1] - 10) { a.x = a.patrol[1] - 10; a.vx = -Math.abs(a.vx); }
    a.facingL = a.vx < 0;
    a.bob = Math.sin(T * 0.006 + (a.id === 'writer' ? 1.5 : 0)) * 0.8;
    a.ftimer += dt;
    if (a.ftimer > 200) { a.ftimer = 0; a.frame ^= 1; }

    // 캐릭터 그로우
    ctx.save();
    ctx.shadowColor = a.color;
    ctx.shadowBlur  = 12;
    const sprite = a.id === 'planner'
      ? plannerSprite(a.frame)
      : writerSprite(a.frame);
    drawSprite(sprite, Math.round(a.x), Math.round(a.y - 14 + a.bob), a.facingL);
    ctx.restore();

    drawBadge(Math.round(a.x), Math.round(a.y - 14 + a.bob), a.name, a.color);
  });

  requestAnimationFrame(loop);
}

// 폰트 로드 후 시작
document.fonts.ready.then(() => requestAnimationFrame(loop));

// ── 클릭 감지 ─────────────────────────────────────
canvas.addEventListener('click', e => {
  const r = canvas.getBoundingClientRect();
  const cx = (e.clientX - r.left) / (r.width  / canvas.width)  / S;
  const cy = (e.clientY - r.top)  / (r.height / canvas.height) / S;

  for (const a of agents) {
    const ax = Math.round(a.x), ay = Math.round(a.y - 14 + a.bob);
    if (cx >= ax - 2 && cx <= ax + 12 && cy >= ay - 2 && cy <= ay + 18) {
      openDialog(a); return;
    }
  }
});

// ── 다이얼로그 ────────────────────────────────────
function openDialog(agent) {
  const dlg = document.getElementById('dialog');
  dlg.className = 'dialog ' + (agent.id === 'planner' ? 'planner-dialog' : 'writer-dialog');

  document.getElementById('d-portrait').textContent = agent.id === 'planner' ? '🧠' : '✍️';
  document.getElementById('d-output').style.display = 'none';
  document.getElementById('d-output').textContent = '';
  document.getElementById('d-output').className = 'dialog-output';

  if (agent.id === 'planner') {
    document.getElementById('d-name').className  = 'dialog-name planner';
    document.getElementById('d-name').textContent = 'PLANNER AGENT';
    document.getElementById('d-desc').textContent = `대기 중 · AI 제안 ${status.suggestions}개 준비됨`;
    document.getElementById('d-stats').innerHTML = `
      <div class="stat-box"><span class="s-label">PLANNED</span><span class="s-val" style="color:#a78bfa">${status.planned}</span></div>
      <div class="stat-box"><span class="s-label">PUBLISHED</span><span class="s-val" style="color:#34d399">${status.published}</span></div>
      <div class="stat-box"><span class="s-label">SUGGEST</span><span class="s-val" style="color:#f43f5e">${status.suggestions}</span></div>
      <div class="stat-box"><span class="s-label">FAILED</span><span class="s-val" style="color:#fb923c">${status.failed}</span></div>
    `;
    document.getElementById('d-actions').innerHTML = `
      <button class="action-btn btn-indigo" onclick="runAction('suggest')">✨ 새 주제 기획 (5개)</button>
      <button class="action-btn btn-ghost"  onclick="closeDialog()">ESC</button>
    `;
  } else {
    document.getElementById('d-name').className  = 'dialog-name writer';
    document.getElementById('d-name').textContent = 'WRITER AGENT';
    document.getElementById('d-desc').textContent = `대기 중 · 발행 완료 ${status.published}개`;
    document.getElementById('d-stats').innerHTML = `
      <div class="stat-box"><span class="s-label">PLANNED</span><span class="s-val" style="color:#a78bfa">${status.planned}</span></div>
      <div class="stat-box"><span class="s-label">PUBLISHED</span><span class="s-val" style="color:#34d399">${status.published}</span></div>
      <div class="stat-box"><span class="s-label">WRITING</span><span class="s-val" style="color:#fbbf24">${status.writing}</span></div>
      <div class="stat-box"><span class="s-label">FAILED</span><span class="s-val" style="color:#fb923c">${status.failed}</span></div>
    `;
    document.getElementById('d-actions').innerHTML = `
      <button class="action-btn btn-green" onclick="runAction('write_publish')">📝 글 쓰고 발행하기</button>
      <button class="action-btn btn-ghost" onclick="closeDialog()">ESC</button>
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
  const out = document.getElementById('d-output');
  out.style.display = 'block';
  out.className = 'dialog-output';
  out.textContent = '실행 중...\n';

  try {
    if (type === 'suggest') {
      const d = await (await fetch('/api/suggest', { method: 'POST' })).json();
      out.className = 'dialog-output ' + (d.ok ? 'success' : 'error');
      out.textContent = d.ok
        ? '✅ 기획 완료! 대시보드 [편집장 승인] 탭에서 확인하세요.'
        : '❌ ' + (d.error || '알 수 없는 오류');
    } else if (type === 'write_publish') {
      out.textContent = '📝 Writer 실행 중...\n';
      const d1 = await (await fetch('/api/run_writer',    { method: 'POST' })).json();
      out.textContent += d1.output || d1.error || '';
      if (d1.ok) {
        out.textContent += '\n🚀 Publisher 실행 중...\n';
        const d2 = await (await fetch('/api/run_publisher', { method: 'POST' })).json();
        out.textContent += d2.output || d2.error || '';
        out.className = 'dialog-output ' + (d2.ok ? 'success' : 'error');
      } else {
        out.className = 'dialog-output error';
      }
    }
  } catch(e) {
    out.textContent += '오류: ' + e.message;
    out.className = 'dialog-output error';
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
