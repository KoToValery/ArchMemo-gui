#!/usr/bin/env python3
"""
Project Delivery Checker — Flask уеб сървър
Стартира се веднъж, достъпва се от браузър (Tailscale / локална мрежа).
Автоматична проверка всеки ден в 08:00.
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, redirect, url_for

sys.path.insert(0, '/home/koto/onedrive-env/lib/python3.14/site-packages')

from checker import ProjectChecker, OUTPUT_DIR, CLOUD_ROOT, log
from html_builder import build_html_report

# ─── APScheduler за автоматична проверка ──────────────────────────────────────
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Глобален стейт
state = {
    "running":       False,
    "last_report":   None,
    "last_run":      None,
    "last_html":     "",
    "last_year":     str(__import__('datetime').datetime.now().year),
    "last_city":     None,
    "log_lines":     [],
    "report_cache":  [],  # История на рапорти [{timestamp, year, city, html, summary}, ...]
}

MAX_LOG_LINES = 200


# ─── Лог handler за UI ────────────────────────────────────────────────────────
class UILogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        state["log_lines"].append(msg)
        if len(state["log_lines"]) > MAX_LOG_LINES:
            state["log_lines"] = state["log_lines"][-MAX_LOG_LINES:]


ui_handler = UILogHandler()
ui_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
log.addHandler(ui_handler)


# ─── Функция за стартиране на проверка ────────────────────────────────────────
def run_check(year: str, city: str | None, send_email: bool = False):
    if state["running"]:
        log.warning("Проверката вече е в ход — пропускам.")
        return

    state["running"]   = True
    state["log_lines"] = []
    log.info("🔍 Стартиране на проверка: година=%s, град=%s, имейл=%s",
             year, city or "всички", send_email)
    try:
        checker = ProjectChecker(year=year, city=city, send_email=send_email)
        report  = checker.run()
        state["last_report"] = report
        state["last_run"]    = datetime.now().strftime("%d.%m.%Y %H:%M")
        state["last_year"]   = year
        state["last_city"]   = city
        log.info("📊 Генериране на HTML рапорт за %d проекта...", len(report.get("projects", [])))
        html = _build_full_html(report, year, city)
        state["last_html"] = html
        
        # Запазване в кеш
        projects = report.get("projects", [])
        total  = len(projects)
        ok     = sum(1 for p in projects if p.get("status") == "Актуален")
        issues = sum(1 for p in projects if p.get("status") == "Има проблеми")
        errors = len(report.get("errors", []))
        
        cache_entry = {
            "timestamp": state["last_run"],
            "year": year,
            "city": city or "Всички",
            "html": html,
            "summary": {"total": total, "ok": ok, "issues": issues, "errors": errors}
        }
        state["report_cache"].insert(0, cache_entry)
        # Пази само последните 20 рапорта
        if len(state["report_cache"]) > 20:
            state["report_cache"] = state["report_cache"][:20]
        
        log.info("✅ Проверката завърши. HTML: %d chars", len(html))
    except Exception as exc:
        log.error("❌ Грешка при проверка: %s", exc, exc_info=True)
        state["last_html"] = f'<div class="no-results">❌ Грешка: {exc}</div>'
    finally:
        state["running"] = False


def _build_full_html(report: dict, year: str, city: str | None) -> str:
    """Генерира HTML за всички проекти в рапорта."""
    projects = report.get("projects", [])
    if not projects:
        return '<div class="no-results">Няма намерени проекти.</div>'

    parts = []
    for p in projects:
        try:
            if not p.get("pln_name"):
                status_cls = "status-ok" if p.get("status") == "Актуален" else "status-warn"
                parts.append(f"""
                <div class="project-card status-only">
                  <div class="card-header">
                    <div class="card-title">🏗 {p['name']} {('(' + p['location'] + ')') if p.get('location') else ''}</div>
                    <div class="card-meta">{p.get('status', '—')}</div>
                  </div>
                </div>""")
                continue

            html = build_html_report(
                city               = f"{year} / {p.get('location') or city or '—'}",
                project_name       = p["name"],
                full_name          = f"{p['name']} ({p['location']})" if p.get("location") else p["name"],
                pln_name           = p.get("pln_name", "—"),
                pln_date_str       = p.get("pln_date_str", "—"),
                delivered_count    = p.get("delivered_count", 0),
                outdated_arch      = p.get("outdated_arch", []),
                delivered_files    = p.get("delivered_files", []),
                specialties_rows   = p.get("specialties_rows", []),
                specialties_detail = p.get("specialties", {}),
                project_path       = p.get("full_path", ""),
                stanovishta        = p.get("stanovishta", {
                    "visa_status": "missing", "skica_status": "missing",
                    "visa_files": [], "skica_files": [],
                    "stanovishte_files": [], "other_files": [],
                }),
                podlozhki_files    = p.get("podlozhki_files", []),
            )
            parts.append(html)
        except Exception as exc:
            log.error("Грешка при генериране на HTML за проект %s: %s", p.get("name", "?"), exc)
            parts.append(f'<div class="project-card status-only"><div class="card-header"><div class="card-title">⚠ {p.get("name","?")} — грешка при рендиране</div><div class="card-meta">{exc}</div></div></div>')

    return "\n".join(parts)


# ─── Scheduler — всеки ден в 08:00 ───────────────────────────────────────────
def scheduled_check():
    year = str(datetime.now().year)
    log.info("⏰ Автоматична проверка в 08:00 — година %s", year)
    run_check(year=year, city=None, send_email=False)


scheduler = BackgroundScheduler(timezone="Europe/Sofia")
scheduler.add_job(scheduled_check, "cron", hour=8, minute=0)
scheduler.start()


# ─── HTML шаблон ──────────────────────────────────────────────────────────────
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Проверка на проекти — Pirin Design</title>
<style>
  :root {
    --bg: #f0f2f5; --card: #fff; --header: #2c3e50; --accent: #3498db;
    --ok: #27ae60; --warn: #e67e22; --err: #e74c3c;
    --text: #2c3e50; --muted: #7f8c8d; --border: #ecf0f1;
    --purple: #8e44ad; --teal: #16a085; --info: #2980b9; --gray: #7f8c8d;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); font-size: 15px; }

  /* ── Top bar ── */
  .topbar { background: var(--header); color: #fff; padding: 14px 16px;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
  .topbar h1 { font-size: 17px; font-weight: 600; }
  .topbar .last-run { font-size: 12px; color: #bdc3c7; }

  /* ── Form ── */
  .form-wrap { background: var(--card); padding: 16px; margin: 12px;
               border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  .form-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
  .form-group { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 140px; }
  .form-group label { font-size: 12px; color: var(--muted); font-weight: 500; }
  .form-group input, .form-group select {
    padding: 9px 12px; border: 1px solid #ddd; border-radius: 7px;
    font-size: 15px; background: #fafafa; width: 100%; cursor: pointer; }
  .form-group input:focus, .form-group select:focus {
    outline: none; border-color: var(--accent); background: #fff; }
  .form-group select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%237f8c8d' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; padding-right: 32px; }
  .checkbox-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
  .checkbox-row input[type=checkbox] { width: 18px; height: 18px; cursor: pointer; }
  .checkbox-row label { font-size: 14px; cursor: pointer; }
  .btn { padding: 10px 20px; border: none; border-radius: 7px; font-size: 15px;
         font-weight: 600; cursor: pointer; transition: opacity .2s; }
  .btn:active { opacity: .8; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-secondary { background: #ecf0f1; color: var(--text); }
  .btn:disabled { opacity: .5; cursor: not-allowed; }

  /* ── Cache list ── */
  .cache-wrap { background: var(--card); padding: 12px 16px; margin: 0 12px 12px;
                border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  .cache-title { font-size: 13px; font-weight: 600; color: var(--muted);
                 margin-bottom: 8px; text-transform: uppercase; letter-spacing: .5px; }
  .cache-list { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
  .cache-item { min-width: 140px; padding: 10px 12px; background: #f8f9fa;
                border-radius: 7px; cursor: pointer; transition: all .2s;
                border: 2px solid transparent; }
  .cache-item:hover { background: #e9ecef; border-color: var(--accent); }
  .cache-time { font-size: 11px; color: var(--muted); font-weight: 600; }
  .cache-info { font-size: 13px; color: var(--text); margin: 4px 0; }
  .cache-summary { display: flex; gap: 6px; margin-top: 6px; }
  .cache-badge { display: inline-block; padding: 2px 6px; border-radius: 4px;
                 font-size: 11px; font-weight: 700; color: #fff; }
  .cache-badge.ok { background: var(--ok); }
  .cache-badge.warn { background: var(--warn); }
  .cache-badge.err { background: var(--err); }

  /* ── Status bar ── */
  .status-bar { margin: 0 12px 8px; padding: 10px 14px; border-radius: 8px;
                font-size: 13px; display: none; }
  .status-bar.running { display: block; background: #eaf4fb; color: var(--info);
                         border: 1px solid #aed6f1; }
  .status-bar.done    { display: block; background: #eafaf1; color: var(--ok);
                         border: 1px solid #a9dfbf; }

  /* ── Summary bar ── */
  .summary { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 12px 12px; }
  .summary-item { flex: 1; min-width: 80px; background: var(--card); border-radius: 8px;
                  padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .summary-item .num { font-size: 26px; font-weight: 700; }
  .summary-item .lbl { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .num-ok   { color: var(--ok); }
  .num-warn { color: var(--warn); }
  .num-err  { color: var(--err); }
  .num-all  { color: var(--accent); }

  /* ── Project cards ── */
  .results { padding: 0 12px 24px; }
  .project-card { background: var(--card); border-radius: 10px; margin-bottom: 14px;
                  box-shadow: 0 1px 4px rgba(0,0,0,.1); overflow: hidden; }
  .card-header { background: var(--header); padding: 14px 16px; cursor: pointer;
                 user-select: none; transition: background .2s; }
  .card-header:hover { background: #34495e; }
  .card-title-row { display: flex; align-items: center; gap: 10px; }
  .card-title-row .toggle-icon { font-size: 12px; transition: transform .2s;
                                  color: #bdc3c7; min-width: 12px; }
  .project-card:not(.collapsed) .card-header .toggle-icon { transform: rotate(90deg); }
  .card-title  { color: #fff; font-size: 15px; font-weight: 600; }
  .card-meta   { color: #bdc3c7; font-size: 12px; margin-top: 3px; }
  .card-path   { color: #95a5a6; font-size: 11px; margin-top: 2px; word-break: break-all; }
  .card-body   { display: none; }
  .project-card:not(.collapsed) .card-body { display: block; }
  .card-section { padding: 14px 16px; border-top: 1px solid var(--border); }
  .section-title { font-weight: 600; font-size: 13px; color: var(--muted);
                   text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
  .status-only .card-header { background: #636e72; cursor: default; }
  .status-only .card-header:hover { background: #636e72; }

  /* ── Tables ── */
  .info-table, .spec-table, .doc-table {
    width: 100%; border-collapse: collapse; font-size: 13px; }
  .info-table td, .spec-table td, .spec-table th, .doc-table td {
    padding: 7px 6px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .spec-table th { background: #f8f9fa; font-weight: 600; font-size: 12px;
                   color: var(--muted); text-align: left; }
  .detail, .date { color: var(--muted); font-size: 12px; }
  .empty { color: var(--muted); font-style: italic; font-size: 12px; padding: 8px 6px; }

  /* ── Badges ── */
  .badge { display: inline-block; padding: 2px 7px; border-radius: 4px;
           font-size: 11px; font-weight: 700; color: #fff; }
  .badge-ok     { background: var(--ok); }
  .badge-warn   { background: var(--warn); }
  .badge-err    { background: var(--err); }
  .badge-info   { background: var(--info); }
  .badge-purple { background: var(--purple); }
  .badge-teal   { background: var(--teal); }
  .badge-gray   { background: var(--gray); }

  /* ── Outdated list ── */
  .outdated-list { margin-top: 10px; padding: 10px 12px; background: #fef9f0;
                   border-left: 3px solid var(--warn); border-radius: 4px; font-size: 12px; }
  .outdated-list ul { margin: 6px 0 0 16px; }
  .outdated-list li { margin-bottom: 2px; color: var(--muted); }

  /* ── Collapsible sections ── */
  .collapsible .section-title { cursor: pointer; user-select: none; display: flex;
                                 justify-content: space-between; align-items: center; }
  .collapsible .section-title:hover { color: var(--accent); }
  .toggle-icon { font-size: 10px; transition: transform .2s; }
  .toggle-icon.open { transform: rotate(-180deg); }
  .section-content { margin-top: 10px; display: none; }
  .section-content.open { display: block; }

  /* ── Log panel ── */
  .log-toggle { margin: 0 12px 8px; }
  .log-toggle button { background: none; border: 1px solid #ddd; border-radius: 6px;
                        padding: 6px 12px; font-size: 12px; cursor: pointer; color: var(--muted); }
  .log-panel { display: none; margin: 0 12px 12px; background: #1e272e; color: #dfe6e9;
               border-radius: 8px; padding: 12px; font-family: monospace; font-size: 11px;
               max-height: 250px; overflow-y: auto; }
  .log-panel.visible { display: block; }

  /* ── No results ── */
  .no-results { text-align: center; padding: 40px; color: var(--muted); font-size: 15px; }

  /* ── Spinner ── */
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid currentColor;
             border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite;
             vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Responsive ── */
  @media (max-width: 480px) {
    .topbar h1 { font-size: 15px; }
    .form-group { min-width: 100%; }
    .summary-item .num { font-size: 22px; }
  }
</style>
</head>
<body>

<div class="topbar">
  <h1>🏗 Проверка на проекти</h1>
  <span class="last-run" id="lastRun">{{ last_run or 'Не е стартирана' }}</span>
</div>

<div class="form-wrap">
  <form id="checkForm" onsubmit="startCheck(event)">
    <div class="form-row">
      <div class="form-group">
        <label for="year">Година</label>
        <select id="year" name="year" required>
          <option value="2024" {{ 'selected' if current_year == '2024' else '' }}>2024</option>
          <option value="2025" {{ 'selected' if current_year == '2025' else '' }}>2025</option>
          <option value="2026" {{ 'selected' if current_year == '2026' else '' }}>2026</option>
        </select>
      </div>
      <div class="form-group">
        <label for="city">Град</label>
        <select id="city" name="city">
          <option value="">Всички градове</option>
          <option value="БЛАГОЕВГРАД">БЛАГОЕВГРАД</option>
          <option value="СОФИЯ">СОФИЯ</option>
          <option value="БАНСКО">БАНСКО</option>
          <option value="РАЗЛОГ">РАЗЛОГ</option>
          <option value="САМОКОВ">САМОКОВ</option>
          <option value="КЮСТЕНДИЛ">КЮСТЕНДИЛ</option>
        </select>
      </div>
      <div class="form-group" style="flex:0">
        <label>&nbsp;</label>
        <button type="submit" class="btn btn-primary" id="runBtn">▶ Провери</button>
      </div>
    </div>
    <div class="checkbox-row" style="margin-top:10px">
      <input type="checkbox" id="sendEmail" name="sendEmail">
      <label for="sendEmail">📧 Изпрати имейл при проблеми</label>
    </div>
  </form>
</div>

{% if report_cache %}
<div class="cache-wrap">
  <div class="cache-title">📚 Предишни рапорти</div>
  <div class="cache-list">
    {% for entry in report_cache %}
    <div class="cache-item" onclick="loadCachedReport({{ loop.index0 }})">
      <div class="cache-time">{{ entry.timestamp }}</div>
      <div class="cache-info">{{ entry.year }} / {{ entry.city }}</div>
      <div class="cache-summary">
        <span class="cache-badge ok">{{ entry.summary.ok }}</span>
        <span class="cache-badge warn">{{ entry.summary.issues }}</span>
        <span class="cache-badge err">{{ entry.summary.errors }}</span>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

<div class="status-bar" id="statusBar"></div>

<div class="summary" id="summary" style="{{ 'display:none' if not last_run else '' }}">
  <div class="summary-item">
    <div class="num num-all" id="sumTotal">{{ total }}</div>
    <div class="lbl">Общо</div>
  </div>
  <div class="summary-item">
    <div class="num num-ok" id="sumOk">{{ ok }}</div>
    <div class="lbl">Актуални</div>
  </div>
  <div class="summary-item">
    <div class="num num-warn" id="sumIssues">{{ issues }}</div>
    <div class="lbl">Проблеми</div>
  </div>
  <div class="summary-item">
    <div class="num num-err" id="sumErrors">{{ errors }}</div>
    <div class="lbl">Грешки</div>
  </div>
</div>

<div class="log-toggle">
  <button onclick="toggleLog()">📋 Лог</button>
</div>
<div class="log-panel" id="logPanel"></div>

<div class="results" id="results">
  {{ report_html | safe }}
</div>

<script>
let pollTimer = null;

function startCheck(e) {
  e.preventDefault();
  const year      = document.getElementById('year').value;
  const city      = document.getElementById('city').value;
  const sendEmail = document.getElementById('sendEmail').checked;

  setStatus('running', '<span class="spinner"></span> Проверката е в ход...');
  document.getElementById('runBtn').disabled = true;
  document.getElementById('results').innerHTML = '';

  fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({year, city: city || null, send_email: sendEmail})
  }).then(r => r.json()).then(d => {
    if (d.status === 'started') {
      pollTimer = setInterval(pollStatus, 2000);
    } else {
      setStatus('done', d.message || 'Готово');
      document.getElementById('runBtn').disabled = false;
    }
  }).catch(() => {
    setStatus('done', '❌ Грешка при свързване');
    document.getElementById('runBtn').disabled = false;
  });
}

function pollStatus() {
  fetch('/status').then(r => r.json()).then(d => {
    updateLog(d.log_lines || []);
    if (!d.running) {
      clearInterval(pollTimer);
      pollTimer = null;
      setStatus('done', '✅ Проверката завърши — ' + (d.last_run || ''));
      document.getElementById('runBtn').disabled = false;
      document.getElementById('lastRun').textContent = d.last_run || '';
      if (d.summary) {
        document.getElementById('sumTotal').textContent  = d.summary.total;
        document.getElementById('sumOk').textContent     = d.summary.ok;
        document.getElementById('sumIssues').textContent = d.summary.issues;
        document.getElementById('sumErrors').textContent = d.summary.errors;
        document.getElementById('summary').style.display = '';
      }
      const html = d.report_html || '';
      const resultsEl = document.getElementById('results');
      resultsEl.innerHTML = html;
    }
  }).catch(err => {
    console.error('Poll error:', err);
  });
}

function setStatus(type, msg) {
  const bar = document.getElementById('statusBar');
  bar.className = 'status-bar ' + type;
  bar.innerHTML = msg;
}

function updateLog(lines) {
  const panel = document.getElementById('logPanel');
  if (panel.classList.contains('visible')) {
    panel.innerHTML = lines.map(l => escHtml(l)).join('<br>');
    panel.scrollTop = panel.scrollHeight;
  }
}

function toggleLog() {
  const panel = document.getElementById('logPanel');
  panel.classList.toggle('visible');
  if (panel.classList.contains('visible')) {
    fetch('/status').then(r => r.json()).then(d => updateLog(d.log_lines || []));
  }
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function toggleSection(el) {
  const content = el.nextElementSibling;
  const icon = el.querySelector('.toggle-icon');
  content.classList.toggle('open');
  icon.classList.toggle('open');
}

function toggleProject(header) {
  const card = header.closest('.project-card');
  card.classList.toggle('collapsed');
}

function loadCachedReport(index) {
  fetch('/cache/' + index).then(r => r.json()).then(d => {
    if (d.html) {
      document.getElementById('results').innerHTML = d.html;
      document.getElementById('lastRun').textContent = d.timestamp;
      if (d.summary) {
        document.getElementById('sumTotal').textContent  = d.summary.total;
        document.getElementById('sumOk').textContent     = d.summary.ok;
        document.getElementById('sumIssues').textContent = d.summary.issues;
        document.getElementById('sumErrors').textContent = d.summary.errors;
        document.getElementById('summary').style.display = '';
      }
      setStatus('done', '📚 Зареден рапорт от ' + d.timestamp);
    }
  }).catch(err => {
    console.error('Cache load error:', err);
    setStatus('done', '❌ Грешка при зареждане на рапорт');
  });
}

// При зареждане на страницата — ако има готов рапорт, зареди го
window.addEventListener('DOMContentLoaded', function() {
  {% if running %}
  document.getElementById('runBtn').disabled = true;
  setStatus('running', '<span class="spinner"></span> Проверката е в ход...');
  pollTimer = setInterval(pollStatus, 2000);
  {% elif last_run %}
  // Рапортът е вграден в страницата от Jinja2 — само покажи summary
  document.getElementById('summary').style.display = '';
  {% endif %}
});
</script>
</body>
</html>"""


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    report = state["last_report"] or {}
    projects = report.get("projects", [])
    total  = len(projects)
    ok     = sum(1 for p in projects if p.get("status") == "Актуален")
    issues = sum(1 for p in projects if p.get("status") == "Има проблеми")
    errors = len(report.get("errors", []))

    return render_template_string(
        PAGE_TEMPLATE,
        current_year = str(datetime.now().year),
        last_run     = state["last_run"] or "",
        report_html  = state["last_html"],
        running      = state["running"],
        report_cache = state["report_cache"],
        total=total, ok=ok, issues=issues, errors=errors,
    )


