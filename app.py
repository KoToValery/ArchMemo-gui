#!/usr/bin/env python3
"""
Project Delivery Checker — Flask уеб сървър
"""

import os
import sys
import json
import glob
import threading
import logging
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

sys.path.insert(0, '/home/koto/onedrive-env/lib/python3.14/site-packages')

from checker import ProjectChecker, OUTPUT_DIR, CLOUD_ROOT, log
from html_builder import build_html_report

from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

SCAN_YEARS  = ["2024", "2025", "2026"]
MAX_LOG_LINES = 200

# ─── Глобален стейт ───────────────────────────────────────────────────────────
# disk_cache: { "2025_БЛАГОЕВГРАД": {timestamp, year, city, projects, summary}, ... }
state = {
    "running":    False,
    "log_lines":  [],
    "disk_cache": {},   # зареден от диск при старт
    "hidden_ids": set(), # скрити проекти (project full_path като id)
}


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


# ─── Зареждане на кеш от диск при старт ──────────────────────────────────────
def load_disk_cache():
    """Зарежда всички cache_*.json файлове от OUTPUT_DIR."""
    pattern = os.path.join(OUTPUT_DIR, "cache_*.json")
    for fpath in glob.glob(pattern):
        try:
            with open(fpath, encoding="utf-8") as f:
                report = json.load(f)
            year = report.get("year", "")
            city = report.get("city", "ALL")
            key  = _cache_key(year, city)
            projects = report.get("projects", [])
            state["disk_cache"][key] = {
                "timestamp": report.get("check_date", "")[:16].replace("T", " "),
                "year":      year,
                "city":      city,
                "projects":  projects,
                "summary":   _calc_summary(projects, report.get("errors", [])),
            }
            log.info("📂 Зареден кеш: %s (%d проекта)", key, len(projects))
        except Exception as exc:
            log.warning("Грешка при зареждане на %s: %s", fpath, exc)

def _cache_key(year: str, city: str) -> str:
    return f"{year}_{(city or 'ALL').upper()}"

def _calc_summary(projects: list, errors: list) -> dict:
    return {
        "total":  len(projects),
        "ok":     sum(1 for p in projects if p.get("status") == "Актуален"),
        "issues": sum(1 for p in projects if p.get("status") == "Има проблеми"),
        "errors": len(errors),
    }


# ─── Запис на кеш в диск ──────────────────────────────────────────────────────
def save_cache_entry(year: str, city: str, report: dict):
    projects = report.get("projects", [])
    city_name = (city or "ALL").upper()
    key = _cache_key(year, city_name)
    state["disk_cache"][key] = {
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "year":      year,
        "city":      city_name,
        "projects":  projects,
        "summary":   _calc_summary(projects, report.get("errors", [])),
    }

    # Презаписване на файла на диска
    label = f"{year}_{city_name.lower()}"
    fpath = os.path.join(OUTPUT_DIR, f"cache_{label}.json")
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log.info("💾 Кешът е записан на диск: %s", fpath)
    except Exception as exc:
        log.error("Грешка при запис на кеш %s: %s", fpath, exc)


