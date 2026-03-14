"""HTML генератор за рапорта."""

from datetime import datetime


def _file_row(f: dict, icon: str = "") -> str:
    """Генерира таблична редица с lazy share link бутон."""
    name    = f.get("name", "")
    date    = f.get("date", "")[:10]
    item_id = f.get("item_id", "")
    # Ако вече имаме генериран линк — директен anchor
    web_url = f.get("web_url", "")
    if web_url:
        link_cell = f'<a href="{web_url}" target="_blank" rel="noopener">🔗 Отвори</a>'
    elif item_id:
        link_cell = f'<button class="link-btn" onclick="getShareLink(this,\'{item_id}\')">🔗 Линк</button>'
    else:
        link_cell = ''
    return f'<tr><td>{icon}{name}</td><td class="date">{date}</td><td>{link_cell}</td></tr>'


def build_html_report(city: str, project_name: str, full_name: str,
                      pln_name: str, pln_date_str: str,
                      delivered_count: int, outdated_arch: list,
                      delivered_files: list,
                      specialties_rows: list, specialties_detail: dict,
                      project_path: str,
                      stanovishta: dict,
                      podlozhki_files: list = None,
                      project_id: str = "",
                      is_hidden: bool = False) -> str:
    check_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    if podlozhki_files is None:
        podlozhki_files = []
    pid = project_id or project_path

    # Статус архитектура
    if outdated_arch:
        arch_status_html = f'<span class="badge badge-warn">СТАРИ ({len(outdated_arch)})</span>'
    elif delivered_count > 0:
        arch_status_html = '<span class="badge badge-ok">АКТУАЛНИ</span>'
    else:
        arch_status_html = '<span class="badge badge-err">ЛИПСВАТ</span>'

    # Специалности
    spec_rows_html = ""
    for row in specialties_rows:
        if row["status"] == "ok":
            status_text, cls = "АКТУАЛНИ", "ok"
            detail = f'{row["files_count"]} файла · {row["latest_date"]}'
        elif row["status"] == "outdated":
            status_text, cls = "СТАРИ", "warn"
            detail = f'Последен: {row["latest_date"]}'
        else:
            status_text, cls = "ЛИПСВАТ", "err"
            detail = "Няма файлове"
        spec_name = row.get("folder_name", row["label"])
        spec_info = specialties_detail.get(spec_name, {})
        if isinstance(spec_info, dict) and "latest_file" in spec_info:
            detail += f'<br><small style="color:#95a5a6">📄 {spec_info["latest_file"]}</small>'
        spec_rows_html += f"""
        <tr>
          <td>{row['label']}</td>
          <td><span class="badge badge-{cls}">{status_text}</span></td>
          <td class="detail">{detail}</td>
        </tr>"""

    # Остарели
    outdated_html = ""
    if outdated_arch:
        items = "".join(f"<li>{f}</li>" for f in outdated_arch[:20])
        if len(outdated_arch) > 20:
            items += f"<li><em>... и още {len(outdated_arch)-20}</em></li>"
        outdated_html = (f'<div class="outdated-list"><strong>⚠ Остарели архитектурни файлове '
                         f'в ПРЕДАДЕНИ:</strong><ul>{items}</ul></div>')

    # ПРЕДАДЕНИ
    delivered_html = ""
    if delivered_files:
        rows = "".join(_file_row(f) for f in delivered_files[:30])
        if len(delivered_files) > 30:
            rows += f'<tr><td colspan="3" class="empty"><em>... и още {len(delivered_files)-30} файла</em></td></tr>'
        delivered_html = f"""
        <div class="card-section collapsible">
          <div class="section-title" onclick="toggleSection(this)">
            📁 Всички файлове в ПРЕДАДЕНИ ({len(delivered_files)}) <span class="toggle-icon">▼</span>
          </div>
          <div class="section-content">
            <table class="doc-table"><thead><tr><th>Файл</th><th>Дата</th><th></th></tr></thead>
            <tbody>{rows}</tbody></table>
          </div>
        </div>"""

    # ПОДЛОЖКИ
    podlozhki_html = ""
    if podlozhki_files:
        rows = "".join(_file_row(f, "📐 ") for f in podlozhki_files)
        podlozhki_html = f"""
        <div class="card-section collapsible">
          <div class="section-title" onclick="toggleSection(this)">
            📐 ПОДЛОЖКИ ({len(podlozhki_files)}) <span class="toggle-icon">▼</span>
          </div>
          <div class="section-content">
            <table class="doc-table"><thead><tr><th>Файл</th><th>Дата</th><th></th></tr></thead>
            <tbody>{rows}</tbody></table>
          </div>
        </div>"""

    # Становища
    def _doc_rows(files, badge, cls):
        return "".join(
            f'<tr><td><span class="badge badge-{cls}">{badge}</span> {f["name"]}</td>'
            f'<td class="date">{f["date"]}</td></tr>'
            for f in files
        )

    visa_status  = stanovishta.get("visa_status", "missing")
    skica_status = stanovishta.get("skica_status", "missing")
    visa_badge   = '<span class="badge badge-ok">НАМЕРЕНА</span>' if visa_status == "found" else '<span class="badge badge-err">ЛИПСВА</span>'
    skica_badge  = '<span class="badge badge-ok">НАМЕРЕНА</span>' if skica_status == "found" else '<span class="badge badge-err">ЛИПСВА</span>'

    all_doc_rows = (
        _doc_rows(stanovishta.get("visa_files", []),        "ВИЗА",      "info") +
        _doc_rows(stanovishta.get("skica_files", []),       "СКИЦА",     "purple") +
        _doc_rows(stanovishta.get("stanovishte_files", []), "СТАНОВИЩЕ", "teal") +
        _doc_rows(stanovishta.get("other_files", []),       "ДРУГО",     "gray")
    )
    if not all_doc_rows:
        all_doc_rows = '<tr><td colspan="2" class="empty">Папката е празна или не съществува</td></tr>'

    hidden_cls  = " hidden-card" if is_hidden else ""
    pid_escaped = pid.replace('"', '&quot;')

    return f"""
<div class="project-card collapsed{hidden_cls}" data-pid="{pid_escaped}">
  <div class="card-header" onclick="toggleProject(this)">
    <div class="card-title-row">
      <span class="toggle-icon">▶</span>
      <div class="card-title">🏗 {full_name}</div>
      <button class="hide-btn" onclick="toggleHide(event,'{pid_escaped}')" title="Скрий/Покажи">👁</button>
    </div>
    <div class="card-meta">{city} · {check_time}</div>
    <div class="card-path">{project_path}</div>
  </div>
  <div class="card-body">
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
    {podlozhki_html}
  </div>
</div>"""