@app.route("/run", methods=["POST"])
def run_endpoint():
    if state["running"]:
        return jsonify({"status": "busy", "message": "Проверката вече е в ход."})
    data       = request.get_json(force=True)
    year       = data.get("year", str(datetime.now().year))
    city       = data.get("city") or None
    send_email = bool(data.get("send_email", False))
    t = threading.Thread(target=run_check, args=(year, city, send_email), daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/status")
def status_endpoint():
    report   = state["last_report"] or {}
    projects = report.get("projects", [])
    total    = len(projects)
    ok       = sum(1 for p in projects if p.get("status") == "Актуален")
    issues   = sum(1 for p in projects if p.get("status") == "Има проблеми")
    errors   = len(report.get("errors", []))
    return jsonify({
        "running":     state["running"],
        "last_run":    state["last_run"],
        "log_lines":   state["log_lines"][-100:],
        "report_html": state["last_html"],
        "summary":     {"total": total, "ok": ok, "issues": issues, "errors": errors},
    })


@app.route("/debug")
def debug_endpoint():
    """Debug endpoint — показва raw данни за диагностика."""
    report   = state["last_report"] or {}
    projects = report.get("projects", [])
    info = {
        "running":        state["running"],
        "last_run":       state["last_run"],
        "html_length":    len(state["last_html"]),
        "html_preview":   state["last_html"][:500] if state["last_html"] else "(empty)",
        "projects_count": len(projects),
        "projects_names": [p.get("name","?") for p in projects[:10]],
        "errors":         report.get("errors", []),
        "cache_count":    len(state["report_cache"]),
    }
    return jsonify(info)


@app.route("/cache/<int:index>")
def cache_endpoint(index):
    """Връща кеширан рапорт по индекс."""
    if 0 <= index < len(state["report_cache"]):
        entry = state["report_cache"][index]
        return jsonify({
            "timestamp": entry["timestamp"],
            "year":      entry["year"],
            "city":      entry["city"],
            "html":      entry["html"],
            "summary":   entry["summary"],
        })
    return jsonify({"error": "Invalid index"}), 404


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("🚀 Сървърът стартира на порт %d", port)
    log.info("   Достъп: http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
