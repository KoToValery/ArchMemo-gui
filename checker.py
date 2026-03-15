#!/usr/bin/env python3
"""
Project Delivery Checker — логика (без CLI, без имейл по подразбиране)
"""

import os
import sys
import json
import msal
import requests
import smtplib
import ssl
import time
import logging
from datetime import datetime, timezone
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, '/home/koto/onedrive-env/lib/python3.14/site-packages')

# ─── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID  = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY  = "https://login.microsoftonline.com/common"
SCOPES     = ["User.Read", "Files.Read", "Files.ReadWrite"]
CACHE_FILE = os.path.expanduser("~/.onedrive_business_token_cache.json")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

OUTPUT_DIR = "/home/koto/.openclaw/workspace/memory"
LOG_FILE   = os.path.join(OUTPUT_DIR, "project_checker.log")

REQUEST_DELAY = 0.5
MAX_RETRIES   = 3
RETRY_DELAY   = 2.0

NOTIFY_EMAIL  = "kostadintosev@gmail.com"
CLOUD_ROOT    = "РАБОТНИ_облак"

KNOWN_SPECIALTIES = {
    # Папки по специалност
    "ВиК":           {"label": "ВиК",             "extra_exts": ()},
    "ГЕОДЕЗИЯ":      {"label": "Геодезия",         "extra_exts": ()},
    "ЕЕ":            {"label": "Енергийна ефект.", "extra_exts": (".doc", ".docx", ".xls", ".xlsx")},
    "ЕЛ":            {"label": "Електро",          "extra_exts": ()},
    "КОНСТРУКЦИИ":   {"label": "Конструкции",      "extra_exts": ()},
    "КС":            {"label": "КС",               "extra_exts": (".doc", ".docx", ".xls", ".xlsx")},
    "ОВК":           {"label": "ОВК",              "extra_exts": ()},
    "ОЗЕЛЕНЯВАНЕ":   {"label": "Озеленяване",      "extra_exts": (".doc", ".docx")},
    "ПБ":            {"label": "Пожарна безопасн.","extra_exts": (".doc", ".docx")},
    "ПБЗ":           {"label": "ПБЗ",              "extra_exts": (".doc", ".docx")},
    "ПУСО":          {"label": "ПУСО",             "extra_exts": (".doc", ".docx", ".xls", ".xlsx")},
    # Папки по проектант (алиас → специалност)
    "ЛЪЧО":          {"label": "Електро (Лъчо)",   "extra_exts": ()},
    "ЮЛИЯ":          {"label": "ОВК (Юлия)",       "extra_exts": ()},
    "ВЕСКА":         {"label": "ВиК (Веска)",      "extra_exts": ()},
    "ТУНЕВ":         {"label": "Конструкции (Тунев)",   "extra_exts": ()},
    "ПЛАМЕН":        {"label": "Конструкции (Пламен)",  "extra_exts": ()},
    "БЕГЪМОВ":       {"label": "Конструкции (Бегъмов)", "extra_exts": ()},
    "ГАНДЖОВ":       {"label": "Конструкции (Ганджов)", "extra_exts": ()},
    "РУЙЧЕВА":       {"label": "Конструкции (Руйчева)", "extra_exts": ()},
    "КАЛЕТИ":        {"label": "КС (Калети)",      "extra_exts": (".doc", ".docx", ".xls", ".xlsx")},
    "ЛЮБИНА":        {"label": "КС (Любина)",      "extra_exts": (".doc", ".docx", ".xls", ".xlsx")},
    "МАРЦЕНКОВ":     {"label": "ПБ (Марценков)",   "extra_exts": (".doc", ".docx")},
}
BASE_EXTS = (".dwg", ".jpg", ".pdf")

_VISA_KEYWORDS    = ("виза", "визи", "viza", "visa")
_SKICA_KEYWORDS   = ("скица", "skica", "skitsa", "sketch", "скетч")
_STANOVISHTE_KEYWORDS = (
    "становище", "stanovishte", "становища", "ERM", "zapad", "vik",
    "чез", "енерго", "energo", "izhodni", "evn", "evi", "еви", "ел.разпр", "ел разпр",
    "вик", "vik", "ЕРМ", "мрежи", "Запад", "stanoviste",
    "напоителни", "ЧЕЗ",
)


