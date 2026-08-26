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

Visual: reskin fintech claro (branco/azul), seguindo o handoff do Claude
Design "Nordex Comparador v2". Tkinter não tem cantos arredondados nem
sombra nativos — os botões e badges que mais aparecem (CTA, botões
secundários, círculos de ícone) são desenhados num Canvas pra chegar perto
do design; os painéis grandes ficam com borda reta de 1px, que é a
aproximação estável pro resto. Nenhuma lógica de negócio mudou: mesmos
argumentos pra gerar_base.main, mesmos dados exibidos — só formatação
pt-BR nos números e novo layout.

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

# ---------------------------------------------------------------------------
# Paleta — tokens do spec "Nordex Comparador v2" (tema claro fintech)
# ---------------------------------------------------------------------------

BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#DCE4EF"
TABLE_BORDER = "#E7EDF6"
TEXT_PRIMARY = "#0B1F44"
TEXT_SECONDARY = "#5E6C84"
TEXT_MUTED = "#8190A5"

ACCENT_BLUE = "#0868E8"
ACCENT_BLUE_HOVER = "#075BCB"
ACCENT_BLUE_DISABLED = "#6BA4F1"
SOFT_BLUE_BG = "#EAF3FF"
DROPZONE_BG = "#F8FAFD"
DROPZONE_BORDER = "#9DC2F5"

GREEN = "#159447"
GREEN_BG = "#ECF9F0"
GREEN_BORDER = "#B9E3C6"
GREEN_TITLE = "#0F7A3A"

RED = "#E32636"
RED_DARK = "#B31C29"
RED_BG = "#FFF0F2"
RED_BORDER = "#F7C3C8"

KPI_BLUE_BG = "#EAF3FF"
KPI_GREEN_BG = "#E7F6EC"
KPI_PURPLE_BG = "#F0EAFE"
KPI_PURPLE_FG = "#7C4DEB"
KPI_AMBER_BG = "#FFF2D6"
KPI_AMBER_FG = "#D97706"

TOTAL_ROW_BG = "#EFF4FB"

FONT_FAMILY = "Segoe UI"


def fmt_size(num_bytes: int) -> str:
    """Mesmo critério do design (fmtBytes): KB abaixo de 1 MB, vírgula
    decimal pt-BR."""
    if not num_bytes:
        return ""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f}".replace(".", ",") + " MB"
    return f"{num_bytes / 1024:.1f}".replace(".", ",") + " KB"


def to_ptbr(raw: str) -> str:
    """Converte um número já formatado em estilo en-US ('-72,609.47', o que
    `gerar_base.py` imprime via `f'{v:,.2f}'`) pra estilo pt-BR
    ('-72.609,47'), só troca de separador — não recalcula nada."""
    s = raw.strip()
    neg = s.startswith("-")
    s = s.lstrip("-")
    s = s.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("-" if neg else "") + s


def fmt_compact_brl(raw: str) -> str:
    """Total processado em forma compacta (mesmo critério do fmtCompact do
    design: bi/mi/mil), a partir do valor já formatado por gerar_base.py."""
    try:
        v = abs(float(raw.strip().replace(",", "")))
    except ValueError:
        return "R$ " + to_ptbr(raw)
    if v >= 1e9:
        return f"R$ {v / 1e9:.2f}".replace(".", ",") + " bi"
    if v >= 1e6:
        return f"R$ {v / 1e6:.2f}".replace(".", ",") + " mi"
    if v >= 1e3:
        return f"R$ {v / 1e3:.1f}".replace(".", ",") + " mil"
    return "R$ " + to_ptbr(f"{v:.2f}")


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


# ---------------------------------------------------------------------------
# Desenho — Tkinter não tem cantos arredondados nativos; um Canvas com
# polígono suavizado (smooth=True) é a forma padrão de simular isso.
# ---------------------------------------------------------------------------

