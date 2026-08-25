#!/usr/bin/env python3
"""GUI desktop (Tkinter) para gerar_base.py — alternativa ao app Electron em
`app/` pra quem só tem Python instalado (sem Node/npm). Não reimplementa
nenhuma lógica de negócio: só monta os argumentos e chama
`gerar_base.main(["--file1", ..., "--file2", ..., "--output-dir", ...])`
diretamente (mesmo processo, numa thread separada pra não travar a UI) —
nada de subprocess. Isso é o que permite empacotar tudo com PyInstaller
num único .exe (ver build_exe.bat): dentro de um executável congelado,
`sys.executable` aponta pro próprio .exe, não pra um python.exe de verdade,
então rodar gerar_base.py como processo filho não funcionaria.

Uso (com Python instalado):
    python gui.py

Uso (executável standalone, sem precisar de Python na máquina):
    build_exe.bat  ->  gera dist\\NordexComparador.exe

Tkinter vem junto do instalador padrão do Python no Windows; em algumas
distros Linux é um pacote à parte (`python3-tk`).
"""

from __future__ import annotations

import contextlib
import io
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import gerar_base


def resource_path(*parts: str) -> Path:
    """Caminho de um asset (ex.: o logo), certo tanto rodando `python gui.py`
    quanto dentro de um .exe do PyInstaller (que extrai os dados pra uma
    pasta temporária apontada por sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
    return base.joinpath(*parts)


LOGO_PATH = resource_path("assets", "nordex-logo.png")

BG = "#0a0e1a"
HEADER_BG = "#0f1526"
PANEL_BG = "#111726"
PANEL_BORDER = "#232a3d"
SLOT_BG = "#0d1220"
SLOT_BORDER = "#3a4156"
TEXT_PRIMARY = "#f2f4f8"
TEXT_SECONDARY = "#9aa0b4"
TEXT_MUTED = "#6b7184"
ACCENT_BLUE = "#3b63e8"
ACCENT_BLUE_HOVER = "#4a72f5"
ACCENT_BLUE_DISABLED = "#28345f"
GREEN = "#1ea55c"
GREEN_BG = "#12241a"
RED = "#ef4444"
RED_BG = "#241212"
BTN_BG = "#1a2136"
BTN_BORDER = "#2c3450"
CONSOLE_BG = "#0b0f1a"

FONT_FAMILY = "Segoe UI"


def fmt_size(num_bytes: int) -> str:
    if not num_bytes:
        return ""
    return f"{num_bytes / (1024 * 1024):.2f} MB"


_ROW_RE = re.compile(r"^ {2}(.+?) {2,}(-?[\d.,]+\.\d{2})\s*$", re.MULTILINE)
_COUNT_RE = re.compile(r"^(.+?):\s+(\d+) linhas\s*$", re.MULTILINE)


def parse_summary(stdout_text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Extrai a tabela de valores por produto (+ Total Geral) e as contagens
    de linhas lidas, do mesmo texto que gerar_base.py já imprime em main()."""
    rows = [(m.group(1).strip(), m.group(2).strip()) for m in _ROW_RE.finditer(stdout_text)]
    counts = [(m.group(1).strip(), m.group(2).strip()) for m in _COUNT_RE.finditer(stdout_text)]
    return rows, counts