def classify_doc_file(name: str) -> str:
    n = name.lower()
    if any(k in n for k in _VISA_KEYWORDS):
        return "виза"
    if any(k in n for k in _SKICA_KEYWORDS):
        return "скица"
    if any(k in n for k in _STANOVISHTE_KEYWORDS):
        return "становище"
    return "друго"


os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ProjectChecker")


class ProjectChecker:

    def __init__(self, year: str, city: str | None = None, send_email: bool = False):
        self.year            = year
        self.city            = city.upper() if city else None
        self.send_email_flag = send_email
        self.token           = None
        self.headers         = None
        self.last_request_ts    = 0.0
        self._sharing_link_cache = {}
        self.smtp_password   = None
        self._load_smtp_password()
        self.report = {
            "check_date":        datetime.now().isoformat(),
            "year":              year,
            "city":              self.city or "ALL",
            "projects":          [],
            "skipped_locations": [],
            "errors":            [],
        }

    def _load_smtp_password(self):
        creds_file = "/home/koto/.openclaw/workspace/.secure/credentials.ini"
        try:
            if not os.path.exists(creds_file):
                return
            with open(creds_file, encoding="utf-8") as f:
                content = f.read()
            in_section = False
            for line in content.splitlines():
                line = line.strip()
                if "[webmail.pirindesign.com]" in line:
                    in_section = True
                elif line.startswith("[") and "]" in line:
                    in_section = False
                elif in_section and line.startswith("password:"):
                    self.smtp_password = line.split(":", 1)[1].strip()
                    return
        except Exception as exc:
            log.error("Грешка при четене на credentials: %s", exc)

    def get_token(self) -> bool:
        try:
            cache = msal.SerializableTokenCache()
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, encoding="utf-8") as f:
                    cache.deserialize(f.read())
            app      = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
            accounts = app.get_accounts()
            if not accounts:
                log.error("Няма запазени акаунти в token cache.")
                return False
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self.token   = result["access_token"]
                self.headers = {
                    "Authorization": f'Bearer {result["access_token"]}',
                    "Content-Type":  "application/json",
                }
                return True
            log.error("Не може да се придобие token: %s", result.get("error_description", "—"))
            return False
        except Exception as exc:
            log.exception("Изключение при придобиване на token: %s", exc)
            return False

    def _get(self, url: str, timeout: int = 30) -> requests.Response | None:
        elapsed = time.time() - self.last_request_ts
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=timeout)
                self.last_request_ts = time.time()
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", RETRY_DELAY * attempt))
                    time.sleep(wait)
                    continue
                return resp
            except requests.Timeout:
                time.sleep(RETRY_DELAY * attempt)
            except requests.ConnectionError as exc:
                time.sleep(RETRY_DELAY * attempt)
            except Exception as exc:
                log.error("Грешка при GET %s: %s", url, exc)
                return None
        return None

    def _post(self, url: str, body: dict, timeout: int = 30) -> requests.Response | None:
        elapsed = time.time() - self.last_request_ts
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        try:
            resp = requests.post(url, headers={**self.headers, "Content-Type": "application/json"},
                                 json=body, timeout=timeout)
            self.last_request_ts = time.time()
            return resp
        except Exception as exc:
            log.error("Грешка при POST %s: %s", url, exc)
            return None

    def _get_sharing_link(self, item_id: str) -> str:
        """Връща anonymous view link за файл. Кешира резултата."""
        if item_id in self._sharing_link_cache:
            return self._sharing_link_cache[item_id]
        url  = f"{GRAPH_BASE}/me/drive/items/{item_id}/createLink"
        resp = self._post(url, {"type": "view", "scope": "anonymous"})
        if resp is not None and resp.status_code in (200, 201):
            link = resp.json().get("link", {}).get("webUrl", "")
            self._sharing_link_cache[item_id] = link
            return link
        # Fallback: organization scope (за business акаунти с забранени anonymous links)
        resp = self._post(url, {"type": "view", "scope": "organization"})
        if resp is not None and resp.status_code in (200, 201):
            link = resp.json().get("link", {}).get("webUrl", "")
            self._sharing_link_cache[item_id] = link
            return link
        log.warning("Не може да се генерира sharing link за item %s", item_id)
        self._sharing_link_cache[item_id] = ""
        return ""

    def get_folder_items(self, path: str) -> list[dict]:
        encoded = quote(path, safe="/")
        url     = f"{GRAPH_BASE}/me/drive/root:/{encoded}:/children"
        resp    = self._get(url)
        if resp is None:
            return []
        if resp.status_code == 200:
            return resp.json().get("value", [])
        log.debug("get_folder_items %s → HTTP %s", path, resp.status_code)
        return []

    def has_cad_folder(self, path: str) -> bool:
        items = self.get_folder_items(path)
        return any("folder" in item and item["name"].upper() == "CAD" for item in items)

    @staticmethod
    def _item_date(item: dict) -> datetime:
        raw = item.get("lastModifiedDateTime", "2000-01-01T00:00:00Z")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime(2000, 1, 1, tzinfo=timezone.utc)

    def send_html_email(self, to: str, subject: str, html_body: str) -> bool:
        if not self.smtp_password:
            log.error("SMTP паролата не е налична.")
            return False
        try:
            msg            = MIMEMultipart("alternative")
            msg["From"]    = "office@pirindesign.com"
            msg["To"]      = to
            msg["Subject"] = subject
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            ctx               = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode   = ssl.CERT_NONE
            with smtplib.SMTP("webmail.pirindesign.com", 587, timeout=30) as srv:
                srv.starttls(context=ctx)
                srv.login("office@pirindesign.com", self.smtp_password)
                srv.send_message(msg)
            log.info("📧 Имейл изпратен: %s", subject[:60])
            return True
        except Exception as exc:
            log.error("Грешка при изпращане на имейл: %s", exc)
            return False

    def _collect_spec_files(self, spec_path: str, extra_exts: tuple) -> list[dict]:
        exts  = BASE_EXTS + extra_exts
        files = []
        items = self.get_folder_items(spec_path)
        for item in items:
            name = item.get("name", "")
            if "folder" in item:
                files += self._collect_spec_files(f"{spec_path}/{name}", extra_exts)
            elif name.lower().endswith(exts):
                files.append(item)
        return files

    def check_project(self, project_path: str, project_name: str, location: str = "") -> dict:
        full_name = f"{project_name} ({location})" if location else project_name
        log.info("── Проект: %s", full_name)

        project_report = {
            "name":            project_name,
            "location":        location,
            "full_path":       project_path,
            "status":          "",
            "last_pln_date":   None,
            "pln_name":        None,
            "pln_date_str":    None,
            "delivered_count": 0,
            "delivered_files": [],
            "outdated_arch":   [],
            "specialties":     {},
            "specialties_rows": [],
            "issues":          [],
            "stanovishta":     {},
            "podlozhki_files": [],
        }

        rabotni_items = self.get_folder_items(f"{project_path}/CAD/АРХИТЕКТУРА/РАБОТНИ")
        pln_files     = [i for i in rabotni_items if i.get("name", "").lower().endswith(".pln")]
        if not pln_files:
            project_report["status"] = "Няма работен pln файл"
            return project_report

        latest_pln   = max(pln_files, key=self._item_date)
        pln_date     = self._item_date(latest_pln)
        pln_date_str = pln_date.strftime("%d.%m.%Y")
        project_report["last_pln_date"] = pln_date.isoformat()
        project_report["pln_name"]      = latest_pln["name"]
        project_report["pln_date_str"]  = pln_date_str

        # ПОДЛОЖКИ — dwg файлове рекурсивно, последните 10 по дата
        podlozhki_root = f"{project_path}/CAD/АРХИТЕКТУРА/РАБОТНИ/ПОДЛОЖКИ"
        podlozhki_raw  = self._collect_spec_files(podlozhki_root, ())
        podlozhki_dwg  = sorted(
            [i for i in podlozhki_raw if i.get("name", "").lower().endswith(".dwg")],
            key=self._item_date, reverse=True
        )
        project_report["podlozhki_files"] = [
            {"name": i["name"], "date": self._item_date(i).isoformat(),
             "item_id": i.get("id", ""), "web_url": ""}
            for i in podlozhki_dwg[:10]
        ]

        # ПРЕДАДЕНИ — рекурсивно в всички подпапки
        predadeni_path  = f"{project_path}/CAD/АРХИТЕКТУРА/ПРЕДАДЕНИ"
        predadeni_raw   = self._collect_spec_files(predadeni_path, ())
        delivered_files = [i for i in predadeni_raw
                           if i.get("name", "").lower().endswith((".dwg", ".pdf"))]
        if not delivered_files:
            project_report["status"] = "Няма файлове в Предадени"
            return project_report

        project_report["delivered_count"] = len(delivered_files)

        outdated_arch = []
        for item in delivered_files:
            fd      = self._item_date(item)
            name    = item["name"]
            item_id = item.get("id", "")
            project_report["delivered_files"].append({
                "name":    name,
                "date":    fd.isoformat(),
                "item_id": item_id,
                "web_url": "",
            })
            if fd < pln_date:
                outdated_arch.append(f"{name} ({fd.strftime('%d.%m.%Y')})")
        project_report["outdated_arch"] = outdated_arch
        if outdated_arch:
            project_report["issues"].append(f"Архитектура: {len(outdated_arch)} остарели файла")

        specs_path   = f"{project_path}/CAD/специалности"
        specs_items  = self.get_folder_items(specs_path)
        spec_folders = {item["name"]: item for item in specs_items if "folder" in item}

        specialties_rows = []
        has_issues       = bool(outdated_arch)

        for folder_name in spec_folders:
            spec_path = f"{specs_path}/{folder_name}"
            key_upper = folder_name.upper()
            known_key = next((k for k in KNOWN_SPECIALTIES if k.upper() == key_upper), None)
            cfg       = KNOWN_SPECIALTIES.get(known_key, {"label": folder_name, "extra_exts": ()})
            spec_files = self._collect_spec_files(spec_path, cfg["extra_exts"])

            if not spec_files:
                specialties_rows.append({"label": cfg["label"], "folder_name": folder_name,
                                         "status": "missing", "files_count": 0, "latest_date": "—"})
                project_report["specialties"][folder_name] = "Няма файлове"
                has_issues = True
                continue

            latest_spec = max(spec_files, key=self._item_date)
            latest_date = self._item_date(latest_spec)
            date_str    = latest_date.strftime("%d.%m.%Y")
            project_report["specialties"][folder_name] = {
                "files_count": len(spec_files),
                "latest_file": latest_spec["name"],
                "latest_date": latest_date.isoformat(),
            }
            if latest_date < pln_date:
                specialties_rows.append({"label": cfg["label"], "folder_name": folder_name,
                                         "status": "outdated",
                                         "files_count": len(spec_files), "latest_date": date_str})
                has_issues = True
            else:
                specialties_rows.append({"label": cfg["label"], "folder_name": folder_name,
                                         "status": "ok",
                                         "files_count": len(spec_files), "latest_date": date_str})

        project_report["specialties_rows"] = specialties_rows

        doc_path  = f"{project_path}/ДОКУМЕНТИ/СТАНОВИЩА И ВИЗА"
        doc_items = self.get_folder_items(doc_path)
        doc_files = [i for i in doc_items if "folder" not in i]

        visa_files = []; skica_files = []; stanovishte_files = []; other_files = []
        for item in doc_files:
            fname = item.get("name", "")
            ftype = classify_doc_file(fname)
            fdate = self._item_date(item).strftime("%d.%m.%Y")
            entry = {"name": fname, "date": fdate}
            if ftype == "виза":       visa_files.append(entry)
            elif ftype == "скица":    skica_files.append(entry)
            elif ftype == "становище": stanovishte_files.append(entry)
            else:                     other_files.append(entry)

        project_report["stanovishta"] = {
            "visa_status":        "found" if visa_files else "missing",
            "skica_status":       "found" if skica_files else "missing",
            "visa_files":         visa_files,
            "skica_files":        skica_files,
            "stanovishte_files":  stanovishte_files,
            "other_files":        other_files,
        }

        if has_issues:
            project_report["status"] = "Има проблеми"
            if self.send_email_flag:
                from html_builder import build_html_report
                html_body = build_html_report(
                    city               = f"{self.year} / {self.city or location}",
                    project_name       = project_name,
                    full_name          = full_name,
                    pln_name           = latest_pln["name"],
                    pln_date_str       = pln_date_str,
                    delivered_count    = len(delivered_files),
                    outdated_arch      = outdated_arch,
                    delivered_files    = project_report["delivered_files"],
                    specialties_rows   = specialties_rows,
                    specialties_detail = project_report["specialties"],
                    project_path       = project_path,
                    stanovishta        = project_report["stanovishta"],
                    podlozhki_files    = project_report["podlozhki_files"],
                )
                subject = f"[{self.year}/{self.city or location}] {full_name} — проверка"
                self.send_html_email(NOTIFY_EMAIL, subject, html_body)
        else:
            project_report["status"] = "Актуален"

        return project_report

    def scan_location(self, location_path: str, location_name: str, parent: str = ""):
        # 1. Пропусни ако името съдържа ПУП или PUP
        if "ПУП" in location_name.upper() or "PUP" in location_name.upper():
            log.info("⏭ Пропускам ПУП папка: %s", location_name)
            return

        if self.has_cad_folder(location_path):
            # 2. Пропусни ако няма файлове и в двете папки (ПОДЛОЖКИ и ПРЕДАДЕНИ)
            podlozhki_root = f"{location_path}/CAD/АРХИТЕКТУРА/РАБОТНИ/ПОДЛОЖКИ"
            predadeni_root = f"{location_path}/CAD/АРХИТЕКТУРА/ПРЕДАДЕНИ"
            
            # Търсим .dwg в ПОДЛОЖКИ (рекурсивно)
            podlozhki_files = self._collect_spec_files(podlozhki_root, ())
            has_podlozhki = any(i.get("name", "").lower().endswith(".dwg") for i in podlozhki_files)
            
            # Търсим .dwg/.pdf в ПРЕДАДЕНИ (рекурсивно)
            predadeni_files = self._collect_spec_files(predadeni_root, ())
            has_predadeni = any(i.get("name", "").lower().endswith(BASE_EXTS) for i in predadeni_files)
            
            if not has_podlozhki and not has_predadeni:
                log.info("⏭ Пропускам проект без файлове в ПОДЛОЖКИ и ПРЕДАДЕНИ: %s", location_name)
                self.report["skipped_locations"].append({
                    "path": location_path, 
                    "reason": "Няма файлове в ПОДЛОЖКИ и ПРЕДАДЕНИ"
                })
                return
            
            project = self.check_project(location_path, location_name, parent)
            self.report["projects"].append(project)
            return

        items      = self.get_folder_items(location_path)
        subfolders = [i for i in items if "folder" in i]
        if not subfolders:
            self.report["skipped_locations"].append({"path": location_path, "reason": "Няма CAD и подпапки"})
            return
        for sub in subfolders:
            self.scan_location(f"{location_path}/{sub['name']}", sub["name"],
                               f"{parent}/{location_name}" if parent else location_name)

    def run(self) -> dict:
        year_path = f"{CLOUD_ROOT}/{self.year}"
        if not self.get_token():
            self.report["errors"].append({"error": "Не може да се получи OneDrive token"})
            return self.report

        if self.city:
            self.scan_location(f"{year_path}/{self.city}", self.city)
            self._save_report(self.year, self.city)
        else:
            items  = self.get_folder_items(year_path)
            cities = [i for i in items if "folder" in i]
            for city_item in cities:
                # Рестартираме проектите за всеки град при пълно сканиране
                city_name = city_item['name']
                city_report = {
                    "check_date":        datetime.now().isoformat(),
                    "year":              self.year,
                    "city":              city_name.upper(),
                    "projects":          [],
                    "skipped_locations": [],
                    "errors":            [],
                }
                # Временно подменяме self.report за scan_location
                original_report = self.report
                self.report = city_report
                
                self.scan_location(f"{year_path}/{city_name}", city_name)
                
                self._save_report(self.year, city_name)
                # Връщаме оригиналния репорт (може да искаме да съберем всичко в 'ALL' също)
                original_report["projects"].extend(self.report["projects"])
                self.report = original_report

            # Записваме и общия 'ALL' файл
            self._save_report(self.year, "ALL")

        return self.report

    def _save_report(self, year: str, city: str):
        label = f"{year}_{city.lower()}"
        report_file = os.path.join(OUTPUT_DIR, f"cache_{label}.json")
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(self.report, f, ensure_ascii=False, indent=2)
            self.report["report_file"] = report_file
            log.info("💾 Записан кеш файл: %s", report_file)
        except Exception as exc:
            log.error("Грешка при запис на кеш файл %s: %s", report_file, exc)
