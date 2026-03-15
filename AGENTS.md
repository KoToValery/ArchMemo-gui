# AGENTS.md — Документация на системата Project Delivery Checker

## Общо описание

Уеб базирана система за автоматична проверка на проектна документация съхранявана в OneDrive (Microsoft Graph API). Стартира се като Flask сървър и е достъпна от браузър в локалната мрежа или през Tailscale.

---

## Файлова структура

```
.
├── app.py           # Flask сървър, маршрути, UI шаблон, scheduler
├── checker.py       # Логика за сканиране на OneDrive
├── html_builder.py  # Генератор на HTML карти за проекти
├── git_helper.py    # Git помощни функции
├── requirements.txt # Python зависимости
└── AGENTS.md        # Тази документация
```

Персистентни данни (в `OUTPUT_DIR = ~/.openclaw/workspace/memory/`):
```
cache_2025_благоевград.json   # Кеш от сканиране по година/град
cache_2025_all.json           # Кеш за всички градове за дадена година
hidden_ids.json               # Скрити проекти (запазват се при рестарт)
project_checker.log           # Лог файл
```

---

## Архитектура

### app.py

**Глобален стейт:**
```python
state = {
    "running":    bool,   # дали сканирането е в ход
    "log_lines":  list,   # последните 200 лог реда за UI
    "disk_cache": dict,   # { "2025_БЛАГОЕВГРАД": {timestamp, year, city, projects, summary} }
    "hidden_ids": set,    # пътища на скрити проекти
}
```

**Ключови функции:**
- `load_disk_cache()` — зарежда всички `cache_*.json` при старт
- `_load_hidden_ids()` / `_save_hidden_ids()` — персистентност на скрити проекти
- `save_cache_entry(year, city, report)` — записва резултат в `disk_cache` и на диск
- `_build_full_html(projects, year, city, show_hidden, hidden_ids)` — генерира HTML от списък проекти
- `run_check(year, city, send_email)` — стартира едно сканиране в отделна нишка
- `run_full_scan()` — сканира всички години 2024–2026

**Маршрути:**

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/` | Главна страница |
| POST | `/run` | Стартира сканиране за година/град |
| POST | `/run_full` | Стартира пълно сканиране 2024–2026 |
| GET | `/status` | Polling — статус, лог, кеш ключове |
| GET | `/load_cache?key=&show_hidden=` | Зарежда HTML от кеш |
| POST | `/toggle_hide` | Скрива/показва проект `{pid}` |
| GET | `/share_link?item_id=` | Генерира OneDrive sharing link (lazy) |
| GET | `/debug` | Диагностична информация |

**Scheduler:** APScheduler стартира `run_full_scan()` всеки ден в 08:00 (Europe/Sofia).

---

### checker.py

**Клас `ProjectChecker`:**

Конструктор: `ProjectChecker(year, city=None, send_email=False)`

**Ключови методи:**

| Метод | Описание |
|-------|----------|
| `get_token()` | Взима OAuth токен от MSAL кеш |
| `get_folder_items(path)` | Листва съдържание на OneDrive папка по път |
| `_collect_spec_files(path, extra_exts)` | Рекурсивно събира файлове по разширение |
| `_get_sharing_link(item_id)` | Генерира anonymous/organization sharing link (с кеш) |
| `check_project(path, name, location)` | Пълна проверка на един проект |
| `scan_location(path, name, parent)` | Рекурсивно сканира папки за проекти |
| `run()` | Основна точка на влизане — сканира година/град |
| `_save_report(year, city)` | Записва `cache_{year}_{city}.json` |

**Структура на проектен рапорт:**
```python
{
    "name":             str,
    "location":         str,
    "full_path":        str,   # използва се като уникален ID
    "status":           str,   # "Актуален" | "Има проблеми" | "Няма работен pln файл" | ...
    "pln_name":         str,
    "pln_date_str":     str,
    "delivered_count":  int,
    "delivered_files":  [{"name", "date", "item_id", "web_url"}],
    "outdated_arch":    [str],
    "specialties":      {folder_name: {files_count, latest_file, latest_date}},
    "specialties_rows": [{"label", "folder_name", "status", "files_count", "latest_date"}],
    "issues":           [str],
    "stanovishta": {
        "visa_status":       "found" | "missing",
        "skica_status":      "found" | "missing",
        "visa_files":        [{"name", "date"}],
        "skica_files":       [{"name", "date"}],
        "stanovishte_files": [{"name", "date"}],
        "other_files":       [{"name", "date"}],
    },
    "podlozhki_files":  [{"name", "date", "item_id", "web_url"}],  # последните 10 по дата
}
```

**Очаквана структура на папките в OneDrive:**
```
РАБОТНИ_облак/
└── {ГОДИНА}/
    └── {ГРАД}/
        └── {ПРОЕКТ}/
            ├── CAD/
            │   └── АРХИТЕКТУРА/
            │       ├── РАБОТНИ/
            │       │   ├── *.pln              # ArchiCAD файлове
            │       │   └── ПОДЛОЖКИ/          # DWG подложки (рекурсивно, топ 10)
            │       └── ПРЕДАДЕНИ/             # Предадени файлове (рекурсивно)
            ├── CAD/специалности/
            │   ├── ВиК/
            │   ├── ЕЛ/  (или ЛЪЧО/)
            │   ├── ОВК/ (или ЮЛИЯ/)
            │   └── ...
            └── ДОКУМЕНТИ/
                └── СТАНОВИЩА И ВИЗА/
