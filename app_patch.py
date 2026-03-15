#!/usr/bin/env python3
import io
import os
import sys

APP_FILE = "app.py"

OLD_BLOCK = """function refreshCacheList(entries) {
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
    el.innerHTML = `<div class="cache-time">\${entry.timestamp}</div>
      <div class="cache-info">\${entry.year} / \${entry.city}</div>
      <div class="cache-summary">
        <span class="cache-badge ok">\${entry.summary.ok}</span>
        <span class="cache-badge warn">\${entry.summary.issues}</span>
        <span class="cache-badge err">\${entry.summary.errors}</span>
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
    `<option value="\${y}" \${y === currentYear ? 'selected' : ''}>\${y}</option>`
  ).join('');


  // Update cities
  citySelect.innerHTML = '<option value=\"\">Всички градове</option>' + 
    Array.from(citiesSet).sort().map(c => 
      `<option value="\${c}" \${c === currentCity ? 'selected' : ''}>\${c}</option>`
    ).join('');
}
"""

NEW_BLOCK = """function getCacheItems() {
  return Array.from(document.querySelectorAll('.cache-item')).map(el => ({
    key: el.dataset.key,
    year: el.dataset.year,
    city: el.dataset.city
  }));
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
    el.dataset.key = key;
    el.dataset.year = entry.year;
    el.dataset.city = entry.city;
    el.innerHTML = `<div class="cache-time">\${entry.timestamp}</div>
      <div class="cache-info">\${entry.year} / \${entry.city}</div>
      <div class="cache-summary">
        <span class="cache-badge ok">\${entry.summary.ok}</span>
        <span class="cache-badge warn">\${entry.summary.issues}</span>
        <span class="cache-badge err">\${entry.summary.errors}</span>
      </div>`;
  });
  updateFilters();
}

function updateFilters() {
  const items = getCacheItems();
  const yearSelect = document.getElementById('year');
  const citySelect = document.getElementById('city');

  const currentYear = yearSelect.value || new Date().getFullYear().toString();
  const currentCity = citySelect.value || '';

  const years = [...new Set(items.map(i => i.year))].sort().reverse();
  yearSelect.innerHTML = years
    .map(y => `<option value="\${y}" \${y === currentYear ? 'selected' : ''}>\${y}</option>`)
    .join('');

  const selectedYear = yearSelect.value;
  const cities = [...new Set(
    items
      .filter(i => i.year === selectedYear && i.city !== 'ALL')
      .map(i => i.city)
  )].sort();

  const cityStillExists = cities.includes(currentCity);
  citySelect.innerHTML =
    '<option value=\"\">Всички градове</option>' +
    cities
      .map(c => `<option value="\${c}" \${c === currentCity && cityStillExists ? 'selected' : ''}>\${c}</option>`)
      .join('');

  if (!cityStillExists) {
    citySelect.value = '';
  }
}

function autoLoadSelectedCache() {
  const year = document.getElementById('year').value;
  const city = document.getElementById('city').value;
  const exactKey = `${year}_${(city || 'ALL').toUpperCase()}`;
  const allKey = `${year}_ALL`;

  if (document.getElementById(`ci-${exactKey}`)) {
    loadFromCache(exactKey);
    return;
  }
  if (!city && document.getElementById(`ci-${allKey}`)) {
    loadFromCache(allKey);
    return;
  }
  if (city && document.getElementById(`ci-${allKey}`)) {
    loadFromCache(allKey);
    return;
  }
  document.getElementById('results').innerHTML =
    '<div class="no-results">Няма кеш за избраната комбинация.</div>';
  document.getElementById('toolbar').style.display = 'none';
  currentKey = null;
}
"""

def main():
    if not os.path.exists(APP_FILE):
        print("Не намирам app.py")
        sys.exit(1)

    with io.open(APP_FILE, "r", encoding="utf-8") as f:
        txt = f.read()

    if "function getCacheItems()" in txt:
        print("Изглежда вече е патчнат (има getCacheItems). Нищо не правя.")
        sys.exit(0)

    if "function refreshCacheList(entries)" not in txt or "function updateFilters()" not in txt:
        print("Не намерих refreshCacheList/updateFilters блок за подмяна.")
        sys.exit(1)

    backup = APP_FILE + ".bak3"
    with io.open(backup, "w", encoding="utf-8") as f:
        f.write(txt)
    print("Backup:", backup)

    # по-груб replace: изваждам стария блок по сигнатурите
    start = txt.index("function refreshCacheList(entries)")
    end = txt.index("function setStatus", start)
    old = txt[start:end]
    new = NEW_BLOCK + "\n\n" + txt[end:]

    txt2 = txt[:start] + NEW_BLOCK + "\n\n" + txt[end:]

    with io.open(APP_FILE, "w", encoding="utf-8") as f:
        f.write(txt2)

    print("Готово: refreshCacheList/updateFilters са подменени.")

if __name__ == "__main__":
    main()