def _rounded_points(x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _icon_bars(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    for x, h in zip((-9, -3, 3, 9), (10, 16, 7, 13)):
        cv.create_line(cx + x, cy + 8, cx + x, cy + 8 - h, fill=color, width=3, capstyle="round")


def _icon_people(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    cv.create_oval(cx - 5, cy - 10, cx + 5, cy, outline=color, width=2)
    cv.create_arc(cx - 10, cy - 3, cx + 10, cy + 15, start=0, extent=180, style="arc", outline=color, width=2)


def _icon_coin(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    cv.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=color, width=2)
    cv.create_text(cx, cy + 1, text="R$", fill=color, font=(FONT_FAMILY, 8, "bold"))


def _icon_tag(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    cv.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=color, width=2)
    cv.create_text(cx, cy + 1, text="#", fill=color, font=(FONT_FAMILY, 11, "bold"))


def _icon_upload(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    cv.create_line(cx, cy + 9, cx, cy - 7, fill=color, width=2.4, capstyle="round")
    cv.create_line(cx - 6, cy - 1, cx, cy - 7, cx + 6, cy - 1, fill=color, width=2.4,
                    capstyle="round", joinstyle="round", smooth=False)
    cv.create_arc(cx - 13, cy - 4, cx + 13, cy + 14, start=190, extent=160, style="arc", outline=color, width=2.2)


def circle_badge(master: tk.Widget, size: int, bg_color: str, draw_icon) -> tk.Canvas:
    cv = tk.Canvas(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
    cv.create_oval(1, 1, size - 1, size - 1, fill=bg_color, outline=bg_color)
    draw_icon(cv, size / 2, size / 2)
    return cv


class RoundedButton(tk.Canvas):
    """Botão com cantos arredondados + hover, desenhado num Canvas (Tkinter
    não tem isso nativo). Suporta um título e, opcionalmente, uma segunda
    linha menor abaixo (usado pelo CTA principal)."""

    def __init__(
        self, master, text="", command=None, *, bg, fg, hover_bg=None,
        subtitle="", subtitle_fg="", radius=10, height=42, bold=True,
        font_size=10, disabled_bg=None, disabled_fg=None, outline="",
        **kw,
    ):
        kw.setdefault("bg", master["bg"])
        super().__init__(master, height=height, highlightthickness=0, **kw)
        self._command = command
        self._bg, self._hover_bg = bg, hover_bg or bg
        self._fg = fg
        self._text, self._subtitle = text, subtitle
        self._subtitle_fg = subtitle_fg or fg
        self._radius, self._outline = radius, outline
        self._font = (FONT_FAMILY, font_size, "bold" if bold else "normal")
        self._sub_font = (FONT_FAMILY, max(8, font_size - 1))
        self._disabled_bg = disabled_bg or bg
        self._disabled_fg = disabled_fg or fg
        self._enabled = True
        self._hovering = False

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Button-1>", self._on_click)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._redraw()

    def set_text(self, text: str | None = None, subtitle: str | None = None) -> None:
        if text is not None:
            self._text = text
        if subtitle is not None:
            self._subtitle = subtitle
        self._redraw()

    def _set_hover(self, hovering: bool) -> None:
        self._hovering = hovering
        self._redraw()

    def _on_click(self, _e) -> None:
        if self._enabled and self._command:
            self._command()

    def _redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width() or 1, self.winfo_height() or 1
        if not self._enabled:
            fill, fg = self._disabled_bg, self._disabled_fg
        elif self._hovering:
            fill, fg = self._hover_bg, self._fg
        else:
            fill, fg = self._bg, self._fg
        r = min(self._radius, h / 2, w / 2)
        self.create_polygon(_rounded_points(1, 1, w - 1, h - 1, r), smooth=True,
                             fill=fill, outline=self._outline or fill)
        if self._subtitle:
            self.create_text(w / 2, h / 2 - 9, text=self._text, fill=fg, font=self._font)
            self.create_text(w / 2, h / 2 + 10, text=self._subtitle, fill=self._subtitle_fg, font=self._sub_font)
        else:
            self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)


def primary_button(master, text, command, *, height=42, width=None, subtitle="") -> RoundedButton:
    return RoundedButton(
        master, text=text, command=command, bg=ACCENT_BLUE, fg="white",
        hover_bg=ACCENT_BLUE_HOVER, disabled_bg=ACCENT_BLUE_DISABLED, disabled_fg="white",
        subtitle=subtitle, subtitle_fg="#DCE9FD", height=height, width=width,
        radius=10, font_size=12 if subtitle else 10,
    )


def secondary_button(master, text, command, *, height=40, width=None) -> RoundedButton:
    return RoundedButton(
        master, text=text, command=command, bg=CARD_BG, fg=ACCENT_BLUE,
        hover_bg=SOFT_BLUE_BG, outline=CARD_BORDER, disabled_bg=CARD_BG, disabled_fg=TEXT_MUTED,
        height=height, width=width, radius=10, font_size=10, bold=False,
    )


def icon_button(master, command, draw_icon, *, size=44) -> tk.Canvas:
    """Botão quadrado com cantos arredondados, sem texto — só um ícone
    desenhado (`draw_icon(canvas, cx, cy, color)`). Usado pro botão de
    'selecionar pasta' ao lado do link de texto, igual ao design."""
    cv = tk.Canvas(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
    state = {"hover": False}

    def redraw(_e=None):
        cv.delete("all")
        w, h = cv.winfo_width() or size, cv.winfo_height() or size
        r = min(10, h / 2, w / 2)
        fill = SOFT_BLUE_BG if state["hover"] else CARD_BG
        cv.create_polygon(_rounded_points(1, 1, w - 1, h - 1, r), smooth=True, fill=fill, outline=ACCENT_BLUE)
        draw_icon(cv, w / 2, h / 2, ACCENT_BLUE)

    def set_hover(hovering):
        state["hover"] = hovering
        redraw()

    cv.bind("<Configure>", redraw)
    cv.bind("<Enter>", lambda _e: (set_hover(True), cv.configure(cursor="hand2")))
    cv.bind("<Leave>", lambda _e: set_hover(False))
    cv.bind("<Button-1>", lambda _e: command())
    return cv


def _icon_folder(cv: tk.Canvas, cx: float, cy: float, color: str) -> None:
    cv.create_line(cx - 8, cy - 3, cx - 8, cy + 6, cx + 8, cy + 6, cx + 8, cy - 2,
                    fill=color, width=1.8, joinstyle="round", capstyle="round")
    cv.create_line(cx - 8, cy - 3, cx - 3, cy - 3, cx - 1, cy - 6, cx + 3, cy - 6, cx + 5, cy - 3, cx + 8, cy - 3,
                    fill=color, width=1.8, joinstyle="round", capstyle="round")


# ---------------------------------------------------------------------------
# Slot — um dos dois seletores de arquivo XLSX (cards "1." e "2." do design)
# ---------------------------------------------------------------------------

class Slot(tk.Frame):
    def __init__(self, master, number: str, title: str, hint: str, on_pick):
        super().__init__(master, bg=BG)
        self._on_pick = on_pick
        self.path: Path | None = None

        card = tk.Frame(self, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=20, pady=18)

        tk.Label(inner, text=f"{number} {title}", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w")
        tk.Label(inner, text=hint, bg=CARD_BG, fg=TEXT_MUTED,
                 font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(1, 12))

        self.zone = tk.Frame(inner, bg=DROPZONE_BG, highlightbackground=DROPZONE_BORDER, highlightthickness=1)
        self.zone.pack(fill="both", expand=True)
        self._build_empty()

    # -- estados --

    def _clear_zone(self) -> None:
        for w in self.zone.winfo_children():
            w.destroy()

    def _bind_click(self, *widgets: tk.Widget) -> None:
        for w in widgets:
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda _e: self._pick())

    def _build_empty(self) -> None:
        self._clear_zone()
        wrap = tk.Frame(self.zone, bg=DROPZONE_BG)
        wrap.pack(expand=True, fill="both", pady=22)
        icon = circle_badge(wrap, 46, DROPZONE_BG, lambda cv, cx, cy: _icon_upload(cv, cx, cy, ACCENT_BLUE))
        icon.pack()
        title = tk.Label(wrap, text="Clique para selecionar o arquivo", bg=DROPZONE_BG, fg=TEXT_PRIMARY,
                          font=(FONT_FAMILY, 10, "bold"))
        title.pack(pady=(10, 2))
        chip = tk.Label(wrap, text="XLSX", bg=SOFT_BLUE_BG, fg=TEXT_SECONDARY,
                         font=(FONT_FAMILY, 8, "bold"), padx=10, pady=3)
        chip.pack(pady=(6, 0))
        self._bind_click(self.zone, wrap, icon, title, chip)

    def _build_selected(self, path: Path) -> None:
        self._clear_zone()
        row = tk.Frame(self.zone, bg=DROPZONE_BG)
        row.pack(fill="both", expand=True, padx=16, pady=16)

        badge = tk.Canvas(row, width=46, height=52, highlightthickness=0, bg=DROPZONE_BG)
        badge.create_polygon(_rounded_points(0, 0, 46, 52, 8), smooth=True, fill=ACCENT_BLUE, outline=ACCENT_BLUE)
        badge.create_polygon(34, 0, 46, 0, 46, 12, fill=DROPZONE_BG, outline=DROPZONE_BG)
        badge.create_text(23, 32, text="XLSX", fill="white", font=(FONT_FAMILY, 7, "bold"))
        badge.pack(side="left", anchor="n")

        info = tk.Frame(row, bg=DROPZONE_BG)
        info.pack(side="left", fill="both", expand=True, padx=(14, 0))
        tk.Label(info, text="Arquivo selecionado", bg=DROPZONE_BG, fg=TEXT_SECONDARY,
                 font=(FONT_FAMILY, 9)).pack(anchor="w")
        tk.Label(info, text=path.name, bg=DROPZONE_BG, fg=TEXT_PRIMARY, wraplength=230, justify="left",
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(1, 0))
        try:
            size_txt = fmt_size(path.stat().st_size)
        except OSError:
            size_txt = ""
        tk.Label(info, text=size_txt, bg=DROPZONE_BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 9)).pack(anchor="w")
        change = tk.Label(info, text="Trocar arquivo", bg=DROPZONE_BG, fg=ACCENT_BLUE,
                           font=(FONT_FAMILY, 9, "underline"), cursor="hand2")
        change.pack(anchor="w", pady=(8, 0))
        change.bind("<Button-1>", lambda _e: self._pick())

    # -- ações --

    def _pick(self) -> None:
        chosen = filedialog.askopenfilename(title="Selecionar arquivo XLSX", filetypes=[("Excel", "*.xlsx")])
        if not chosen:
            return
        self.set_path(Path(chosen))
        self._on_pick()

    def set_path(self, path: Path) -> None:
        self.path = path
        self._build_selected(path)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nordex Comparador")
        self.geometry("1120x920")
        self.minsize(860, 680)
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
            troughcolor=SOFT_BLUE_BG, background=ACCENT_BLUE,
            bordercolor=SOFT_BLUE_BG, lightcolor=ACCENT_BLUE, darkcolor=ACCENT_BLUE,
        )
        style.configure(
            "Nordex.Vertical.TScrollbar",
            troughcolor=BG, background=CARD_BORDER, bordercolor=BG,
            arrowcolor=TEXT_SECONDARY, lightcolor=CARD_BORDER, darkcolor=CARD_BORDER,
        )
        style.map("Nordex.Vertical.TScrollbar", background=[("active", "#C7D4E6")])

    # ---------------- layout ----------------

    def _build_header(self):
        header = tk.Frame(self, bg=CARD_BG, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        inner = tk.Frame(header, bg=CARD_BG)
        inner.pack(side="left", padx=32, pady=12)

        if LOGO_PATH.exists():
            self._logo_img = tk.PhotoImage(file=str(LOGO_PATH))
            factor = max(1, round(self._logo_img.height() / 40))
            if factor > 1:
                self._logo_img = self._logo_img.subsample(factor, factor)
            tk.Label(inner, image=self._logo_img, bg=CARD_BG).pack(side="left")
        else:
            tk.Label(inner, text="NORDEX", bg=CARD_BG, fg=ACCENT_BLUE,
                     font=(FONT_FAMILY, 18, "bold")).pack(side="left")

        tk.Frame(inner, bg=CARD_BORDER, width=1, height=40).pack(side="left", padx=24)

        icon_wrap = tk.Frame(inner, bg=CARD_BG)
        icon_wrap.pack(side="left")
        badge = tk.Canvas(icon_wrap, width=40, height=40, highlightthickness=0, bg=CARD_BG)
        badge.create_polygon(_rounded_points(0, 0, 40, 40, 10), smooth=True, fill=SOFT_BLUE_BG, outline=SOFT_BLUE_BG)
        _icon_bars(badge, 20, 20, ACCENT_BLUE)
        badge.pack(side="left")

        titles = tk.Frame(inner, bg=CARD_BG)
        titles.pack(side="left", padx=(14, 0))
        tk.Label(titles, text="Comparador de Pagamentos", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 15, "bold")).pack(anchor="w")
        tk.Label(titles, text="Analise e concilie arquivos de pagamentos e fornecedores", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(anchor="w")

        tk.Frame(self, bg=CARD_BORDER, height=1).pack(fill="x")

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
        wrap.pack(fill="both", expand=True, padx=32, pady=(24, 20))

        # --- linha 1: os dois arquivos SAP ---
        files_row = tk.Frame(wrap, bg=BG)
        files_row.pack(fill="x", pady=(0, 20))
        self.slot1 = Slot(files_row, "1.", "Itens de fornecedor",
                           "Relatório SAP de administrar itens de fornecedor", self._on_files_changed)
        self.slot1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.slot2 = Slot(files_row, "2.", "Partidas individuais no Razão",
                           "Relatório SAP de partidas individuais", self._on_files_changed)
        self.slot2.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # --- linha 2: pasta de saída + configurações (informativo) ---
        row2 = tk.Frame(wrap, bg=BG)
        row2.pack(fill="x", pady=(0, 20))
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)
        self._build_output_card(row2).grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._build_settings_card(row2).grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # --- CTA ---
        self.run_btn = primary_button(
            wrap, "▶  Executar Análise", self._start_run, height=64,
            subtitle="Selecione os dois arquivos e a pasta de saída",
        )
        self.run_btn.pack(fill="x", pady=(0, 20))
        self.run_btn.set_enabled(False)

        self.progress = ttk.Progressbar(wrap, mode="indeterminate", style="Nordex.Horizontal.TProgressbar")

        self.console_panel = self._panel(wrap)
        tk.Label(self.console_panel, text="Console", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", padx=20, pady=(16, 10))
        console_wrap = tk.Frame(self.console_panel, bg=CARD_BG)
        console_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.console = tk.Text(console_wrap, height=12, bg=TEXT_PRIMARY, fg="#DCE9FD",
                                insertbackground="#DCE9FD", font=("Consolas", 9),
                                relief="flat", wrap="word", state="disabled")
        self.console.tag_config("stderr", foreground="#FFB4BC")
        self.console.pack(fill="both", expand=True)

        # --- KPIs + tabela de resultado (só aparecem depois de rodar) ---
        self.kpi_row = tk.Frame(wrap, bg=BG)
        self.results_panel = self._panel(wrap)
        self._results_header_built = False

        self.success_panel = self._panel(wrap)
        self._build_success_panel()

        self.error_panel = self._panel(wrap)
        self._build_error_panel()

        self._update_run_state()

    def _panel(self, master):
        return tk.Frame(master, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)

    def _build_output_card(self, master):
        card = self._panel(master)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(inner, text="3. Pasta de saída", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", pady=(0, 12))

        box = tk.Frame(inner, bg=DROPZONE_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        box.pack(fill="x")
        self.output_lbl = tk.Label(box, text="Nenhuma pasta selecionada", bg=DROPZONE_BG, fg=TEXT_MUTED,
                                    font=(FONT_FAMILY, 10), anchor="w")
        self.output_lbl.pack(fill="x", padx=14, pady=12)

        actions = tk.Frame(inner, bg=CARD_BG)
        actions.pack(fill="x", pady=(14, 0))
        link = tk.Label(actions, text="Selecionar pasta", bg=CARD_BG, fg=ACCENT_BLUE,
                         font=(FONT_FAMILY, 10, "underline"), cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: self._pick_output())
        icon_button(actions, self._pick_output, _icon_folder, size=44).pack(side="right")
        return card

    def _build_settings_card(self, master):
        card = self._panel(master)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(inner, text="Configurações de análise", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", pady=(0, 10))

        def kv_row(label, value, border_top=True):
            # Empilhado (label em cima, valor embaixo) em vez de lado a lado:
            # o card fica estreito o bastante (metade da largura da janela)
            # pra "Regras SAP (automático)" não caber ao lado do rótulo sem
            # estourar a borda — empilhado funciona em qualquer largura.
            if border_top:
                tk.Frame(inner, bg=CARD_BORDER, height=1).pack(fill="x")
            row = tk.Frame(inner, bg=CARD_BG)
            row.pack(fill="x", pady=10)
            tk.Label(row, text=label, bg=CARD_BG, fg=TEXT_SECONDARY,
                     font=(FONT_FAMILY, 9)).pack(anchor="w")
            tk.Label(row, text=value, bg=CARD_BG, fg=TEXT_PRIMARY,
                     font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(2, 0))

        kv_row("Comparar por", "Regras SAP (automático)", border_top=False)
        kv_row("Moeda", "BRL (R$)")
        return card

    def _build_success_panel(self):
        # Sem cabeçalho de card aqui de propósito — o "4. Resultado da
        # Análise" já é o título do results_panel (tabela) logo acima;
        # este painel é só o banner de status, igual ao design.
        row = tk.Frame(self.success_panel, bg=GREEN_BG, highlightbackground=GREEN_BORDER, highlightthickness=1)
        row.pack(fill="x", padx=20, pady=(20, 20))
        inner = tk.Frame(row, bg=GREEN_BG)
        inner.pack(fill="x", padx=16, pady=14)
        inner.grid_columnconfigure(1, weight=1)

        circle_badge(inner, 36, GREEN, lambda cv, cx, cy: cv.create_text(
            cx, cy, text="✓", fill="white", font=(FONT_FAMILY, 13, "bold"))).grid(row=0, column=0, sticky="n")

        info = tk.Frame(inner, bg=GREEN_BG)
        info.grid(row=0, column=1, sticky="w", padx=14)
        tk.Label(info, text="Relatório gerado com sucesso!", bg=GREEN_BG, fg=GREEN_TITLE,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w")
        self.success_filename = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_filename.pack(anchor="w")
        self.success_path = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_path.pack(anchor="w")
        self.success_size = tk.Label(info, bg=GREEN_BG, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w")
        self.success_size.pack(anchor="w")

        actions = tk.Frame(inner, bg=GREEN_BG)
        actions.grid(row=0, column=2, sticky="e", padx=(14, 0))
        secondary_button(actions, "Abrir Relatório", self._open_file, width=150).pack(side="left", padx=(0, 8))
        primary_button(actions, "Abrir Pasta do Relatório", self._open_folder, width=190).pack(side="left")

    def _build_error_panel(self):
        tk.Label(self.error_panel, text="Falha ao gerar relatório", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=20, pady=(18, 12))
        row = tk.Frame(self.error_panel, bg=RED_BG, highlightbackground=RED_BORDER, highlightthickness=1)
        row.pack(fill="x", padx=20, pady=(0, 20))
        inner = tk.Frame(row, bg=RED_BG)
        inner.pack(fill="x", padx=16, pady=14)

        circle_badge(inner, 36, RED, lambda cv, cx, cy: cv.create_text(
            cx, cy, text="✕", fill="white", font=(FONT_FAMILY, 13, "bold"))).pack(side="left", anchor="n")

        info = tk.Frame(inner, bg=RED_BG)
        info.pack(side="left", fill="both", expand=True, padx=14)
        tk.Label(info, text="Não foi possível gerar o relatório", bg=RED_BG, fg=RED_DARK,
                 font=(FONT_FAMILY, 11, "bold")).pack(anchor="w")
        self.error_msg = tk.Text(info, height=6, bg=RED_BG, fg=RED_DARK, font=("Consolas", 9),
                                  relief="flat", wrap="word", bd=0, state="disabled")
        self.error_msg.pack(fill="both", expand=True, pady=(6, 0))

    # ---------------- KPIs + tabela (reconstruídos a cada rodada) ----------------

    def _kpi_card(self, master, bg, draw_icon, value, label, hint):
        card = self._panel(master)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        circle_badge(inner, 52, bg, draw_icon).pack(side="left")
        text = tk.Frame(inner, bg=CARD_BG)
        text.pack(side="left", padx=(14, 0), fill="x", expand=True)
        tk.Label(text, text=value, bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 17, "bold")).pack(anchor="w")
        tk.Label(text, text=label, bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(2, 0))
        tk.Label(text, text=hint, bg=CARD_BG, fg=TEXT_MUTED,
                 font=(FONT_FAMILY, 8)).pack(anchor="w")
        return card

    def _render_kpis(self, rows, counts):
        for w in self.kpi_row.winfo_children():
            w.destroy()
        by_label = dict(counts)
        partidas = by_label.get("Partidas individuais no Razão", "-")
        fornecedor = by_label.get("Administrar itens de fornecedor", "-")
        produtos = [r for r in rows if r[0] != "Total Geral"]
        total_raw = next((v for k, v in rows if k == "Total Geral"), "0")

        specs = [
            (KPI_BLUE_BG, lambda cv, cx, cy: _icon_bars(cv, cx, cy, ACCENT_BLUE),
             partidas, "Partidas individuais", "Linhas do Razão"),
            (KPI_GREEN_BG, lambda cv, cx, cy: _icon_people(cv, cx, cy, GREEN),
             fornecedor, "Itens de fornecedor", "Linhas de fornecedor"),
            (KPI_PURPLE_BG, lambda cv, cx, cy: _icon_coin(cv, cx, cy, KPI_PURPLE_FG),
             fmt_compact_brl(total_raw), "Total processado", "Valor total analisado"),
            (KPI_AMBER_BG, lambda cv, cx, cy: _icon_tag(cv, cx, cy, KPI_AMBER_FG),
             str(len(produtos)), "Categorias", "Produtos classificados"),
        ]
        for i, (bg, icon, value, label, hint) in enumerate(specs):
            card = self._kpi_card(self.kpi_row, bg, icon, value, label, hint)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0 if i == 3 else 0))
            self.kpi_row.grid_columnconfigure(i, weight=1)

    def _render_results_table(self, rows):
        for w in self.results_panel.winfo_children():
            w.destroy()
        tk.Label(self.results_panel, text="4. Resultado da Análise", bg=CARD_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=20, pady=(18, 12))

        table = tk.Frame(self.results_panel, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        table.pack(fill="x", padx=20, pady=(0, 20))
        table.grid_columnconfigure(0, weight=1)
        table.grid_columnconfigure(1, minsize=200)

        head = tk.Frame(table, bg=DROPZONE_BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        head.grid_columnconfigure(1, minsize=200)
        tk.Label(head, text="Categoria / Produto", bg=DROPZONE_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 10, "bold")).grid(row=0, column=0, sticky="w", padx=20, pady=12)
        tk.Label(head, text="Valor (BRL)", bg=DROPZONE_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 10, "bold")).grid(row=0, column=1, sticky="e", padx=20, pady=12)

        r = 1
        for label, raw_value in rows:
            is_total = label == "Total Geral"
            row_bg = TOTAL_ROW_BG if is_total else CARD_BG
            neg = raw_value.strip().startswith("-")
            amount = to_ptbr(raw_value)
            weight = "bold" if is_total else "normal"
            fg = RED if neg else TEXT_PRIMARY

            tk.Frame(table, bg=TABLE_BORDER, height=1).grid(row=r, column=0, columnspan=2, sticky="ew")
            r += 1
            line = tk.Frame(table, bg=row_bg)
            line.grid(row=r, column=0, columnspan=2, sticky="ew")
            line.grid_columnconfigure(0, weight=1)
            line.grid_columnconfigure(1, minsize=200)
            tk.Label(line, text=label, bg=row_bg, fg=TEXT_PRIMARY,
                     font=(FONT_FAMILY, 10, weight)).grid(row=0, column=0, sticky="w", padx=20, pady=12)
            tk.Label(line, text=amount, bg=row_bg, fg=fg,
                     font=(FONT_FAMILY, 10, weight)).grid(row=0, column=1, sticky="e", padx=20, pady=12)
            r += 1

    # ---------------- state ----------------

    def _on_files_changed(self):
        self._hide_reports()
        self._update_run_state()

    def _pick_output(self):
        chosen = filedialog.askdirectory(title="Selecionar pasta de saída")
        if not chosen:
            return
        self.output_dir = Path(chosen)
        self.output_lbl.config(text=chosen, fg=TEXT_PRIMARY)
        self._update_run_state()

    def _can_run(self) -> bool:
        return bool(self.slot1.path and self.slot2.path and self.output_dir) and not self.is_running

    def _update_run_state(self):
        self.run_btn.set_enabled(self._can_run())
        if self.is_running:
            return
        if not (self.slot1.path and self.slot2.path):
            sub = "Selecione os dois arquivos e a pasta de saída"
        elif not self.output_dir:
            sub = "Selecione a pasta de saída"
        else:
            sub = "Processar arquivos e gerar relatório"
        self.run_btn.set_text("▶  Executar Análise", sub)

    def _hide_reports(self):
        self.success_panel.pack_forget()
        self.error_panel.pack_forget()
        self.kpi_row.pack_forget()
        self.results_panel.pack_forget()

    # ---------------- run ----------------

    def _start_run(self):
        if not self._can_run():
            return
        self.is_running = True
        self._hide_reports()
        self.run_btn.set_enabled(False)
        self.run_btn.set_text("⏳  Processando...", "Aguarde enquanto os arquivos são processados")

        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

        self.console_panel.pack_forget()
        self.progress.pack(fill="x", pady=(0, 20))
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
        self._update_run_state()

        if rows:
            self._render_kpis(rows, counts)
            self.kpi_row.pack(fill="x", pady=(0, 20))
            self._render_results_table(rows)
            self.results_panel.pack(fill="x", pady=(0, 20))

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