def open_path(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - user-triggered, opens their own generated file
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError as exc:
        print(f"Não foi possível abrir {path}: {exc}")


class SecondaryButton(tk.Button):
    def __init__(self, master, text="", **kw):
        super().__init__(
            master, text=text, bg=BTN_BG, fg=TEXT_PRIMARY,
            activebackground="#232b47", activeforeground=TEXT_PRIMARY,
            font=(FONT_FAMILY, 9), relief="flat", bd=0,
            highlightbackground=BTN_BORDER, highlightthickness=1,
            padx=12, pady=5, cursor="hand2", **kw,
        )


class PrimaryButton(tk.Button):
    def __init__(self, master, text="", **kw):
        super().__init__(
            master, text=text, bg=ACCENT_BLUE, fg="white",
            activebackground=ACCENT_BLUE_HOVER, activeforeground="white",
            font=(FONT_FAMILY, 9, "bold"), relief="flat", bd=0,
            padx=16, pady=9, cursor="hand2", **kw,
        )


class Slot(tk.Frame):
    """Um dos dois seletores de arquivo XLSX (equivalente ao <sc-for> do design)."""

    def __init__(self, master, label: str, on_pick):
        super().__init__(master, bg=PANEL_BG)
        self._on_pick = on_pick
        self.path: Path | None = None

        box = tk.Frame(self, bg=SLOT_BG, highlightbackground=SLOT_BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True, padx=6, pady=4)

        tk.Label(box, text=label, bg=SLOT_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10),
                 wraplength=250, justify="center").pack(pady=(12, 8), padx=14)

        icon = tk.Frame(box, bg=GREEN, width=36, height=40)
        icon.pack_propagate(False)
        icon.pack(pady=(0, 8))
        tk.Label(icon, text="X", bg=GREEN, fg="white", font=(FONT_FAMILY, 13, "bold")).pack(expand=True)

        self.name_lbl = tk.Label(box, text="Nenhum arquivo selecionado", bg=SLOT_BG, fg=TEXT_PRIMARY,
                                  font=(FONT_FAMILY, 11, "bold"), wraplength=250, justify="center")
        self.name_lbl.pack(padx=14)
        self.size_lbl = tk.Label(box, text=" ", bg=SLOT_BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 9))
        self.size_lbl.pack(pady=(2, 8))

        self.pick_btn = SecondaryButton(box, text="Selecionar arquivo", command=self._pick)
        self.pick_btn.pack(pady=(0, 12))

    def _pick(self):
        chosen = filedialog.askopenfilename(title="Selecionar arquivo XLSX", filetypes=[("Excel", "*.xlsx")])
        if not chosen:
            return
        self.set_path(Path(chosen))
        self._on_pick()

    def set_path(self, path: Path):
        self.path = path
        self.name_lbl.config(text=path.name)
        try:
            self.size_lbl.config(text=fmt_size(path.stat().st_size))
        except OSError:
            self.size_lbl.config(text=" ")
        self.pick_btn.config(text="Trocar arquivo")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nordex Comparador")
        self.geometry("1000x860")
        self.minsize(780, 640)
        self.configure(bg=BG)

        self.output_dir: Path | None = None
        self.is_running = False
        self.last_report_path: Path | None = None
        self.log_queue: "queue.Queue[tuple]" = queue.Queue()

        self._configure_style()
        self._build_header()
        self._build_body()
        self.after(80, self._poll_queue)

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Nordex.Horizontal.TProgressbar",
            troughcolor=PANEL_BG, background=ACCENT_BLUE,
            bordercolor=PANEL_BG, lightcolor=ACCENT_BLUE, darkcolor=ACCENT_BLUE,
        )
        style.configure(
            "Nordex.Vertical.TScrollbar",
            troughcolor=BG, background=BTN_BG, bordercolor=BG,
            arrowcolor=TEXT_SECONDARY, lightcolor=BTN_BG, darkcolor=BTN_BG,
        )
        style.map("Nordex.Vertical.TScrollbar", background=[("active", "#232b47")])
        style.configure(
            "Nordex.Treeview",
            background=PANEL_BG, fieldbackground=PANEL_BG, foreground=TEXT_PRIMARY,
            borderwidth=0, rowheight=24, font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Nordex.Treeview.Heading",
            background=SLOT_BG, foreground=TEXT_SECONDARY, relief="flat",
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.map("Nordex.Treeview", background=[("selected", BTN_BG)], foreground=[("selected", TEXT_PRIMARY)])
        style.map("Nordex.Treeview.Heading", background=[("active", SLOT_BG)])

    # ---------------- layout ----------------

    def _build_header(self):
        header = tk.Frame(self, bg=HEADER_BG, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        inner = tk.Frame(header, bg=HEADER_BG)
        inner.pack(side="left", padx=32, pady=12)

        if LOGO_PATH.exists():
            self._logo_img = tk.PhotoImage(file=str(LOGO_PATH))
            factor = max(1, self._logo_img.width() // 150)
            if factor > 1:
                self._logo_img = self._logo_img.subsample(factor, factor)
            tk.Label(inner, image=self._logo_img, bg=HEADER_BG).pack()
        else:
            tk.Label(inner, text="NORDEX", bg=HEADER_BG, fg="#4a90f0",
                     font=(FONT_FAMILY, 18, "bold")).pack()

        tk.Frame(self, bg=PANEL_BORDER, height=1).pack(fill="x")

    def _build_body(self):
        scroll_area = tk.Frame(self, bg=BG)
        scroll_area.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_area, bg=BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview,
                                 style="Nordex.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        outer = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=outer, anchor="nw")

        def on_outer_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(e):
            canvas.itemconfig(window_id, width=e.width)

        outer.bind("<Configure>", on_outer_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(e):
            delta = e.delta if sys.platform == "darwin" else int(e.delta / 120)
            canvas.yview_scroll(-delta, "units")

        def on_mousewheel_linux(e):
            canvas.yview_scroll(-1 if e.num == 4 else 1, "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_mousewheel_linux)
        canvas.bind_all("<Button-5>", on_mousewheel_linux)

        wrap = tk.Frame(outer, bg=BG)
        wrap.pack(fill="both", expand=True, padx=32, pady=(20, 16))

        tk.Label(wrap, text="Bem-vindo!", bg=BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 18, "bold")).pack(pady=(0, 4), anchor="w")
        tk.Label(wrap, text="Selecione os dois relatórios SAP para gerar o relatório de pagamentos.",
                 bg=BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10)).pack(pady=(0, 12), anchor="w")

        panel1 = self._panel(wrap)
        panel1.pack(fill="x", pady=(0, 12))
        tk.Label(panel1, text="1. Selecionar Arquivos XLSX", bg=PANEL_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", padx=20, pady=(12, 8))

        slots_row = tk.Frame(panel1, bg=PANEL_BG)
        slots_row.pack(fill="x", padx=14)
        self.slot1 = Slot(slots_row, "Arquivo 1 — Administrar itens de fornecedor", self._on_files_changed)
        self.slot1.pack(side="left", fill="both", expand=True)
        self.slot2 = Slot(slots_row, "Arquivo 2 — Partidas individuais no Razão", self._on_files_changed)
        self.slot2.pack(side="left", fill="both", expand=True)

        tk.Frame(panel1, bg=PANEL_BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))
        out_row = tk.Frame(panel1, bg=PANEL_BG)
        out_row.pack(fill="x", padx=20, pady=(0, 12))
        left = tk.Frame(out_row, bg=PANEL_BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Pasta de saída", bg=PANEL_BG, fg=TEXT_SECONDARY,
                 font=(FONT_FAMILY, 9)).pack(anchor="w")
        self.output_lbl = tk.Label(left, text="Nenhuma pasta selecionada", bg=PANEL_BG,
                                    fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), anchor="w")
        self.output_lbl.pack(anchor="w")
        SecondaryButton(out_row, text="Selecionar pasta", command=self._pick_output).pack(side="right")

        self.run_btn = tk.Frame(wrap, bg=ACCENT_BLUE_DISABLED)
        self.run_btn.pack(fill="x", pady=(0, 12))
        self.run_label = tk.Label(self.run_btn, text="▶  Executar Análise", bg=ACCENT_BLUE_DISABLED,
                                   fg="white", font=(FONT_FAMILY, 12, "bold"))
        self.run_label.pack(pady=(10, 0))
        self.run_sub = tk.Label(self.run_btn, text="Selecione os dois arquivos e a pasta de saída",
                                 bg=ACCENT_BLUE_DISABLED, fg="#c7cffb", font=(FONT_FAMILY, 9))
        self.run_sub.pack(pady=(0, 10))
        self._run_widgets = (self.run_btn, self.run_label, self.run_sub)

        self.progress = ttk.Progressbar(wrap, mode="indeterminate", style="Nordex.Horizontal.TProgressbar")

        self.console_panel = self._panel(wrap)
        tk.Label(self.console_panel, text="Console", bg=PANEL_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", padx=20, pady=(16, 10))
        console_wrap = tk.Frame(self.console_panel, bg=PANEL_BG)
        console_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.console = tk.Text(console_wrap, height=12, bg=CONSOLE_BG, fg="#c7cbe0",
                                insertbackground="#c7cbe0", font=("Consolas", 9),
                                relief="flat", wrap="word", state="disabled")
        self.console.tag_config("stderr", foreground="#f5a3a3")
        self.console.pack(fill="both", expand=True)

        self.success_panel = self._panel(wrap)
        self._build_success_panel()

        self.error_panel = self._panel(wrap)
        self._build_error_panel()

        self._set_run_enabled(False)

    def _panel(self, master):
        return tk.Frame(master, bg=PANEL_BG, highlightbackground=PANEL_BORDER, highlightthickness=1)

    def _build_success_panel(self):
        tk.Label(self.success_panel, text="2. Relatório Gerado", bg=PANEL_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=20, pady=(18, 12))

        self.summary_frame = tk.Frame(self.success_panel, bg=PANEL_BG)
        self.summary_counts_lbl = tk.Label(self.summary_frame, text="", bg=PANEL_BG, fg=TEXT_SECONDARY,
                                            font=(FONT_FAMILY, 9), anchor="w", justify="left")
        self.summary_counts_lbl.pack(anchor="w", pady=(0, 8))
        self.summary_tree = ttk.Treeview(self.summary_frame, columns=("produto", "valor"), show="headings",
                                          height=5, style="Nordex.Treeview")
        self.summary_tree.heading("produto", text="Produto", anchor="w")
        self.summary_tree.heading("valor", text="Valor (BRL)", anchor="e")
        self.summary_tree.column("produto", anchor="w", width=240, stretch=True)
        self.summary_tree.column("valor", anchor="e", width=160, stretch=False)
        self.summary_tree.tag_configure("total", font=(FONT_FAMILY, 9, "bold"))
        self.summary_tree.pack(fill="x")
        self.summary_frame.pack(fill="x", padx=20, pady=(0, 4))

        row = tk.Frame(self.success_panel, bg=GREEN_BG, highlightbackground=GREEN, highlightthickness=1)
        row.pack(fill="x", padx=20, pady=(0, 20))
        inner = tk.Frame(row, bg=GREEN_BG)
        inner.pack(fill="x", padx=16, pady=14)
        inner.grid_columnconfigure(1, weight=1)

        icon = tk.Frame(inner, bg=GREEN, width=36, height=36)
        icon.pack_propagate(False)
        icon.grid(row=0, column=0, sticky="n")
        tk.Label(icon, text="✓", bg=GREEN, fg="white", font=(FONT_FAMILY, 13, "bold")).pack(expand=True)

        info = tk.Frame(inner, bg=GREEN_BG)
        info.grid(row=0, column=1, sticky="w", padx=14)
        tk.Label(info, text="Relatório gerado com sucesso!", bg=GREEN_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w")
        self.success_filename = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_filename.pack(anchor="w")
        self.success_path = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_path.pack(anchor="w")
        self.success_size = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_size.pack(anchor="w")

        actions = tk.Frame(inner, bg=GREEN_BG)
        actions.grid(row=0, column=2, sticky="e", padx=(14, 0))
        SecondaryButton(actions, text="Abrir Relatório", command=self._open_file).pack(side="left", padx=(0, 8))
        PrimaryButton(actions, text="Abrir Pasta do Relatório", command=self._open_folder).pack(side="left")

    def _build_error_panel(self):
        tk.Label(self.error_panel, text="Falha ao gerar relatório", bg=PANEL_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=20, pady=(18, 12))
        row = tk.Frame(self.error_panel, bg=RED_BG, highlightbackground=RED, highlightthickness=1)
        row.pack(fill="x", padx=20, pady=(0, 20))
        inner = tk.Frame(row, bg=RED_BG)
        inner.pack(fill="x", padx=16, pady=14)

        icon = tk.Frame(inner, bg=RED, width=36, height=36)
        icon.pack_propagate(False)
        icon.pack(side="left", anchor="n")
        tk.Label(icon, text="✕", bg=RED, fg="white", font=(FONT_FAMILY, 13, "bold")).pack(expand=True)

        info = tk.Frame(inner, bg=RED_BG)
        info.pack(side="left", fill="both", expand=True, padx=14)
        tk.Label(info, text="Não foi possível gerar o relatório", bg=RED_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w")
        self.error_msg = tk.Text(info, height=6, bg=RED_BG, fg="#f5b3b3", font=("Consolas", 9),
                                  relief="flat", wrap="word", bd=0, state="disabled")
        self.error_msg.pack(fill="both", expand=True, pady=(6, 0))

    # ---------------- state ----------------

    def _on_files_changed(self):
        self._hide_reports()
        self._update_run_state()

    def _pick_output(self):
        chosen = filedialog.askdirectory(title="Selecionar pasta de saída")
        if not chosen:
            return
        self.output_dir = Path(chosen)
        self.output_lbl.config(text=chosen)
        self._update_run_state()

    def _can_run(self) -> bool:
        return bool(self.slot1.path and self.slot2.path and self.output_dir) and not self.is_running

    def _update_run_state(self):
        self._set_run_enabled(self._can_run())
        if self.is_running:
            return
        if not (self.slot1.path and self.slot2.path):
            self.run_sub.config(text="Selecione os dois arquivos e a pasta de saída")
        elif not self.output_dir:
            self.run_sub.config(text="Selecione a pasta de saída")
        else:
            self.run_sub.config(text="Processar arquivos e gerar relatório")

    def _set_run_enabled(self, enabled: bool):
        color = ACCENT_BLUE if enabled else ACCENT_BLUE_DISABLED
        for w in self._run_widgets:
            w.config(bg=color, cursor="hand2" if enabled else "arrow")
            w.unbind("<Button-1>")
            if enabled:
                w.bind("<Button-1>", lambda _e: self._start_run())

    def _hide_reports(self):
        self.success_panel.pack_forget()
        self.error_panel.pack_forget()

    # ---------------- run ----------------

    def _start_run(self):
        if not self._can_run():
            return
        self.is_running = True
        self._hide_reports()
        self._set_run_enabled(False)
        self.run_label.config(text="⏳  Processando...")
        self.run_sub.config(text="Aguarde enquanto os arquivos são processados")

        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

        self.console_panel.pack_forget()
        self.progress.pack(fill="x", pady=(0, 16))
        self.progress.start(12)

        argv = [
            "--file1", str(self.slot1.path),
            "--file2", str(self.slot2.path),
            "--output-dir", str(self.output_dir),
        ]
        threading.Thread(target=self._run_analysis, args=(argv,), daemon=True).start()

    def _run_analysis(self, argv: list[str]):
        """Chama gerar_base.main(argv) direto (mesmo processo) numa thread
        separada — sem subprocess. stdout é capturado linha a linha e
        também repassado ao console em tempo real via log_queue."""

        class _QueueWriter(io.TextIOBase):
            def __init__(self, q: "queue.Queue[tuple]"):
                self._q = q
                self.parts: list[str] = []

            def write(self, s: str) -> int:
                if s:
                    self.parts.append(s)
                    self._q.put(("log", "stdout", s))
                return len(s)

        writer = _QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer):
                code = gerar_base.main(argv)
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines(keepends=True):
                self.log_queue.put(("log", "stderr", line))
            self.log_queue.put(("error", tb.strip()))
            return

        stdout_text = "".join(writer.parts)
        if code == 0:
            report_path = None
            for line in reversed(stdout_text.splitlines()):
                if line.startswith("Arquivo:"):
                    report_path = line.split("Arquivo:", 1)[1].strip()
                    break
            if report_path and Path(report_path).exists():
                rows, counts = parse_summary(stdout_text)
                self.log_queue.put(("done", report_path, rows, counts))
            else:
                self.log_queue.put((
                    "error",
                    "O script terminou sem erro, mas não foi possível localizar o arquivo gerado.",
                ))
        else:
            self.log_queue.put(("error", f"gerar_base.py terminou com código {code}."))

    def _poll_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, tag, text = item
                    self.console.config(state="normal")
                    self.console.insert("end", text, ("stderr",) if tag == "stderr" else ())
                    self.console.see("end")
                    self.console.config(state="disabled")
                elif kind == "done":
                    _, report_path, rows, counts = item
                    self._on_done(report_path, rows, counts)
                elif kind == "error":
                    self._on_error(item[1])
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _on_done(self, report_path: str, rows: list[tuple[str, str]], counts: list[tuple[str, str]]):
        self.is_running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.console_panel.pack_forget()
        self.run_label.config(text="▶  Executar Análise")
        self._update_run_state()

        self.summary_tree.delete(*self.summary_tree.get_children())
        for label, value in rows:
            tags = ("total",) if label == "Total Geral" else ()
            self.summary_tree.insert("", "end", values=(label, value), tags=tags)
        self.summary_counts_lbl.config(text="   ".join(f"{label}: {value} linhas" for label, value in counts))
        if rows:
            self.summary_frame.pack(fill="x", padx=20, pady=(0, 4))
        else:
            self.summary_frame.pack_forget()

        p = Path(report_path)
        self.last_report_path = p
        self.success_filename.config(text=f"Arquivo: {p.name}")
        self.success_path.config(text=f"Pasta: {p.parent}")
        try:
            self.success_size.config(text=f"Tamanho: {fmt_size(p.stat().st_size)}")
        except OSError:
            self.success_size.config(text="")
        self.error_panel.pack_forget()
        self.success_panel.pack(fill="x", pady=(0, 16))

    def _on_error(self, message: str):
        self.is_running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.run_label.config(text="▶  Executar Análise")
        self._update_run_state()

        self.error_msg.config(state="normal")
        self.error_msg.delete("1.0", "end")
        self.error_msg.insert("1.0", message)
        self.error_msg.config(state="disabled")
        self.success_panel.pack_forget()
        self.error_panel.pack(fill="x", pady=(0, 16))
        self.console_panel.pack(fill="both", expand=True, pady=(0, 16))

    # ---------------- shell actions ----------------

    def _open_file(self):
        if self.last_report_path:
            open_path(self.last_report_path)

    def _open_folder(self):
        if self.last_report_path:
            open_path(self.last_report_path.parent)


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
