#!/usr/bin/env python3
"""
ArchMemo Git Helper — GUI версия
Изисква: Python 3.10+ с tkinter (вграден)
"""
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
import queue

PROJECT_DIR = "H:\My Drive\RABOTNA\PYTHON\ArchiMemo\ArchMemo-gui"

# ─── Цветова схема (тъмна, developer тема) ───────────────────────────────────
COLORS = {
    "bg":           "#0f1117",
    "bg2":          "#1a1d27",
    "bg3":          "#252836",
    "border":       "#2e3248",
    "accent":       "#5b6af0",
    "accent_hover": "#7b8af8",
    "accent_dim":   "#2d3470",
    "green":        "#3dd68c",
    "red":          "#f05b5b",
    "yellow":       "#f0c05b",
    "text":         "#e8eaf6",
    "text_dim":     "#7b80a0",
    "text_muted":   "#4a4f70",
    "log_bg":       "#0a0c12",
    "log_cmd":      "#5b6af0",
    "log_ok":       "#3dd68c",
    "log_err":      "#f05b5b",
    "log_warn":     "#f0c05b",
    "log_info":     "#7b80a0",
}

FONT_MONO  = ("JetBrains Mono", 10) if True else ("Courier", 10)
FONT_UI    = ("Segoe UI", 10)
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_SMALL = ("Segoe UI", 9)


# ─── Subprocess helper ────────────────────────────────────────────────────────

def run_cmd(cmd, cwd=PROJECT_DIR):
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        capture_output=True, text=True
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


# ─── Главен прозорец ──────────────────────────────────────────────────────────

class GitHelperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ArchMemo · Git Helper")
        self.geometry("860x640")
        self.minsize(700, 520)
        self.configure(bg=COLORS["bg"])
        self._queue = queue.Queue()

        self._setup_styles()
        self._build_ui()
        self._after_poll()

        # Автоматично зареди статус при старт
        self.after(200, self.do_status)

    # ── Styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame",       background=COLORS["bg"])
        style.configure("Card.TFrame",  background=COLORS["bg2"],
                        relief="flat", borderwidth=1)
        style.configure("TLabel",
                        background=COLORS["bg"],
                        foreground=COLORS["text"],
                        font=FONT_UI)
        style.configure("Dim.TLabel",
                        background=COLORS["bg2"],
                        foreground=COLORS["text_dim"],
                        font=FONT_SMALL)
        style.configure("Title.TLabel",
                        background=COLORS["bg"],
                        foreground=COLORS["text"],
                        font=FONT_TITLE)
        style.configure("Branch.TLabel",
                        background=COLORS["bg3"],
                        foreground=COLORS["accent_hover"],
                        font=("Segoe UI", 10, "bold"),
                        padding=(8, 3))

        # Бутони
        for name, fg, bg, hover in [
            ("Primary",  COLORS["text"],    COLORS["accent"],   COLORS["accent_hover"]),
            ("Success",  COLORS["bg"],      COLORS["green"],    "#5ef0a8"),
            ("Warning",  COLORS["bg"],      COLORS["yellow"],   "#f8d07a"),
            ("Danger",   COLORS["text"],    COLORS["bg3"],      COLORS["red"]),
            ("Neutral",  COLORS["text_dim"],COLORS["bg3"],      COLORS["bg2"]),
        ]:
            style.configure(f"{name}.TButton",
                            background=bg, foreground=fg,
                            font=("Segoe UI", 10, "bold"),
                            padding=(14, 7), relief="flat", borderwidth=0)
            style.map(f"{name}.TButton",
                      background=[("active", hover), ("pressed", hover)],
                      foreground=[("active", fg)])

        # Progressbar
        style.configure("Thin.Horizontal.TProgressbar",
                        troughcolor=COLORS["bg3"],
                        background=COLORS["accent"],
                        thickness=3)

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=COLORS["bg2"], height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⬡", bg=COLORS["bg2"],
                 fg=COLORS["accent"], font=("Segoe UI", 18)).pack(side="left", padx=(18, 6), pady=8)
        tk.Label(header, text="ArchMemo", bg=COLORS["bg2"],
                 fg=COLORS["text"], font=("Segoe UI", 14, "bold")).pack(side="left", pady=8)
        tk.Label(header, text="git helper", bg=COLORS["bg2"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 11)).pack(side="left", padx=(6, 0), pady=8)

        # Branch badge (вдясно)
        self.branch_var = tk.StringVar(value="…")
        self.branch_lbl = tk.Label(header, textvariable=self.branch_var,
                                   bg=COLORS["accent_dim"], fg=COLORS["accent_hover"],
                                   font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.branch_lbl.pack(side="right", padx=18)

        # ── Progress bar (тънка, под хедъра) ──────────────────────────────────
        self.progress = ttk.Progressbar(self, style="Thin.Horizontal.TProgressbar",
                                        mode="indeterminate", length=400)
        self.progress.pack(fill="x")

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Ляво — бутони + статус панел
        left = tk.Frame(body, bg=COLORS["bg"], width=210)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        self._build_buttons(left)
        self._build_status_panel(left)

        # Дясно — лог конзола
        right = tk.Frame(body, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)
        self._build_console(right)

    def _build_buttons(self, parent):
        tk.Label(parent, text="ОПЕРАЦИИ", bg=COLORS["bg"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))

        buttons = [
            ("📊  Статус",          "Primary", self.do_status),
            ("⬇   Pull",            "Success", self.do_pull),
            ("📤  Push",            "Primary", self.do_push),
            ("🔄  Синхронизация",   "Warning", self.do_sync),
            ("📜  Log",             "Neutral", self.do_log),
            ("🔍  Diff",            "Neutral", self.do_diff),
            ("🌿  Клонове",         "Neutral", self.do_branch),
            ("⚠   Hard Reset",     "Danger",  self.do_reset),
        ]

        for label, style, cmd in buttons:
            btn = ttk.Button(parent, text=label, style=f"{style}.TButton", command=cmd)
            btn.pack(fill="x", pady=3)

    def _build_status_panel(self, parent):
        sep = tk.Frame(parent, bg=COLORS["border"], height=1)
        sep.pack(fill="x", pady=(14, 10))

        tk.Label(parent, text="РЕПО СТАТУС", bg=COLORS["bg"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")

        def row(icon, label, var):
            f = tk.Frame(parent, bg=COLORS["bg"])
            f.pack(fill="x", pady=2)
            tk.Label(f, text=icon, bg=COLORS["bg"], fg=COLORS["text_dim"],
                     font=("Segoe UI", 9), width=2).pack(side="left")
            tk.Label(f, text=label, bg=COLORS["bg"], fg=COLORS["text_dim"],
                     font=("Segoe UI", 9)).pack(side="left")
            lbl = tk.Label(f, textvariable=var, bg=COLORS["bg"],
                           fg=COLORS["accent_hover"], font=("Segoe UI", 9, "bold"))
            lbl.pack(side="right")
            return lbl

        self.st_ahead  = tk.StringVar(value="—")
        self.st_behind = tk.StringVar(value="—")
        self.st_staged = tk.StringVar(value="—")
        self.st_dirty  = tk.StringVar(value="—")

        row("↑", "Ahead:",   self.st_ahead)
        row("↓", "Behind:",  self.st_behind)
        row("●", "Staged:",  self.st_staged)
        row("○", "Changed:", self.st_dirty)

    def _build_console(self, parent):
        hdr = tk.Frame(parent, bg=COLORS["bg2"], height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="КОНЗОЛА", bg=COLORS["bg2"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=12, pady=7)

        btn_clear = tk.Label(hdr, text="✕ изчисти", bg=COLORS["bg2"],
                             fg=COLORS["text_muted"], font=("Segoe UI", 8),
                             cursor="hand2")
        btn_clear.pack(side="right", padx=10)
        btn_clear.bind("<Button-1>", lambda e: self._clear_console())

        self.console = tk.Text(
            parent,
            bg=COLORS["log_bg"], fg=COLORS["text"],
            font=("Courier New", 10),
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["accent_dim"],
            relief="flat", borderwidth=0,
            wrap="word", state="disabled",
            padx=12, pady=10,
        )
        self.console.pack(fill="both", expand=True)

        # Тагове за оцветяване
        self.console.tag_config("cmd",   foreground=COLORS["log_cmd"], font=("Courier New", 10, "bold"))
        self.console.tag_config("ok",    foreground=COLORS["log_ok"])
        self.console.tag_config("err",   foreground=COLORS["log_err"])
        self.console.tag_config("warn",  foreground=COLORS["log_warn"])
        self.console.tag_config("info",  foreground=COLORS["log_info"])
        self.console.tag_config("plain", foreground=COLORS["text"])

        scrollbar = tk.Scrollbar(self.console, bg=COLORS["bg3"],
                                 troughcolor=COLORS["bg2"],
                                 activebackground=COLORS["accent"])
        scrollbar.pack(side="right", fill="y")
        self.console.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.console.yview)

    # ── Console helpers ───────────────────────────────────────────────────────

    def _log(self, text, tag="plain"):
        self.console.config(state="normal")
        self.console.insert("end", text + "\n", tag)
        self.console.see("end")
        self.console.config(state="disabled")

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

    def _log_section(self, title):
        self._log(f"\n{'─'*42}", "info")
        self._log(f"  {title}", "cmd")
        self._log(f"{'─'*42}", "info")

    def _busy(self, state: bool):
        if state:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ── Queue polling (thread-safe UI updates) ────────────────────────────────

    def _after_poll(self):
        try:
            while True:
                fn = self._queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(50, self._after_poll)

    def _post(self, fn):
        self._queue.put(fn)

    # ── Git операции (в отделна нишка) ────────────────────────────────────────

    def _run_in_thread(self, fn):
        self._busy(True)
        threading.Thread(target=self._thread_wrapper(fn), daemon=True).start()

    def _thread_wrapper(self, fn):
        def wrapper():
            try:
                fn()
            finally:
                self._post(lambda: self._busy(False))
                self._post(self._refresh_status_badge)
        return wrapper

    def _refresh_status_badge(self):
        """Обновява branch + статус числата тихо."""
        branch_out, _, _ = run_cmd("git rev-parse --abbrev-ref HEAD")
        self.branch_var.set(f"  {branch_out or '?'}  ")

        ahead,  _, _ = run_cmd("git rev-list @{u}..HEAD --count")
        behind, _, _ = run_cmd("git rev-list HEAD..@{u} --count")
        status, _, _ = run_cmd("git status --porcelain")

        staged  = sum(1 for l in status.splitlines() if l and l[0] != " " and l[0] != "?")
        dirty   = sum(1 for l in status.splitlines() if l and (l[1] != " " or l[:2] == "??"))

        self.st_ahead.set(ahead  or "0")
        self.st_behind.set(behind or "0")
        self.st_staged.set(str(staged))
        self.st_dirty.set(str(dirty))

    # ── Команди ───────────────────────────────────────────────────────────────

    def do_status(self):
        def task():
            self._post(lambda: self._log_section("📊 Git статус"))

            out, err_, rc = run_cmd("git status -sb")
            lines = out.splitlines() if out else []

            for line in lines:
                if line.startswith("##"):
                    self._post(lambda l=line: self._log(l, "info"))
                elif line.startswith("M") or line.startswith("A"):
                    self._post(lambda l=line: self._log(l, "ok"))
                elif line.startswith("D") or line.startswith("?"):
                    self._post(lambda l=line: self._log(l, "warn"))
                else:
                    self._post(lambda l=line: self._log(l, "plain"))

            if not lines:
                self._post(lambda: self._log("  Работната директория е чиста.", "ok"))

        self._run_in_thread(task)

    def do_pull(self):
        def task():
            self._post(lambda: self._log_section("⬇  Pull от GitHub"))

            dirty, _, _ = run_cmd("git status -s")
            stashed = False

            if dirty:
                self._post(lambda: self._log("  Откривам незапазени промени — stash-ирам...", "warn"))
                out, err_, rc = run_cmd("git stash push --include-untracked -m 'auto-stash before pull'")
                if rc != 0:
                    # Ако stash се провали — опитай pull директно (merge strategy)
                    self._post(lambda e=err_: self._log(f"  Stash не успя ({e}) — pull с merge...", "warn"))
                    stashed = False
                else:
                    stashed = True

            out, err_, rc = run_cmd("git pull origin main")
            for line in (out + err_).splitlines():
                tag = "ok" if "Already up to date" in line or "Fast-forward" in line else "plain"
                self._post(lambda l=line, t=tag: self._log(f"  {l}", t))

            if stashed:
                self._post(lambda: self._log("  Възстановявам stash...", "info"))
                out2, err2, rc2 = run_cmd("git stash pop")
                tag2 = "ok" if rc2 == 0 else "err"
                self._post(lambda o=out2, t=tag2: self._log(f"  {o}", t))

            result_tag = "ok" if rc == 0 else "err"
            result_msg = "✅ Pull завърши успешно!" if rc == 0 else "❌ Pull се провали."
            self._post(lambda m=result_msg, t=result_tag: self._log(f"\n  {m}", t))

        self._run_in_thread(task)

    def do_push(self):
        msg = simpledialog.askstring(
            "Push",
            "Commit съобщение:",
            initialvalue="Update files",
            parent=self
        )
        if msg is None:
            return

        def task():
            self._post(lambda: self._log_section("📤 Push към GitHub"))

            status_out, _, _ = run_cmd("git status -s")
            if not status_out:
                self._post(lambda: self._log("  Няма промени за качване.", "info"))
                return

            for line in status_out.splitlines():
                self._post(lambda l=line: self._log(f"  {l}", "warn"))

            run_cmd("git add .")
            out, err_, rc = run_cmd(f'git commit -m "{msg}"')
            self._post(lambda o=out: self._log(f"  {o}", "info"))

            out2, err2, rc2 = run_cmd("git push origin main")
            for line in (out2 + err2).splitlines():
                self._post(lambda l=line: self._log(f"  {l}", "plain"))

            result_tag = "ok" if rc2 == 0 else "err"
            result_msg = "✅ Качено успешно!" if rc2 == 0 else "❌ Push се провали. Провери грешките по-горе."
            self._post(lambda m=result_msg, t=result_tag: self._log(f"\n  {m}", t))

        self._run_in_thread(task)

    def do_sync(self):
        msg = simpledialog.askstring(
            "Синхронизация",
            "Commit съобщение:",
            initialvalue="Sync files",
            parent=self
        )
        if msg is None:
            return

        def task():
            self._post(lambda: self._log_section("🔄 Синхронизация (pull → push)"))

            # Pull
            self._post(lambda: self._log("  ⬇  Pull...", "info"))
            out, err_, rc = run_cmd("git pull origin main")
            for line in (out + err_).splitlines():
                self._post(lambda l=line: self._log(f"     {l}", "plain"))
            if rc != 0:
                self._post(lambda: self._log("  ❌ Pull се провали — push пропуснат.", "err"))
                return

            # Push
            self._post(lambda: self._log("  📤  Push...", "info"))
            status_out, _, _ = run_cmd("git status -s")
            if not status_out:
                self._post(lambda: self._log("  Няма нови промени за качване.", "info"))
                return

            run_cmd("git add .")
            run_cmd(f'git commit -m "{msg}"')
            out2, err2, rc2 = run_cmd("git push origin main")
            for line in (out2 + err2).splitlines():
                self._post(lambda l=line: self._log(f"     {l}", "plain"))

            result_tag = "ok" if rc2 == 0 else "err"
            result_msg = "✅ Синхронизацията завърши!" if rc2 == 0 else "❌ Push се провали."
            self._post(lambda m=result_msg, t=result_tag: self._log(f"\n  {m}", t))

        self._run_in_thread(task)

    def do_log(self):
        def task():
            self._post(lambda: self._log_section("📜 Последни 15 commit-а"))
            out, _, _ = run_cmd("git log --oneline --graph -n 15")
            for line in out.splitlines():
                self._post(lambda l=line: self._log(f"  {l}", "plain"))

        self._run_in_thread(task)

    def do_diff(self):
        def task():
            self._post(lambda: self._log_section("🔍 Diff (unstaged)"))
            out, _, _ = run_cmd("git diff --stat")
            if not out:
                self._post(lambda: self._log("  Няма unstaged промени.", "info"))
                return
            for line in out.splitlines():
                self._post(lambda l=line: self._log(f"  {l}", "plain"))

            full_out, _, _ = run_cmd("git diff")
            for line in full_out.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    self._post(lambda l=line: self._log(l, "ok"))
                elif line.startswith("-") and not line.startswith("---"):
                    self._post(lambda l=line: self._log(l, "err"))
                elif line.startswith("@@"):
                    self._post(lambda l=line: self._log(l, "cmd"))
                else:
                    self._post(lambda l=line: self._log(l, "plain"))

        self._run_in_thread(task)

    def do_branch(self):
        def task():
            self._post(lambda: self._log_section("🌿 Клонове"))
            out, _, _ = run_cmd("git branch -a")
            for line in out.splitlines():
                tag = "ok" if line.strip().startswith("*") else "plain"
                self._post(lambda l=line, t=tag: self._log(f"  {l}", t))

        self._run_in_thread(task)

    def do_reset(self):
        if not messagebox.askyesno(
            "⚠ Hard Reset",
            "Това ще изтрие ВСИЧКИ незапазени промени!\n\nСигурен ли си?",
            icon="warning"
        ):
            return

        def task():
            self._post(lambda: self._log_section("⚠  Hard Reset"))
            run_cmd("git checkout -- .")
            run_cmd("git clean -fd")
            self._post(lambda: self._log("  ✅ Работната директория е изчистена.", "ok"))

        self._run_in_thread(task)


# ─── Старт ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.path.exists(os.path.join(PROJECT_DIR, ".git")):
        import sys
        print(f"❌ Не е намерено Git репо в {PROJECT_DIR}")
        sys.exit(1)

    app = GitHelperApp()
    app.mainloop()