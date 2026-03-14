"""HTML генератор за рапорта — използва се и от уеб интерфейса, и за имейл."""

from datetime import datetime


def build_html_report(city: str, project_name: str, full_name: str,
                      pln_name: str, pln_date_str: str,
                      delivered_count: int, outdated_arch: list,
                      delivered_files: list,
                      specialties_rows: list, specialties_detail: dict,
                      project_path: str,
                      stanovishta: dict) -> str:
    check_time = datetime.now().strftime("%d.%m.%Y %H:%M")

    arch_status_html = (
        f'<span class="badge badge-warn">⚠ {len(outdated_arch)} остарели</span>'
        if outdated_arch else
        '<span class="badge badge-ok">✔ Актуална</span>'
    )

    # Таблица на специалности с детайли
    spec_rows_html = ""
    for row in specialties_rows:
        if row["status"] == "ok":
            icon, cls, detail = "✔", "ok", f'{row["files_count"]} файла · {row["latest_date"]}'
        elif row["status"] == "outdated":
            icon, cls, detail = "⚠", "warn", f'Последен: {row["latest_date"]}'
        else:
            icon, cls, detail = "✘", "err", "Няма файлове"
        
        # Детайли за специалността (ако има)
        spec_name = row.get("folder_name", row["label"])
        spec_info = specialties_detail.get(spec_name, {})
        if isinstance(spec_info, dict) and "latest_file" in spec_info:
            detail += f'<br><small style="color:#95a5a6">📄 {spec_info["latest_file"]}</small>'
        
        spec_rows_html += f"""
        <tr>
          <td>{row['label']}</td>
          <td><span class="badge badge-{cls}">{icon}</span></td>
          <td class="detail">{detail}</td>
        </tr>"""

    # Остарели архитектурни файлове
    outdated_html = ""
    if outdated_arch:
        items = "".join(f"<li>{f}</li>" for f in outdated_arch[:20])
        if len(outdated_arch) > 20:
            items += f"<li><em>... и още {len(outdated_arch)-20}</em></li>"
        outdated_html = f'<div class="outdated-list"><strong>⚠ Остарели архитектурни файлове в ПРЕДАДЕНИ:</strong><ul>{items}</ul></div>'

    # Всички файлове в ПРЕДАДЕНИ (за детайлен преглед)
    delivered_html = ""
    if delivered_files:
        delivered_rows = "".join(
            f'<tr><td>{f["name"]}</td><td class="date">{f["date"]}</td></tr>'
            for f in delivered_files[:30]
        )
        if len(delivered_files) > 30:
            delivered_rows += f'<tr><td colspan="2" class="empty"><em>... и още {len(delivered_files)-30} файла</em></td></tr>'
        delivered_html = f"""
        <div class="card-section collapsible">
          <div class="section-title" onclick="toggleSection(this)">
            📁 Всички файлове в ПРЕДАДЕНИ ({len(delivered_files)}) <span class="toggle-icon">▼</span>
          </div>
          <div class="section-content" style="display:none">
            <table class="doc-table">{delivered_rows}</table>
          </div>
        </div>"""

    # Становища и виза
    def _doc_rows(files, badge, cls):
        return "".join(
            f'<tr><td><span class="badge badge-{cls}">{badge}</span> {f["name"]}</td>'
            f'<td class="date">{f["date"]}</td></tr>'
            for f in files
        )

    visa_badge  = '<span class="badge badge-ok">✔ Намерена</span>' if stanovishta["visa_status"] == "found" else '<span class="badge badge-err">✘ Не е намерена</span>'
    skica_badge = '<span class="badge badge-ok">✔ Намерена</span>' if stanovishta["skica_status"] == "found" else '<span class="badge badge-err">✘ Не е намерена</span>'

    all_doc_rows = (
        _doc_rows(stanovishta["visa_files"],        "ВИЗА",      "info") +
        _doc_rows(stanovishta["skica_files"],       "СКИЦА",     "purple") +
        _doc_rows(stanovishta["stanovishte_files"], "СТАНОВИЩЕ", "teal") +
        _doc_rows(stanovishta["other_files"],       "ДРУГО",     "gray")
    )
    if not all_doc_rows:
        all_doc_rows = '<tr><td colspan="2" class="empty">Папката е празна или не съществува</td></tr>'

    return f"""
<div class="project-card">
  <div class="card-header">
    <div class="card-title">🏗 {full_name}</div>
    <div class="card-meta">{city} · {check_time}</div>
    <div class="card-path">{project_path}</div>
  </div>
  <div class="card-section">
    <table class="info-table">
      <tr>
        <td>📄 Последен .pln файл</td>
        <td><strong>{pln_name}</strong></td>
        <td>{pln_date_str}</td>
      </tr>
      <tr>
        <td>📁 Файлове в Предадени</td>
        <td><strong>{delivered_count}</strong></td>
        <td>{arch_status_html}</td>
      </tr>
    </table>
    {outdated_html}
  </div>
  <div class="card-section">
    <div class="section-title">🔧 Специалности</div>
    <table class="spec-table">
      <thead><tr><th>Специалност</th><th>Статус</th><th>Детайли</th></tr></thead>
      <tbody>{spec_rows_html}</tbody>
    </table>
  </div>
  <div class="card-section">
    <div class="section-title">📋 Становища и Виза</div>
    <table class="info-table">
      <tr><td>Виза</td><td colspan="2">{visa_badge}</td></tr>
      <tr><td>Скица</td><td colspan="2">{skica_badge}</td></tr>
    </table>
    <table class="doc-table">{all_doc_rows}</table>
  </div>
  {delivered_html}
</div>"""