# ─── Генериране на HTML от проекти ────────────────────────────────────────────
def _build_full_html(projects: list, year: str, city: str | None,
                     show_hidden: bool = False, hidden_ids: set = None) -> str:
    if hidden_ids is None:
        hidden_ids = set()
    if not projects:
        return '<div class="no-results">Няма намерени проекти.</div>'

    parts = []
    for p in projects:
        pid = p.get("full_path", p.get("name", ""))
        is_hidden = pid in hidden_ids
        if is_hidden and not show_hidden:
            continue
        try:
            if not p.get("pln_name"):
                parts.append(f"""
                <div class="project-card status-only{' hidden-card' if is_hidden else ''}" data-pid="{pid}">
                  <div class="card-header">
                    <div class="card-title-row">
                      <div class="card-title">🏗 {p['name']} {('(' + p['location'] + ')') if p.get('location') else ''}</div>
                      <button class="hide-btn" onclick="toggleHide(event,'{pid}')" title="Скрий/Покажи">👁</button>
                    </div>
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
                project_id         = pid,
                is_hidden          = is_hidden,
            )
            parts.append(html)
        except Exception as exc:
            log.error("Грешка при рендиране на %s: %s", p.get("name", "?"), exc)
            parts.append(f'<div class="project-card status-only"><div class="card-header">'
                         f'<div class="card-title">⚠ {p.get("name","?")} — грешка</div>'
                         f'<div class="card-meta">{exc}</div></div></div>')
    return "\n".join(parts) if parts else '<div class="no-results">Всички проекти са скрити.</div>'


# ─── Проверка ─────────────────────────────────────────────────────────────────
def run_check(year: str, city: str | None, send_email: bool = False):
    if state["running"]:
        log.warning("Проверката вече е в ход — пропускам.")
        return
    state["running"]   = True
    state["log_lines"] = []
    log.info("🔍 Стартиране: година=%s, град=%s", year, city or "всички")
    try:
        checker = ProjectChecker(year=year, city=city, send_email=send_email)
        report  = checker.run()
        save_cache_entry(year, city, report)
        log.info("✅ Завърши: %d проекта", len(report.get("projects", [])))
    except Exception as exc:
        log.error("❌ Грешка: %s", exc, exc_info=True)
    finally:
        state["running"] = False


def run_full_scan():
    """Пълно сканиране на всички години 2024-2026."""
    log.info("🔄 Пълно сканиране 2024-2026...")
    for year in SCAN_YEARS:
        run_check(year=year, city=None, send_email=False)
    log.info("✅ Пълното сканиране завърши.")


# ─── Scheduler ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Europe/Sofia")
scheduler.add_job(run_full_scan, "cron", hour=8, minute=0)
scheduler.start()

# Зареди кеш от диск при старт
load_disk_cache()


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

  .topbar { background: var(--header); color: #fff; padding: 14px 16px;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
  .topbar h1 { font-size: 17px; font-weight: 600; }
  .topbar .last-run { font-size: 12px; color: #bdc3c7; }

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
  .form-group select { appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%237f8c8d' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; padding-right: 32px; }
  .checkbox-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
  .checkbox-row input[type=checkbox] { width: 18px; height: 18px; cursor: pointer; }
  .checkbox-row label { font-size: 14px; cursor: pointer; }
  .btn { padding: 10px 20px; border: none; border-radius: 7px; font-size: 15px;
         font-weight: 600; cursor: pointer; transition: opacity .2s; }
  .btn:active { opacity: .8; }
  .btn-primary   { background: var(--accent); color: #fff; }
  .btn-secondary { background: #ecf0f1; color: var(--text); }
  .btn-danger    { background: var(--err); color: #fff; }
  .btn:disabled  { opacity: .5; cursor: not-allowed; }

  .cache-wrap { background: var(--card); padding: 12px 16px; margin: 0 12px 12px;
                border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  .cache-title { font-size: 13px; font-weight: 600; color: var(--muted);
                 margin-bottom: 8px; text-transform: uppercase; letter-spacing: .5px; }
  .cache-list { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; flex-wrap: wrap; }
  .cache-item { min-width: 130px; padding: 10px 12px; background: #f8f9fa;
                border-radius: 7px; cursor: pointer; transition: all .2s;
                border: 2px solid transparent; }
  .cache-item:hover { background: #e9ecef; border-color: var(--accent); }
  .cache-item.active { border-color: var(--accent); background: #eaf4fb; }
  .cache-time { font-size: 11px; color: var(--muted); font-weight: 600; }
  .cache-info { font-size: 13px; color: var(--text); margin: 4px 0; }
  .cache-summary { display: flex; gap: 6px; margin-top: 6px; }
  .cache-badge { display: inline-block; padding: 2px 6px; border-radius: 4px;
                 font-size: 11px; font-weight: 700; color: #fff; }
  .cache-badge.ok   { background: var(--ok); }
  .cache-badge.warn { background: var(--warn); }
  .cache-badge.err  { background: var(--err); }

  #contextMenu { position: fixed; background: #fff; border: 1px solid #ddd;
                 box-shadow: 2px 2px 10px rgba(0,0,0,0.15); border-radius: 6px;
                 padding: 5px 0; min-width: 140px; display: none; z-index: 1000; }
  #contextMenu div { padding: 8px 15px; font-size: 13px; cursor: pointer; color: var(--text); }
  #contextMenu div:hover { background: #f8f9fa; color: var(--err); }

  .status-bar { margin: 0 12px 8px; padding: 10px 14px; border-radius: 8px;
                font-size: 13px; display: none; }
  .status-bar.running { display: block; background: #eaf4fb; color: var(--info);
                         border: 1px solid #aed6f1; }
  .status-bar.done    { display: block; background: #eafaf1; color: var(--ok);
                         border: 1px solid #a9dfbf; }

  .toolbar { display: flex; gap: 8px; align-items: center; margin: 0 12px 8px; flex-wrap: wrap; }

  .summary { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 12px 12px; }
  .summary-item { flex: 1; min-width: 80px; background: var(--card); border-radius: 8px;
                  padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .summary-item .num { font-size: 26px; font-weight: 700; }
  .summary-item .lbl { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .num-ok   { color: var(--ok); }
  .num-warn { color: var(--warn); }
  .num-err  { color: var(--err); }
  .num-all  { color: var(--accent); }

  .results { padding: 0 12px 24px; }
  .project-card { background: var(--card); border-radius: 10px; margin-bottom: 14px;
                  box-shadow: 0 1px 4px rgba(0,0,0,.1); overflow: hidden; }
  .project-card.hidden-card { opacity: 0.45; }
  .card-header { background: var(--header); padding: 14px 16px; cursor: pointer;
                 user-select: none; transition: background .2s; }
  .card-header:hover { background: #34495e; }
  .card-title-row { display: flex; align-items: center; gap: 10px; }
  .card-title-row .toggle-icon { font-size: 12px; transition: transform .2s;
                                  color: #bdc3c7; min-width: 12px; }
  .project-card:not(.collapsed) .card-header .toggle-icon { transform: rotate(90deg); }
  .card-title  { color: #fff; font-size: 15px; font-weight: 600; flex: 1; }
  .card-meta   { color: #bdc3c7; font-size: 12px; margin-top: 3px; }
  .card-path   { color: #95a5a6; font-size: 11px; margin-top: 2px; word-break: break-all; }
  .card-body   { display: none; }
  .project-card:not(.collapsed) .card-body { display: block; }
  .card-section { padding: 14px 16px; border-top: 1px solid var(--border); }
  .section-title { font-weight: 600; font-size: 13px; color: var(--muted);
                   text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
  .status-only .card-header { background: #636e72; cursor: default; }
  .status-only .card-header:hover { background: #636e72; }

  .hide-btn { background: none; border: none; cursor: pointer; font-size: 14px;
              padding: 2px 6px; border-radius: 4px; color: #bdc3c7;
              transition: background .15s; flex-shrink: 0; }
  .hide-btn:hover { background: rgba(255,255,255,.15); }

  .info-table, .spec-table, .doc-table {
    width: 100%; border-collapse: collapse; font-size: 13px; }
  .info-table td, .spec-table td, .spec-table th, .doc-table td {
    padding: 7px 6px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .spec-table th { background: #f8f9fa; font-weight: 600; font-size: 12px;
                   color: var(--muted); text-align: left; }
  .detail, .date { color: var(--muted); font-size: 12px; }
  .empty { color: var(--muted); font-style: italic; font-size: 12px; padding: 8px 6px; }

  .badge { display: inline-block; padding: 2px 7px; border-radius: 4px;
           font-size: 11px; font-weight: 700; color: #fff; }
  .badge-ok     { background: var(--ok); }
  .badge-warn   { background: var(--warn); }
  .badge-err    { background: var(--err); }
  .badge-info   { background: var(--info); }
  .badge-purple { background: var(--purple); }
  .badge-teal   { background: var(--teal); }
  .badge-gray   { background: var(--gray); }

  .outdated-list { margin-top: 10px; padding: 10px 12px; background: #fef9f0;
                   border-left: 3px solid var(--warn); border-radius: 4px; font-size: 12px; }
  .outdated-list ul { margin: 6px 0 0 16px; }
  .outdated-list li { margin-bottom: 2px; color: var(--muted); }

  .collapsible .section-title { cursor: pointer; user-select: none; display: flex;
                                 justify-content: space-between; align-items: center; }
  .collapsible .section-title:hover { color: var(--accent); }
  .toggle-icon { font-size: 10px; transition: transform .2s; }
  .toggle-icon.open { transform: rotate(-180deg); }
  .section-content { margin-top: 10px; display: none; }
  .section-content.open { display: block; }

  .link-btn { background: none; border: 1px solid #ddd; border-radius: 4px;
              padding: 2px 8px; font-size: 11px; cursor: pointer; color: var(--info);
              transition: all .15s; }
  .link-btn:hover { background: var(--info); color: #fff; border-color: var(--info); }
  .link-btn.loading { opacity: .6; cursor: wait; }

  .log-toggle { margin: 0 12px 8px; }
  .log-toggle button { background: none; border: 1px solid #ddd; border-radius: 6px;
                        padding: 6px 12px; font-size: 12px; cursor: pointer; color: var(--muted); }
  .log-panel { display: none; margin: 0 12px 12px; background: #1e272e; color: #dfe6e9;
               border-radius: 8px; padding: 12px; font-family: monospace; font-size: 11px;
               max-height: 250px; overflow-y: auto; }
  .log-panel.visible { display: block; }

  .no-results { text-align: center; padding: 40px; color: var(--muted); font-size: 15px; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid currentColor;
             border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite;
             vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }

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
      <div class="form-group" style="flex:0">
        <label>&nbsp;</label>
        <button type="button" class="btn btn-danger" id="fullScanBtn" onclick="startFullScan()">🔄 Пълно сканиране</button>
      </div>
    </div>
    <div class="checkbox-row" style="margin-top:10px">
      <input type="checkbox" id="sendEmail" name="sendEmail">
      <label for="sendEmail">📧 Изпрати имейл при проблеми</label>
    </div>
  </form>
</div>

{% if cache_entries %}
<div class="cache-wrap">
  <div class="cache-title">📚 Налични данни (десен бутон за изтриване)</div>
  <div class="cache-list" id="cacheList">
    {% for key, entry in cache_entries %}
    <div class="cache-item" id="ci-{{ key }}" onclick="loadFromCache('{{ key }}')" oncontextmenu="showContextMenu(event, '{{ key }}')">
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

<div id="contextMenu">
  <div onclick="deleteCache()">🗑 Изтрий кеша</div>
</div>

<div class="status-bar" id="statusBar"></div>

<div class="toolbar" id="toolbar" style="display:none">
  <div class="summary" style="margin:0; flex:1">
    <div class="summary-item">
      <div class="num num-all" id="sumTotal">0</div>
      <div class="lbl">Общо</div>
    </div>
    <div class="summary-item">
      <div class="num num-ok" id="sumOk">0</div>
      <div class="lbl">Актуални</div>
    </div>
    <div class="summary-item">
      <div class="num num-warn" id="sumIssues">0</div>
      <div class="lbl">Проблеми</div>
    </div>
    <div class="summary-item">
      <div class="num num-err" id="sumErrors">0</div>
      <div class="lbl">Грешки</div>
    </div>
  </div>
  <div class="checkbox-row">
    <input type="checkbox" id="showHidden" onchange="toggleShowHidden()">
    <label for="showHidden">Покажи скрити</label>
  </div>
</div>

<div class="log-toggle">
  <button onclick="toggleLog()">📋 Лог</button>
</div>
<div class="log-panel" id="logPanel"></div>

<div class="results" id="results"></div>

<script>
let pollTimer   = null;
let currentKey  = null;
let menuKey     = null;

function showContextMenu(e, key) {
  e.preventDefault();
  menuKey = key;
  const menu = document.getElementById('contextMenu');
  menu.style.display = 'block';
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
  
  // Close menu on click elsewhere
  document.addEventListener('click', hideContextMenu, { once: true });
}

function hideContextMenu() {
  document.getElementById('contextMenu').style.display = 'none';
}

function deleteCache() {
  if (!menuKey) return;
  if (!confirm('Сигурни ли сте, че искате да изтриете този кеш?')) return;
  
  fetch('/delete_cache', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({key: menuKey})
  }).then(r => r.json()).then(d => {
    if (d.status === 'deleted') {
      const el = document.getElementById('ci-' + menuKey);
      if (el) el.remove();
      if (currentKey === menuKey) {
        document.getElementById('results').innerHTML = '';
        document.getElementById('toolbar').style.display = 'none';
        currentKey = null;
      }
      updateFilters();
    }
  });
}

function startCheck(e) {
  e.preventDefault();
  const year      = document.getElementById('year').value;
  const city      = document.getElementById('city').value;
  const sendEmail = document.getElementById('sendEmail').checked;
  const key       = year + '_' + (city || 'ALL');

  // Ако има кеш — зареди веднага, после провери дали да сканира
  if (hasCacheEntry(key)) {
    loadFromCache(key);
    return;
  }

  runScan(year, city || null, sendEmail);
}

function hasCacheEntry(key) {
  return !!document.getElementById('ci-' + key);
}

function runScan(year, city, sendEmail) {
  setStatus('running', '<span class="spinner"></span> Проверката е в ход...');
  document.getElementById('runBtn').disabled = true;
  document.getElementById('fullScanBtn').disabled = true;

  fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({year, city, send_email: sendEmail || false})
  }).then(r => r.json()).then(d => {
    if (d.status === 'started') {
      pollTimer = setInterval(pollStatus, 2000);
    } else {
      setStatus('done', d.message || 'Готово');
      document.getElementById('runBtn').disabled = false;
      document.getElementById('fullScanBtn').disabled = false;
    }
  }).catch(() => {
    setStatus('done', '❌ Грешка при свързване');
    document.getElementById('runBtn').disabled = false;
    document.getElementById('fullScanBtn').disabled = false;
  });
}

function startFullScan() {
  if (!confirm('Ще се сканират всички години 2024-2026. Продължи?')) return;
  setStatus('running', '<span class="spinner"></span> Пълно сканиране в ход...');
  document.getElementById('runBtn').disabled = true;
  document.getElementById('fullScanBtn').disabled = true;
  fetch('/run_full', {method: 'POST'}).then(r => r.json()).then(d => {
    if (d.status === 'started') {
      pollTimer = setInterval(pollStatus, 2000);
    }
  });
}

function pollStatus() {
  fetch('/status').then(r => r.json()).then(d => {
    updateLog(d.log_lines || []);
    if (!d.running) {
      clearInterval(pollTimer);
      pollTimer = null;
      document.getElementById('runBtn').disabled = false;
      document.getElementById('fullScanBtn').disabled = false;
      setStatus('done', '✅ Завърши — ' + (d.last_scan || ''));
      // Обнови cache list
      if (d.cache_entries) refreshCacheList(d.cache_entries);
      // Ако текущо зареденият ключ е обновен — презареди
      if (currentKey && d.updated_keys && d.updated_keys.includes(currentKey)) {
        loadFromCache(currentKey);
      }
    }
  }).catch(err => console.error('Poll error:', err));
}

function loadFromCache(key) {
  currentKey = key;
  document.querySelectorAll('.cache-item').forEach(el => el.classList.remove('active'));
  const ci = document.getElementById('ci-' + key);
  if (ci) ci.classList.add('active');

  const showHidden = document.getElementById('showHidden').checked;
  fetch('/load_cache?key=' + encodeURIComponent(key) + '&show_hidden=' + showHidden)
    .then(r => r.json()).then(d => {
      if (d.error) { setStatus('done', '❌ ' + d.error); return; }
      document.getElementById('results').innerHTML = d.html;
      document.getElementById('lastRun').textContent = d.timestamp;
      document.getElementById('sumTotal').textContent  = d.summary.total;
      document.getElementById('sumOk').textContent     = d.summary.ok;
      document.getElementById('sumIssues').textContent = d.summary.issues;
      document.getElementById('sumErrors').textContent = d.summary.errors;
      document.getElementById('toolbar').style.display = '';
      setStatus('done', '📂 ' + d.year + ' / ' + d.city + ' — ' + d.timestamp);
    });
}

function toggleShowHidden() {
  if (currentKey) loadFromCache(currentKey);
}

function toggleHide(event, pid) {
  event.stopPropagation();
  fetch('/toggle_hide', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pid})
  }).then(r => r.json()).then(d => {
    if (currentKey) loadFromCache(currentKey);
  });
}

function getShareLink(btn, itemId) {
  btn.classList.add('loading');
  btn.textContent = '⏳';
  fetch('/share_link?item_id=' + encodeURIComponent(itemId))
    .then(r => r.json()).then(d => {
      if (d.url) {
        const a = document.createElement('a');
        a.href = d.url; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = '🔗 Отвори';
        btn.replaceWith(a);
      } else {
        btn.textContent = '❌';
        btn.classList.remove('loading');
      }
    }).catch(() => { btn.textContent = '❌'; btn.classList.remove('loading'); });
}

function refreshCacheList(entries) {
  const list = document.getElementById('cacheList');
  if (!list) return;
  entries.forEach(([key, entry]) => {
    let el = document.getElementById('ci-' + key);
    if (!el) {
      el = document.createElement('div');
      el.className = 'cache-item';
      el.id = 'ci-' + key;
      el.onclick = () => loadFromCache(key);
      el.oncontextmenu = (e) => showContextMenu(e, key);
      list.appendChild(el);
    }
    el.innerHTML = `<div class="cache-time">${entry.timestamp}</div>
      <div class="cache-info">${entry.year} / ${entry.city}</div>
      <div class="cache-summary">
        <span class="cache-badge ok">${entry.summary.ok}</span>
        <span class="cache-badge warn">${entry.summary.issues}</span>
        <span class="cache-badge err">${entry.summary.errors}</span>
      </div>`;
  });
  updateFilters();
}

function updateFilters() {
  const yearsSet = new Set(['2024', '2025', '2026']);
  const citiesSet = new Set(['БЛАГОЕВГРАД', 'СОФИЯ', 'БАНСКО', 'РАЗЛОГ', 'САМОКОВ', 'КЮСТЕНДИЛ']);
  
  // Collect from current cache items
  document.querySelectorAll('.cache-item').forEach(el => {
    const info = el.querySelector('.cache-info').textContent;
    const parts = info.split(' / ');
    if (parts.length === 2) {
      yearsSet.add(parts[0].trim());
      if (parts[1].trim() !== 'ALL') citiesSet.add(parts[1].trim());
    }
  });

  const yearSelect = document.getElementById('year');
  const citySelect = document.getElementById('city');
  const currentYear = yearSelect.value;
  const currentCity = citySelect.value;

  // Update years
  yearSelect.innerHTML = Array.from(yearsSet).sort().reverse().map(y => 
    `<option value="${y}" ${y === currentYear ? 'selected' : ''}>${y}</option>`
  ).join('');

  // Update cities
  citySelect.innerHTML = '<option value="">Всички градове</option>' + 
    Array.from(citiesSet).sort().map(c => 
      `<option value="${c}" ${c === currentCity ? 'selected' : ''}>${c}</option>`
    ).join('');
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
  header.closest('.project-card').classList.toggle('collapsed');
}

window.addEventListener('DOMContentLoaded', function() {
  updateFilters();
  {% if running %}
  document.getElementById('runBtn').disabled = true;
  document.getElementById('fullScanBtn').disabled = true;
  setStatus('running', '<span class="spinner"></span> Проверката е в ход...');
  pollTimer = setInterval(pollStatus, 2000);
  {% elif default_key %}
  loadFromCache('{{ default_key }}');
  {% endif %}
});
</script>
</body>
</html>"""


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    cache_entries = sorted(state["disk_cache"].items(), reverse=True)
    # Намери най-новия запис за текущата година като default
    cur_year = str(datetime.now().year)
    default_key = next(
        (k for k, _ in cache_entries if k.startswith(cur_year + "_ALL")),
        cache_entries[0][0] if cache_entries else None
    )
    return render_template_string(
        PAGE_TEMPLATE,
        current_year  = cur_year,
        last_run      = "",
        running       = state["running"],
        cache_entries = cache_entries,
        default_key   = default_key or "",
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


@app.route("/run_full", methods=["POST"])
def run_full_endpoint():
    if state["running"]:
        return jsonify({"status": "busy", "message": "Проверката вече е в ход."})
    t = threading.Thread(target=run_full_scan, daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/status")
def status_endpoint():
    return jsonify({
        "running":       state["running"],
        "last_scan":     datetime.now().strftime("%d.%m.%Y %H:%M"),
        "log_lines":     state["log_lines"][-100:],
        "cache_entries": list(state["disk_cache"].items()),
        "updated_keys":  list(state["disk_cache"].keys()),
    })


@app.route("/load_cache")
def load_cache_endpoint():
    key         = request.args.get("key", "")
    show_hidden = request.args.get("show_hidden", "false").lower() == "true"
    entry = state["disk_cache"].get(key)
    if not entry:
        return jsonify({"error": f"Няма данни за {key}"})
    html = _build_full_html(
        entry["projects"], entry["year"], entry["city"],
        show_hidden=show_hidden, hidden_ids=state["hidden_ids"]
    )
    return jsonify({
        "html":      html,
        "timestamp": entry["timestamp"],
        "year":      entry["year"],
        "city":      entry["city"],
        "summary":   entry["summary"],
    })


@app.route("/toggle_hide", methods=["POST"])
def toggle_hide_endpoint():
    pid = request.get_json(force=True).get("pid", "")
    if pid in state["hidden_ids"]:
        state["hidden_ids"].discard(pid)
        hidden = False
    else:
        state["hidden_ids"].add(pid)
        hidden = True
    return jsonify({"hidden": hidden})


@app.route("/delete_cache", methods=["POST"])
def delete_cache_endpoint():
    key = request.get_json(force=True).get("key", "")
    if not key or key not in state["disk_cache"]:
        return jsonify({"error": "Невалиден ключ за кеш"}), 400
    
    entry = state["disk_cache"][key]
    year = entry["year"]
    city = entry["city"].lower()
    label = f"{year}_{city}"
    fpath = os.path.join(OUTPUT_DIR, f"cache_{label}.json")
    
    try:
        if os.path.exists(fpath):
            os.remove(fpath)
            log.info("🗑 Изтрит кеш файл: %s", fpath)
        
        del state["disk_cache"][key]
        return jsonify({"status": "deleted"})
    except Exception as exc:
        log.error("Грешка при изтриване на кеш %s: %s", fpath, exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/share_link")
def share_link_endpoint():
    """Генерира sharing link при заявка (lazy)."""
    item_id = request.args.get("item_id", "")
    if not item_id:
        return jsonify({"error": "Няма item_id"}), 400
    try:
        checker = ProjectChecker.__new__(ProjectChecker)
        checker.last_request_ts    = 0.0
        checker._sharing_link_cache = {}
        checker.token   = None
        checker.headers = None
        if not checker.get_token():
            return jsonify({"error": "Не може да се получи токен"}), 500
        url = checker._get_sharing_link(item_id)
        return jsonify({"url": url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/debug")
def debug_endpoint():
    return jsonify({
        "running":      state["running"],
        "cache_keys":   list(state["disk_cache"].keys()),
        "hidden_count": len(state["hidden_ids"]),
    })


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("🚀 Сървърът стартира на порт %d", port)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