```

**Филтри при сканиране:**
- Папки съдържащи `ПУП` или `PUP` в името се пропускат
- Проекти без `.dwg` файлове в ПОДЛОЖКИ (рекурсивно) се пропускат

**KNOWN_SPECIALTIES** — речник на познатите специалности и техните алиаси по проектант:

| Ключ (папка) | Етикет | Проектант |
|---|---|---|
| ВиК | ВиК | — |
| ГЕОДЕЗИЯ | Геодезия | — |
| ЕЕ | Енергийна ефект. | — |
| ЕЛ | Електро | — |
| КОНСТРУКЦИИ | Конструкции | — |
| КС | КС | — |
| ОВК | ОВК | — |
| ОЗЕЛЕНЯВАНЕ | Озеленяване | — |
| ПБ | Пожарна безопасн. | — |
| ПБЗ | ПБЗ | — |
| ПУСО | ПУСО | — |
| ЛЪЧО | Електро (Лъчо) | Лъчо → ЕЛ |
| ЮЛИЯ | ОВК (Юлия) | Юлия → ОВК |
| ВЕСКА | ВиК (Веска) | Веска → ВиК |
| ТУНЕВ | Конструкции (Тунев) | Тунев → Конструкции |
| ПЛАМЕН | Конструкции (Пламен) | Пламен → Конструкции |
| БЕГЪМОВ | Конструкции (Бегъмов) | Бегъмов → Конструкции |
| ГАНДЖОВ | Конструкции (Ганджов) | Ганджов → Конструкции |
| РУЙЧЕВА | Конструкции (Руйчева) | Руйчева → Конструкции |
| КАЛЕТИ | КС (Калети) | Калети → КС |
| ЛЮБИНА | КС (Любина) | Любина → КС |
| МАРЦЕНКОВ | ПБ (Марценков) | Марценков → ПБ |

**Класификация на документи** (`classify_doc_file`):
- `виза` — съдържа: виза, визи, viza, visa
- `скица` — съдържа: скица, skica, skitsa, sketch, скетч
- `становище` — съдържа: становище, ERM, ВиК, ЧЕЗ, EVN, мрежи и др.
- `друго` — всичко останало

---

### html_builder.py

**Функция `build_html_report(...)`** — генерира HTML карта за един проект.

Параметри:
```python
city, project_name, full_name,
pln_name, pln_date_str,
delivered_count, outdated_arch,
delivered_files,          # [{"name", "date", "item_id", "web_url"}]
specialties_rows,
specialties_detail,
project_path,
stanovishta,
podlozhki_files = None,   # последните 10 DWG от ПОДЛОЖКИ
project_id      = "",     # уникален ID (full_path)
is_hidden       = False,  # дали е скрит
missing_docs    = False,  # дали липсва виза или становище → оранжев header
```

**Визуални индикатори:**
- Оранжев header (`missing-docs`) — липсва виза или становища
- Намалена прозрачност (`hidden-card`) — скрит проект
- Бутон 👁 — скрива/показва проект (запазва се при рестарт)
- Бутон "🔗 Линк" — генерира OneDrive sharing link при клик (lazy, не при сканиране)

---

## OneDrive / Graph API

**Scopes:** `User.Read`, `Files.Read`, `Files.ReadWrite`

`Files.ReadWrite` е нужен само за `createLink` (генериране на sharing links). Програмата не изтрива и не модифицира файлове — използва само `GET` и `POST /createLink`.

**Sharing links:**
- Първо се опитва `scope: "anonymous"` (без логин)
- При отказ (business акаунт с ограничения) — `scope: "organization"` (само за потребители в tenant-а)
- Линковете се генерират lazy — само при клик от потребителя
- Кешират се в паметта за времето на сесията

---

## Стартиране

```bash
pip install -r requirements.txt
python app.py
```

Сървърът стартира на `http://0.0.0.0:5000`. При първо стартиране се отваря браузър за OAuth логин в Microsoft.

Порт може да се промени с environment variable:
```bash
PORT=8080 python app.py
```

---

## Автоматично сканиране

Scheduler-ът стартира пълно сканиране (2024, 2025, 2026) всеки ден в **08:00 (Europe/Sofia)**. Резултатите се записват в `cache_*.json` файлове и се зареждат автоматично при следващ старт на сървъра.
