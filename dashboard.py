"""
청약 인사이트 대시보드

EC2에서 실행: python dashboard.py
접속: http://<EC2_IP>:5001
"""

import re
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path
from flask import Flask, jsonify, abort

app = Flask(__name__)

BLOG        = "llmenginehistory"
TASKS_DIR   = Path(f"blogs/{BLOG}/tasks")
ARTICLES    = Path(f"articles/{BLOG}")
DAILY_RATE  = 4


# ── 데이터 로딩 ─────────────────────────────────────────────────

def parse_task(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = {
        "task_id": path.stem,
        "topic": path.stem,
        "notice_name": "",
        "region": "",
        "apply_end": "",
        "deadline": "",
        "housing_source": "",
        "supply_type": "",
        "series": "",
        "created_at": "",
        "list_mi": "",
    }
    parts = text.split("---")
    if len(parts) >= 3:
        for line in parts[1].strip().splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                data[k.strip()] = v.strip()
    if data["notice_name"]:
        data["topic"] = data["notice_name"]
    data["deadline_date"] = _parse_date(data.get("apply_end") or data.get("deadline", ""))
    return data


def _parse_date(s: str):
    if not s:
        return None
    m = re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    return None


def load_tasks(folder: str) -> list:
    p = TASKS_DIR / folder
    if not p.exists():
        return []
    tasks = [parse_task(f) for f in p.glob("*.md")]
    return sorted(tasks, key=lambda t: (t.get("deadline_date") or date(9999, 1, 1), t["task_id"]))


def has_preview(task_id: str) -> bool:
    return (ARTICLES / "preview" / f"{task_id}.html").exists()


def read_html(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    title_m = re.search(r"<!--\s*TITLE:\s*(.+?)\s*-->", content)
    title   = title_m.group(1) if title_m else path.stem
    body    = re.sub(r"<!--\s*TITLE:\s*.+?\s*-->\n?", "", content)
    return title, body


def _wrap_html(title: str, body: str, task_id: str, badge: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{max-width:800px;margin:0 auto;padding:0 0 60px;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;font-size:15px;line-height:1.8;color:#1a1a1a}}
.bar{{position:sticky;top:0;background:#0f172a;color:#e2e8f0;padding:11px 20px;display:flex;align-items:center;gap:12px;font-size:13px;z-index:100;border-bottom:1px solid #1e293b}}
.bar a{{color:#a5b4fc;text-decoration:none;padding:4px 10px;border-radius:5px;transition:.15s}}
.bar a:hover{{background:#1e293b}}
.bar .ttl{{flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}}
.bar .badge{{font-size:11px;padding:2px 8px;border-radius:4px;background:#1e293b;color:#94a3b8}}
.content{{padding:24px 20px}}
h2{{font-size:18px;margin:28px 0 12px;border-bottom:2px solid #f0f0f0;padding-bottom:6px}}
h3{{font-size:15px;margin:20px 0 8px}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}}
th,td{{border:1px solid #ddd;padding:8px 12px;text-align:center}}
th{{background:#f5f5f5;font-weight:600}}
p{{margin:10px 0}}
ul,ol{{margin:8px 0 8px 20px}}
</style>
</head>
<body>
<div class="bar">
  <a href="/">← 목록</a>
  <span class="ttl">{title}</span>
  {f'<span class="badge">{badge}</span>' if badge else ''}
  <span class="badge" style="color:#64748b">{task_id}</span>
</div>
<div class="content">{body}</div>
</body>
</html>"""


# ── 라우트 ────────────────────────────────────────────────────

@app.route("/")
def index():
    today    = date.today()
    planned  = load_tasks("planned")
    published = load_tasks("published")
    writing  = load_tasks("writing")
    failed   = load_tasks("failed")

    # 마감 임박 (3일 이내)
    urgent = [t for t in planned if t["deadline_date"] and
              0 < (t["deadline_date"] - today).days <= 3]

    # 미리보기는 클릭 시 on-demand 생성 (항상 버튼 표시)
    for t in planned:
        t["preview"] = True

    # 발행 완료 역순 정렬
    published_rev = list(reversed(published))

    now_str = datetime.now().strftime("%Y.%m.%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>청약 인사이트 대시보드</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;background:#f8fafc;color:#0f172a;min-height:100vh;font-size:14px}}

/* Header */
header{{background:#0f172a;padding:0 28px;height:54px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:100}}
.logo{{font-size:16px;font-weight:800;color:#a5b4fc;letter-spacing:-.3px}}
.logo em{{color:#e2e8f0;font-style:normal}}
.dot{{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:blink 2s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.now{{margin-left:auto;color:#475569;font-size:12px}}

/* Container */
.wrap{{max-width:1100px;margin:0 auto;padding:24px 20px}}

/* KPI */
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
@media(max-width:700px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}}}
.kpi{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px}}
.kpi-label{{font-size:11px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
.kpi-val{{font-size:28px;font-weight:900;line-height:1}}
.kpi-sub{{font-size:11px;color:#94a3b8;margin-top:4px}}
.c-blue{{color:#6366f1}}.c-green{{color:#22c55e}}.c-orange{{color:#f59e0b}}.c-red{{color:#ef4444}}

/* Tabs */
.tabs{{display:flex;gap:2px;border-bottom:2px solid #e2e8f0;margin-bottom:16px}}
.tab{{padding:9px 18px;background:none;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;
      font-size:13px;font-weight:600;color:#94a3b8;cursor:pointer;transition:.15s;display:flex;align-items:center;gap:6px}}
.tab:hover{{color:#475569}}
.tab.on{{color:#6366f1;border-bottom-color:#6366f1}}
.cnt{{background:#f1f5f9;color:#64748b;font-size:11px;font-weight:700;padding:1px 7px;border-radius:99px}}
.tab.on .cnt{{background:#e0e7ff;color:#6366f1}}
.pane{{display:none}}.pane.on{{display:block}}

/* Table */
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden}}
table{{width:100%;border-collapse:collapse}}
thead th{{text-align:left;font-size:11px;font-weight:600;color:#94a3b8;text-transform:uppercase;
          letter-spacing:.04em;padding:10px 14px;background:#f8fafc;border-bottom:1px solid #e2e8f0}}
tbody td{{padding:10px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover td{{background:#fafbff}}

/* Badges */
.badge{{display:inline-flex;align-items:center;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600;white-space:nowrap}}
.b-sale{{background:#dbeafe;color:#1d4ed8}}
.b-rent{{background:#dcfce7;color:#15803d}}
.b-region{{background:#f1f5f9;color:#475569}}
.b-lh{{background:#fef3c7;color:#b45309}}
.b-ah{{background:#fce7f3;color:#be185d}}
.b-apt{{background:#ede9fe;color:#6d28d9}}
.b-other{{background:#fff7ed;color:#c2410c}}

/* Deadline */
.dl-ok{{color:#94a3b8;font-size:12px}}
.dl-soon{{color:#f59e0b;font-weight:700;font-size:12px}}
.dl-urgent{{color:#ef4444;font-weight:700;font-size:12px;animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.5}}}}

/* Buttons */
.btn-preview{{font-size:11px;color:#6366f1;text-decoration:none;background:#e0e7ff;
              padding:3px 9px;border-radius:5px;white-space:nowrap;transition:.15s}}
.btn-preview:hover{{background:#c7d2fe}}
.empty{{padding:48px;text-align:center;color:#94a3b8;font-size:13px;line-height:2}}
</style>
</head>
<body>

<header>
  <span class="logo">청약<em>인사이트</em></span>
  <div class="dot"></div>
  <span style="color:#475569;font-size:12px">파이프라인 대시보드</span>
  <span class="now">{now_str}</span>
</header>

<div class="wrap">

  <!-- KPI -->
  <div class="kpi-row">
    <div class="kpi">
      <div class="kpi-label">발행 대기</div>
      <div class="kpi-val c-blue">{len(planned)}</div>
      <div class="kpi-sub">하루 {DAILY_RATE}개 기준 {_dday(len(planned), DAILY_RATE)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">발행 완료</div>
      <div class="kpi-val c-green">{len(published)}</div>
      <div class="kpi-sub">총 {len(planned)+len(published)+len(writing)+len(failed)}건 중</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">마감 임박 (3일)</div>
      <div class="kpi-val {'c-red' if urgent else 'c-orange'}">{len(urgent)}</div>
      <div class="kpi-sub">{"우선 발행 필요" if urgent else "여유 있음"}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">작성중 / 실패</div>
      <div class="kpi-val c-orange">{len(writing)}<span style="font-size:16px;color:#cbd5e1"> / </span>{len(failed)}</div>
      <div class="kpi-sub">writing / failed</div>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab on" data-tab="planned">발행 대기 <span class="cnt">{len(planned)}</span></button>
    <button class="tab" data-tab="published">발행 완료 <span class="cnt">{len(published)}</span></button>
  </div>

  <!-- 대기 -->
  <div id="tab-planned" class="pane on">
    <div class="card">
      {"<table><thead><tr><th>#</th><th>공고명</th><th>구분</th><th>지역</th><th>청약 마감</th><th></th></tr></thead><tbody>"
        + "".join(_planned_row(i+1, t, today) for i, t in enumerate(planned))
        + "</tbody></table>" if planned else '<div class="empty">대기 중인 공고가 없어요.<br>내일 아침 6~7시 수집 후 추가됩니다.</div>'}
    </div>
  </div>

  <!-- 발행 완료 -->
  <div id="tab-published" class="pane">
    <div class="card">
      {"<table><thead><tr><th>발행일</th><th>제목</th><th>구분</th><th>지역</th><th></th></tr></thead><tbody>"
        + "".join(_published_row(t) for t in published_rev)
        + "</tbody></table>" if published_rev else '<div class="empty">발행된 글이 없어요.</div>'}
    </div>
  </div>

</div>

<script>
document.querySelectorAll('.tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('on');
  }});
}});
setTimeout(() => location.reload(), 60000);
</script>
</body>
</html>"""


def _dday(n, rate):
    if n == 0:
        return "소재 없음"
    d = (n + rate - 1) // rate
    return f"약 {d}일치"


def _supply_badge(t: dict) -> str:
    hs = t.get("housing_source", "")
    st = t.get("supply_type", "")
    mi = t.get("list_mi", "")

    badges = []
    # 소스
    if mi == "applyhome" or "applyhome" in str(t.get("detail_url", "")):
        badges.append('<span class="badge b-ah">청약홈</span>')
    elif mi in ("1026", "1027") or "lh.or.kr" in str(t.get("detail_url", "")):
        badges.append('<span class="badge b-lh">LH</span>')

    # 분양/임대
    if hs == "분양":
        badges.append('<span class="badge b-sale">분양</span>')
    elif hs == "임대":
        badges.append('<span class="badge b-rent">임대</span>')

    # 주택 유형
    if "오피스텔" in st or "도시형" in st:
        badges.append('<span class="badge b-other">오피스텔</span>')
    elif "잔여" in st or "임의" in st:
        badges.append('<span class="badge b-other">잔여세대</span>')
    elif "APT" in st.upper() or "아파트" in st or not st:
        pass  # 기본은 표시 안 함

    return " ".join(badges) if badges else '<span class="badge b-region">-</span>'


def _deadline_html(t: dict, today: date) -> str:
    dl = t.get("deadline_date")
    dl_str = t.get("apply_end") or t.get("deadline", "")
    if not dl:
        return f'<span class="dl-ok">{dl_str or "-"}</span>'
    diff = (dl - today).days
    if diff <= 3:
        cls = "dl-urgent"
        suffix = f"D-{diff}" if diff > 0 else "오늘마감"
    elif diff <= 7:
        cls = "dl-soon"
        suffix = f"D-{diff}"
    else:
        cls = "dl-ok"
        suffix = f"D-{diff}"
    return f'<span class="{cls}">{dl_str}<br>{suffix}</span>'


def _planned_row(i: int, t: dict, today: date) -> str:
    name    = t["topic"][:40] + ("…" if len(t["topic"]) > 40 else "")
    region  = f'<span class="badge b-region">{t["region"]}</span>' if t["region"] else ""
    dl_html = _deadline_html(t, today)
    badges  = _supply_badge(t)
    preview = (f'<a class="btn-preview" href="/preview/{t["task_id"]}" target="_blank">미리보기</a>'
               if t["preview"] else '<span style="color:#e2e8f0;font-size:11px">-</span>')
    return (f"<tr>"
            f"<td style='color:#cbd5e1;font-size:12px'>{i}</td>"
            f"<td><strong style='font-size:13px'>{name}</strong></td>"
            f"<td>{badges}</td>"
            f"<td>{region}</td>"
            f"<td>{dl_html}</td>"
            f"<td>{preview}</td>"
            f"</tr>")


def _published_row(t: dict) -> str:
    name   = t["topic"][:45] + ("…" if len(t["topic"]) > 45 else "")
    region = f'<span class="badge b-region">{t["region"]}</span>' if t["region"] else ""
    badges = _supply_badge(t)
    date_s = t.get("created_at") or t["task_id"][:8]
    btn    = f'<a class="btn-preview" href="/preview/{t["task_id"]}" target="_blank">HTML 보기</a>'
    return (f"<tr>"
            f"<td style='color:#94a3b8;font-size:12px'>{date_s}</td>"
            f"<td><span style='font-size:13px'>{name}</span></td>"
            f"<td>{badges}</td>"
            f"<td>{region}</td>"
            f"<td>{btn}</td>"
            f"</tr>")


@app.route("/preview/<task_id>")
def preview(task_id: str):
    """대기 중 공고 HTML 미리보기."""
    html_path = ARTICLES / "preview" / f"{task_id}.html"

    # preview 없으면 planned에서 writer --dry-run 생성 시도
    if not html_path.exists():
        task_path = TASKS_DIR / "planned" / f"{task_id}.md"
        if not task_path.exists():
            task_path = TASKS_DIR / "published" / f"{task_id}.md"
        if task_path.exists():
            subprocess.run(
                ["venv/bin/python", "agents/writer_agent.py",
                 "--blog", BLOG, "--task", str(task_path), "--dry-run"],
                capture_output=True, timeout=120,
                cwd=Path(__file__).parent,
            )
    if not html_path.exists():
        # published HTML fallback
        html_path = ARTICLES / "published" / f"{task_id}.html"
    if not html_path.exists():
        abort(404)

    result = read_html(html_path)
    if not result:
        abort(404)
    title, body = result

    # published 여부
    is_pub = (TASKS_DIR / "published" / f"{task_id}.md").exists()
    badge  = "✅ 발행됨" if is_pub else "⏳ 대기 중"

    return _wrap_html(title, body, task_id, badge)


@app.route("/api/status")
def api_status():
    def count(folder):
        p = TASKS_DIR / folder
        return len(list(p.glob("*.md"))) if p.exists() else 0
    return jsonify({
        "planned":     count("planned"),
        "published":   count("published"),
        "writing":     count("writing"),
        "failed":      count("failed"),
        "suggestions": count("suggestions"),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
