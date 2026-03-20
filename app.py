"""
app.py
------
Janela principal unificada do Price Checker Bot.

Abas:
  ▶  Monitoramento   — Iniciar verificação, logs em tempo real, barra de progresso
  ⚙  Configurações   — Google Sheets e Telegram
  📦  Produtos        — Adicionar / Editar / Remover produtos monitorados
  🏪  Lojas           — Mapeamento de domínios → scrapers

Execute:
    python app.py

Empacote com:
    .\\build.bat
"""

# ─────────────────────────────────────────────────────────────────────────────
# Stdlib
# ─────────────────────────────────────────────────────────────────────────────
import ast
import json
import logging
import queue
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import messagebox, ttk

# ─────────────────────────────────────────────────────────────────────────────
# BASE_DIR: funciona em .py e em .exe (PyInstaller frozen)
# ─────────────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH         = BASE_DIR / "config.json"
STORE_DETECTOR_PATH = BASE_DIR / "price_tracker" / "core" / "store_detector.py"
SCRAPERS_DIR        = BASE_DIR / "price_tracker" / "scrapers"

# ─────────────────────────────────────────────────────────────────────────────
# Paleta de cores (tema escuro — Catppuccin Mocha)
# ─────────────────────────────────────────────────────────────────────────────
BG        = "#1e1e2e"
BG_PANEL  = "#313244"
BG_INPUT  = "#181825"
ACCENT    = "#89b4fa"
SUCCESS   = "#a6e3a1"
WARNING   = "#f9e2af"
ERROR_C   = "#f38ba8"
FG        = "#cdd6f4"
FG_DIM    = "#6c7086"
FG_DARK   = "#1e1e2e"
SEL_BG    = "#45475a"

FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 9)
FONT_LABEL = ("Segoe UI", 9)

# ─────────────────────────────────────────────────────────────────────────────
# IDs de scrapers builtin
# ─────────────────────────────────────────────────────────────────────────────
_BUILTIN_SCRAPER_IDS = {"kabum", "pichau", "amazon", "terabyte"}

# Template de scraper
_SCRAPER_TEMPLATE = '''\
"""
scrapers/{sid}.py
{dash}
Scraper especifico para {sid}.
"""
import logging
from typing import Optional
from bs4 import BeautifulSoup
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SELECTORS: list[str] = [
    # ".preco-produto",
    # "[data-testid=\'price\']",
]

def extract(soup: BeautifulSoup) -> Optional[dict]:
    for selector in _SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)
            if price is not None:
                logger.info(f"[{sid}] Preco R$ {{price:.2f}} - seletor: \'{{selector}}\'")
                return {{"price": price, "currency": "BRL", "confidence": 0.88}}
        except Exception as exc:
            logger.debug(f"[{sid}] Erro no seletor \'{{selector}}\': {{exc}}")
    logger.warning("[{sid}] Nenhum seletor retornou preco valido.")
    return None
'''

# ─────────────────────────────────────────────────────────────────────────────
# I/O — config.json
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {
            "google_sheets": {"credentials_file": "credentials.json", "spreadsheet_name": "Price Tracker"},
            "telegram": {"enabled": False, "bot_token": "", "chat_id": "", "alert_on_new_low": True},
            "products": [],
        }
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# I/O — STORE_MAP (armazenado em config.json["store_map"])
# ─────────────────────────────────────────────────────────────────────────────

# Lojas builtin hardcoded — importadas diretamente do módulo compilado
from price_tracker.core.store_detector import STORE_MAP as _BUILTIN_STORE_MAP


def load_store_map() -> dict:
    """Retorna builtin stores + custom stores do config.json."""
    result = dict(_BUILTIN_STORE_MAP)
    cfg = load_config()
    result.update(cfg.get("store_map", {}))
    return result


def save_store_map(store_map: dict, config: dict) -> None:
    """Salva apenas lojas não-builtin em config.json[\"store_map\"]."""
    custom = {k: v for k, v in store_map.items() if k not in _BUILTIN_STORE_MAP}
    config["store_map"] = custom


def create_scraper_template(store_id: str) -> Path:
    dest = SCRAPERS_DIR / f"{store_id}.py"
    dash = "-" * (len(f"scrapers/{store_id}.py") + 1)
    dest.write_text(_SCRAPER_TEMPLATE.format(sid=store_id, dash=dash), encoding="utf-8")
    return dest


def _scraper_status(scraper_id: str) -> str:
    py_file = SCRAPERS_DIR / f"{scraper_id}.py"
    if py_file.exists():
        return "Builtin" if scraper_id in _BUILTIN_SCRAPER_IDS else "Personalizado"
    return "Sem arquivo"


def _read_scraper_selectors(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'_SELECTORS\s*(?::\s*list\[str\])?\s*=\s*\[(.*?)\]', text, re.DOTALL)
    if not m:
        return []
    selectors = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m2 = re.match(r'^["\'](.+?)["\'],?\s*$', stripped)
        if m2:
            selectors.append(m2.group(1))
    return selectors


def _write_scraper_selectors(path: Path, selectors: list) -> None:
    text = path.read_text(encoding="utf-8")
    if selectors:
        inner = "\n".join(f'    "{s}",' for s in selectors)
        new_block = f"[\n{inner}\n]"
    else:
        new_block = "[]"
    new_text = re.sub(
        r'(_SELECTORS\s*(?::\s*list\[str\])?\s*=\s*)\[.*?\]',
        lambda mo: mo.group(1) + new_block,
        text, flags=re.DOTALL,
    )
    path.write_text(new_text, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-fill helpers
# ─────────────────────────────────────────────────────────────────────────────

def _gui_auto_name(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            slug = parts[-1].replace("-", " ").replace("_", " ").strip()
            if slug and not slug.isdigit():
                return slug[:80].title()
        return urlparse(url).netloc.lstrip("www.").split(".")[0].title()
    except Exception:
        return "Produto"


def _gui_auto_store(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host  = urlparse(url).netloc.lstrip("www.")
        parts = [p for p in host.split(".") if p]
        if len(parts) >= 3 and parts[-1] == "br" and parts[-2] in {"com", "net", "org", "gov"}:
            return parts[-3].title()
        if len(parts) >= 2:
            return parts[-2].title()
        return parts[0].title() if parts else "?"
    except Exception:
        return "?"


# ─────────────────────────────────────────────────────────────────────────────
# Logging handler thread-safe
# ─────────────────────────────────────────────────────────────────────────────

class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(record)


# =============================================================================
# Diálogos modais
# =============================================================================

class _BaseDialog(tk.Toplevel):
    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")


class ScraperEditorDialog(_BaseDialog):
    def __init__(self, parent, scraper_id: str, path: Path):
        super().__init__(parent)
        self.title(f"Editar Scraper — {scraper_id}")
        self.resizable(True, True)
        self.minsize(520, 380)
        self.grab_set()
        self._path = path

        hdr = ttk.LabelFrame(self, text="Arquivo", padding=8)
        hdr.pack(fill="x", padx=12, pady=(12, 4))
        try:
            rel = path.relative_to(BASE_DIR)
        except ValueError:
            rel = path
        ttk.Label(hdr, text=str(rel)).pack(anchor="w")

        sel_frame = ttk.LabelFrame(
            self, text="Seletores CSS (um por linha, do mais ao menos especifico)", padding=10
        )
        sel_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._sel_text = tk.Text(sel_frame, width=64, height=10, font=FONT_MONO,
                                 bg=BG_INPUT, fg=FG, insertbackground=FG)
        vsb = ttk.Scrollbar(sel_frame, command=self._sel_text.yview)
        self._sel_text.configure(yscrollcommand=vsb.set)
        self._sel_text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        selectors = _read_scraper_selectors(path)
        if selectors:
            self._sel_text.insert("1.0", "\n".join(selectors))

        ttk.Label(
            self,
            text=(
                "O bot testa cada seletor em ordem ate encontrar um preco valido.\n"
                "Deixe em branco para depender apenas de JSON-LD e heuristica automatica."
            ),
        ).pack(anchor="w", padx=12, pady=(0, 4))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Salvar",   command=self._save).pack(side="right")
        self._center(parent)

    def _save(self) -> None:
        raw = self._sel_text.get("1.0", "end").strip()
        selectors = [s.strip() for s in raw.splitlines() if s.strip()]
        try:
            _write_scraper_selectors(self._path, selectors)
            self.destroy()
        except Exception as exc:
            messagebox.showwarning("Erro ao salvar", f"Nao foi possivel salvar:\n{exc}", parent=self)


class ProductDialog(_BaseDialog):
    def __init__(self, parent, product: Optional[dict] = None):
        super().__init__(parent)
        self.title("Novo Produto" if product is None else "Editar Produto")
        self.resizable(False, True)
        self.grab_set()
        self.result: Optional[dict] = None

        pad = {"padx": 8, "pady": 5}

        # ── Seletor de modo ───────────────────────────────────────────────
        mode_frame = ttk.LabelFrame(self, text="Modo de busca", padding=8)
        mode_frame.pack(fill="x", padx=12, pady=(12, 4))
        initial_mode = (product.get("search_mode", "url") if product else "url")
        self._mode_var = tk.StringVar(value=initial_mode)
        ttk.Radiobutton(
            mode_frame, text="URL direta  (comportamento atual)",
            variable=self._mode_var, value="url",
            command=self._on_mode_change,
        ).pack(side="left", padx=(4, 16))
        ttk.Radiobutton(
            mode_frame, text="Busca no Shopping  (multi-loja, por palavras-chave)",
            variable=self._mode_var, value="shopping",
            command=self._on_mode_change,
        ).pack(side="left", padx=4)

        # ── Frame: modo URL ───────────────────────────────────────────────
        self._url_frame = ttk.LabelFrame(self, text="URL e Seletores", padding=10)

        for row, label in enumerate(["Nome do produto (opcional):", "Loja (opcional):", "URL da pagina:"]):
            ttk.Label(self._url_frame, text=label).grid(row=row, column=0, sticky="w", **pad)
            e = ttk.Entry(self._url_frame, width=55)
            e.grid(row=row, column=1, sticky="ew", **pad)
            setattr(self, ["_name_e", "_store_e", "_url_e"][row], e)
        self._url_frame.columnconfigure(1, weight=1)

        self._url_e.bind("<FocusOut>", self._auto_fill_store)
        ttk.Label(
            self._url_frame,
            text="Nome e Loja sao opcionais — preenchidos automaticamente pela URL.",
            font=("Segoe UI", 8),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 2))

        sel_inner = ttk.LabelFrame(self._url_frame, text="Seletores CSS (opcionais, um por linha)", padding=8)
        sel_inner.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=4, pady=(4, 0))
        self._url_frame.rowconfigure(4, weight=1)
        ttk.Label(
            sel_inner,
            text="Camadas: 1. JSON-LD   2. Scraper dedicado   3. Seletores CSS   4. Heuristica",
            justify="left",
        ).pack(anchor="w", padx=2, pady=(0, 4))
        self._sel_text = tk.Text(sel_inner, width=60, height=6, font=FONT_MONO,
                                 bg=BG_INPUT, fg=FG, insertbackground=FG)
        sb = ttk.Scrollbar(sel_inner, command=self._sel_text.yview)
        self._sel_text.configure(yscrollcommand=sb.set)
        self._sel_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ── Frame: modo Shopping ──────────────────────────────────────────
        self._shop_frame = ttk.LabelFrame(self, text="Busca no Shopping", padding=10)

        ttk.Label(self._shop_frame, text="Nome do produto:").grid(row=0, column=0, sticky="w", **pad)
        self._shop_name_e = ttk.Entry(self._shop_frame, width=55)
        self._shop_name_e.grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(self._shop_frame, text="Palavras-chave\n(uma por linha):").grid(row=1, column=0, sticky="nw", **pad)
        kw_wrap = tk.Frame(self._shop_frame, bg=BG_INPUT)
        kw_wrap.grid(row=1, column=1, sticky="nsew", **pad)
        self._kw_text = tk.Text(kw_wrap, width=52, height=4, font=FONT_MONO,
                                bg=BG_INPUT, fg=FG, insertbackground=FG)
        kw_sb = ttk.Scrollbar(kw_wrap, command=self._kw_text.yview)
        self._kw_text.configure(yscrollcommand=kw_sb.set)
        self._kw_text.pack(side="left", fill="both", expand=True)
        kw_sb.pack(side="right", fill="y")
        ttk.Label(self._shop_frame, text="Ex: rtx 4070 super, placa de video nvidia",
                  font=("Segoe UI", 8)).grid(row=2, column=1, sticky="w", padx=8, pady=(0, 4))

        nums_frame = ttk.Frame(self._shop_frame)
        nums_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

        ttk.Label(nums_frame, text="Max. resultados:").grid(row=0, column=0, sticky="w", padx=(4, 4), pady=3)
        self._max_results_e = ttk.Entry(nums_frame, width=8)
        self._max_results_e.insert(0, "10")
        self._max_results_e.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(nums_frame, text="Preco minimo (R$):").grid(row=0, column=2, sticky="w", padx=(16, 4), pady=3)
        self._min_price_e = ttk.Entry(nums_frame, width=12)
        self._min_price_e.grid(row=0, column=3, sticky="w", pady=3)

        ttk.Label(nums_frame, text="Preco maximo (R$):").grid(row=0, column=4, sticky="w", padx=(16, 4), pady=3)
        self._max_price_e = ttk.Entry(nums_frame, width=12)
        self._max_price_e.grid(row=0, column=5, sticky="w", pady=3)

        src_frame = ttk.LabelFrame(self._shop_frame, text="Fontes de busca", padding=6)
        src_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 0))
        self._src_ml_var   = tk.BooleanVar(value=True)
        self._src_zoom_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(src_frame, text="Mercado Livre  (API gratuita)", variable=self._src_ml_var).pack(side="left", padx=8)
        ttk.Checkbutton(src_frame, text="Zoom.com.br  (agregador BR)",   variable=self._src_zoom_var).pack(side="left", padx=8)

        self._shop_frame.columnconfigure(1, weight=1)

        # ── Preenche campos ao editar produto existente ───────────────────
        if product:
            if initial_mode == "shopping":
                self._shop_name_e.insert(0, product.get("name", ""))
                self._kw_text.insert("1.0", "\n".join(product.get("keywords", [])))
                self._max_results_e.delete(0, "end")
                self._max_results_e.insert(0, str(product.get("max_results", 10)))
                mi = product.get("min_price")
                mx = product.get("max_price")
                if mi is not None:
                    self._min_price_e.insert(0, str(mi))
                if mx is not None:
                    self._max_price_e.insert(0, str(mx))
                sources = product.get("sources", ["mercadolivre", "zoom"])
                self._src_ml_var.set("mercadolivre" in sources)
                self._src_zoom_var.set("zoom" in sources)
            else:
                self._name_e.insert(0, product.get("name", ""))
                self._store_e.insert(0, product.get("store", ""))
                self._url_e.insert(0, product.get("url", ""))
                self._sel_text.insert("1.0", "\n".join(product.get("price_selectors", [])))

        # ── Botoes ────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Salvar",   command=self._save).pack(side="right")

        # Exibe o frame correspondente ao modo inicial
        self._on_mode_change()
        self._center(parent)

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        if mode == "shopping":
            self._url_frame.pack_forget()
            self._shop_frame.pack(fill="both", expand=True, padx=12, pady=4)
        else:
            self._shop_frame.pack_forget()
            self._url_frame.pack(fill="both", expand=True, padx=12, pady=4)

    def _auto_fill_store(self, _event=None) -> None:
        if self._store_e.get().strip():
            return
        url = self._url_e.get().strip()
        if url:
            store = _gui_auto_store(url)
            if store and store != "?":
                self._store_e.insert(0, store)

    def _save(self) -> None:
        mode = self._mode_var.get()

        if mode == "shopping":
            name = self._shop_name_e.get().strip()
            if not name:
                messagebox.showwarning("Campo obrigatorio", "Informe o nome do produto.", parent=self)
                return
            keywords = [k.strip() for k in self._kw_text.get("1.0", "end").strip().splitlines() if k.strip()]
            try:
                max_results = int(self._max_results_e.get().strip() or "10")
            except ValueError:
                messagebox.showwarning("Valor invalido", "Max. resultados deve ser um numero inteiro.", parent=self)
                return
            def _parse_price(s):
                s = s.strip().replace(",", ".")
                return float(s) if s else None
            try:
                min_p = _parse_price(self._min_price_e.get())
                max_p = _parse_price(self._max_price_e.get())
            except ValueError:
                messagebox.showwarning("Valor invalido", "Preco minimo/maximo invalido.", parent=self)
                return
            sources = []
            if self._src_ml_var.get():
                sources.append("mercadolivre")
            if self._src_zoom_var.get():
                sources.append("zoom")
            if not sources:
                messagebox.showwarning("Fontes vazias", "Selecione ao menos uma fonte de busca.", parent=self)
                return
            result: dict = {
                "search_mode": "shopping",
                "name": name,
                "keywords": keywords,
                "max_results": max_results,
                "sources": sources,
            }
            if min_p is not None:
                result["min_price"] = min_p
            if max_p is not None:
                result["max_price"] = max_p
            self.result = result
            self.destroy()
            return

        # Modo URL
        url   = self._url_e.get().strip()
        name  = self._name_e.get().strip()
        store = self._store_e.get().strip()
        sels  = [s.strip() for s in self._sel_text.get("1.0", "end").strip().splitlines() if s.strip()]
        if not url:
            messagebox.showwarning("Campo obrigatorio", "Informe a URL do produto.", parent=self)
            return
        result = {"url": url, "name": name or _gui_auto_name(url), "store": store or _gui_auto_store(url)}
        if sels:
            result["price_selectors"] = sels
        self.result = result
        self.destroy()


class StoreDialog(_BaseDialog):
    def __init__(self, parent, existing_keys: set):
        super().__init__(parent)
        self.title("Adicionar Loja")
        self.resizable(False, False)
        self.grab_set()
        self.result: Optional[dict] = None
        self._existing = existing_keys

        pad = {"padx": 8, "pady": 5}
        fields_frame = ttk.LabelFrame(self, text="Mapeamento de Dominio", padding=12)
        fields_frame.pack(fill="x", padx=12, pady=(12, 4))

        ttk.Label(fields_frame, text="Dominio da loja:").grid(row=0, column=0, sticky="w", **pad)
        self._domain_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self._domain_var, width=30).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(fields_frame, text='Ex: "americanas" para americanas.com.br', font=("Segoe UI", 8)).grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(fields_frame, text="ID do scraper:").grid(row=2, column=0, sticky="w", **pad)
        self._id_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self._id_var, width=30).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Label(fields_frame, text='Arquivo em price_tracker/scrapers/ (sem ".py")', font=("Segoe UI", 8)).grid(row=3, column=1, sticky="w", padx=8)
        fields_frame.columnconfigure(1, weight=1)
        self._domain_var.trace_add("write", self._auto_fill_id)

        opt_frame = ttk.Frame(self, padding=(12, 4))
        opt_frame.pack(fill="x")
        self._create_file_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Criar arquivo de scraper template", variable=self._create_file_var).pack(anchor="w")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Button(btn_frame, text="Cancelar",  command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Adicionar", command=self._save).pack(side="right")
        self._center(parent)

    def _auto_fill_id(self, *_) -> None:
        domain  = self._domain_var.get().strip().lower()
        safe    = re.sub(r"[^a-z0-9_-]", "", domain)
        current = self._id_var.get().strip()
        if not current or current == getattr(self, "_last_auto", ""):
            self._id_var.set(safe)
            self._last_auto = safe

    def _save(self) -> None:
        domain     = self._domain_var.get().strip().lower()
        scraper_id = self._id_var.get().strip().lower()
        if not domain:
            messagebox.showwarning("Campo obrigatorio", "Informe o dominio.", parent=self)
            return
        if not scraper_id:
            messagebox.showwarning("Campo obrigatorio", "Informe o ID do scraper.", parent=self)
            return
        if domain in self._existing:
            messagebox.showwarning("Dominio duplicado", f'"{domain}" ja existe.', parent=self)
            return
        self.result = {"domain": domain, "scraper_id": scraper_id, "create_file": self._create_file_var.get()}
        self.destroy()


# =============================================================================
# Abas de conteúdo
# =============================================================================

class MonitorTab(ttk.Frame):
    """Aba principal: execucao do bot, barra de progresso e logs."""

    _FORMATTER = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    def __init__(self, parent, app: "App"):
        super().__init__(parent)
        self._app = app
        self._running = False
        self._build()

    def _build(self) -> None:
        # Resumo de config
        info_bar = tk.Frame(self, bg=BG, pady=6)
        info_bar.pack(fill="x", padx=16)
        self._info_lbl = tk.Label(info_bar, text="", font=FONT_SMALL, bg=BG, fg=FG_DIM, justify="left")
        self._info_lbl.pack(side="left")

        # Botões de controle
        ctrl = tk.Frame(self, bg=BG, pady=8)
        ctrl.pack(fill="x", padx=16)

        self._run_btn = tk.Button(
            ctrl, text="▶   Iniciar Verificacao",
            bg=SUCCESS, fg=FG_DARK, activebackground=SUCCESS, activeforeground=FG_DARK,
            relief="flat", padx=16, pady=7, font=("Segoe UI", 10, "bold"),
            cursor="hand2", command=self._start_run,
        )
        self._run_btn.pack(side="left")

        tk.Button(
            ctrl, text="Limpar Logs",
            bg=BG_PANEL, fg=FG, activebackground=SEL_BG, activeforeground=FG,
            relief="flat", padx=14, pady=7, font=("Segoe UI", 10),
            cursor="hand2", command=self._clear_logs,
        ).pack(side="left", padx=8)

        # Barra de progresso
        prog_outer = tk.Frame(self, bg=BG, pady=2)
        prog_outer.pack(fill="x", padx=16)
        self._prog_lbl = tk.Label(prog_outer, text="", font=FONT_SMALL, bg=BG, fg=FG_DIM)
        self._prog_lbl.pack(anchor="w")
        self._pbar = ttk.Progressbar(
            prog_outer, style="App.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self._pbar.pack(fill="x", pady=(2, 6))

        # Area de logs
        log_outer = tk.Frame(self, bg=BG)
        log_outer.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        tk.Label(log_outer, text="Logs", font=("Segoe UI", 9, "bold"), bg=BG, fg=FG_DIM).pack(anchor="w")

        text_frame = tk.Frame(log_outer, bg=BG_INPUT)
        text_frame.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            text_frame, bg=BG_INPUT, fg=FG, font=FONT_MONO,
            state="disabled", relief="flat", borderwidth=0, wrap="none",
            selectbackground=SEL_BG, selectforeground=FG, insertbackground=FG,
        )
        sy = ttk.Scrollbar(text_frame, orient="vertical",   command=self._log_text.yview)
        sx = ttk.Scrollbar(text_frame, orient="horizontal", command=self._log_text.xview)
        self._log_text.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right",  fill="y")
        sx.pack(side="bottom", fill="x")
        self._log_text.pack(fill="both", expand=True, padx=2, pady=2)

        self._log_text.tag_configure("DEBUG",     foreground=FG_DIM)
        self._log_text.tag_configure("INFO",      foreground=FG)
        self._log_text.tag_configure("WARNING",   foreground=WARNING)
        self._log_text.tag_configure("ERROR",     foreground=ERROR_C)
        self._log_text.tag_configure("CRITICAL",  foreground=ERROR_C)
        self._log_text.tag_configure("SEPARATOR", foreground=ACCENT)

    def setup_logging(self, q: queue.Queue) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        h = _QueueHandler(q)
        h.setFormatter(self._FORMATTER)
        h.setLevel(logging.DEBUG)
        root_logger.addHandler(h)

    def refresh_info(self) -> None:
        try:
            cfg   = load_config()
            n     = len(cfg.get("products", []))
            sheet = cfg.get("google_sheets", {}).get("spreadsheet_name", "?")
            tg    = "ativo" if cfg.get("telegram", {}).get("enabled") else "desativado"
            self._info_lbl.configure(
                text=f"Planilha: {sheet}   |   Produtos monitorados: {n}   |   Telegram: {tg}"
            )
        except Exception:
            self._info_lbl.configure(text="config.json nao encontrado ou invalido")

    def write_log(self, record: logging.LogRecord) -> None:
        line = self._FORMATTER.format(record) + "\n"
        tag  = record.levelname if record.levelname in (
            "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        ) else "INFO"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line, tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_logs(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _start_run(self) -> None:
        if self._running:
            return
        self._running = True
        self._run_btn.configure(state="disabled", text="Executando...")
        self._app.set_status("Executando verificacao de precos...", WARNING)
        self._pbar.configure(value=0)
        self._prog_lbl.configure(text="Iniciando...")
        self._write_separator()
        threading.Thread(target=self._worker, daemon=True).start()

    def _write_separator(self) -> None:
        ts  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        sep = f"\n{'─' * 60}\n  Execucao iniciada em {ts}\n{'─' * 60}\n\n"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", sep, "SEPARATOR")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _worker(self) -> None:
        try:
            from main import setup_logging, run
            _root = logging.getLogger()
            if not any(isinstance(h, logging.FileHandler) for h in _root.handlers):
                setup_logging(level="INFO")
            run(on_progress=self._on_progress)
        except Exception:
            logging.getLogger(__name__).exception("Erro inesperado durante a execucao")
        finally:
            self.after(0, self._finish_run)

    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.after(0, self._update_progress, current, total, name)

    def _update_progress(self, current: int, total: int, name: str) -> None:
        pct = (current / total * 100) if total > 0 else 0
        self._pbar["value"] = pct
        self._prog_lbl.configure(text=f"[{current}/{total}]  {name}")

    def _finish_run(self) -> None:
        self._running = False
        self._run_btn.configure(state="normal", text="▶   Iniciar Verificacao")
        self._app.set_status("Verificacao concluida", SUCCESS)
        self._pbar["value"] = 100
        self._prog_lbl.configure(text="Concluido!")


# ─────────────────────────────────────────────────────────────────────────────

class GeneralTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=16)

        gs_frame = ttk.LabelFrame(self, text="Google Sheets", padding=12)
        gs_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(gs_frame, text="Arquivo de credenciais:").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        self.creds_var = tk.StringVar()
        ttk.Entry(gs_frame, textvariable=self.creds_var, width=52).grid(row=0, column=1, sticky="ew", padx=6, pady=5)

        ttk.Label(gs_frame, text="Nome da planilha:").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        self.sheet_var = tk.StringVar()
        ttk.Entry(gs_frame, textvariable=self.sheet_var, width=52).grid(row=1, column=1, sticky="ew", padx=6, pady=5)
        gs_frame.columnconfigure(1, weight=1)

        tg_frame = ttk.LabelFrame(self, text="Telegram (opcional)", padding=12)
        tg_frame.pack(fill="x")

        self.tg_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(tg_frame, text="Ativar alertas via Telegram", variable=self.tg_enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=5
        )
        ttk.Label(tg_frame, text="Bot Token:").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        self.tg_token_var = tk.StringVar()
        ttk.Entry(tg_frame, textvariable=self.tg_token_var, width=52).grid(row=1, column=1, sticky="ew", padx=6, pady=5)

        ttk.Label(tg_frame, text="Chat ID:").grid(row=2, column=0, sticky="w", padx=6, pady=5)
        self.tg_chat_var = tk.StringVar()
        ttk.Entry(tg_frame, textvariable=self.tg_chat_var, width=52).grid(row=2, column=1, sticky="ew", padx=6, pady=5)

        self.tg_low_var = tk.BooleanVar()
        ttk.Checkbutton(tg_frame, text="Alertar ao atingir novo minimo historico", variable=self.tg_low_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=5
        )
        tg_frame.columnconfigure(1, weight=1)

    def load(self, config: dict) -> None:
        gs = config.get("google_sheets", {})
        self.creds_var.set(gs.get("credentials_file", "credentials.json"))
        self.sheet_var.set(gs.get("spreadsheet_name", "Price Tracker"))
        tg = config.get("telegram", {})
        self.tg_enabled_var.set(tg.get("enabled", False))
        self.tg_token_var.set(tg.get("bot_token", ""))
        self.tg_chat_var.set(tg.get("chat_id", ""))
        self.tg_low_var.set(tg.get("alert_on_new_low", True))

    def flush(self, config: dict) -> None:
        config["google_sheets"] = {
            "credentials_file": self.creds_var.get().strip(),
            "spreadsheet_name": self.sheet_var.get().strip(),
        }
        config["telegram"] = {
            "enabled":          self.tg_enabled_var.get(),
            "bot_token":        self.tg_token_var.get().strip(),
            "chat_id":          self.tg_chat_var.get().strip(),
            "alert_on_new_low": self.tg_low_var.get(),
        }


# ─────────────────────────────────────────────────────────────────────────────

class ProductsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=16)
        self._products: list = []

        cols = ("nome", "loja", "seletores")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse", height=14)
        self._tree.heading("nome",      text="Produto")
        self._tree.heading("loja",      text="Loja")
        self._tree.heading("seletores", text="Seletores CSS")
        self._tree.column("nome",      width=240, minwidth=140)
        self._tree.column("loja",      width=120, minwidth=80)
        self._tree.column("seletores", width=340, minwidth=160)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<Double-1>", lambda _e: self._edit())

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for text, cmd in [
            ("Adicionar",   self._add),
            ("Editar",      self._edit),
            ("Remover",     self._remove),
            ("Mover acima", lambda: self._move(-1)),
            ("Mover abaixo", lambda: self._move(1)),
        ]:
            ttk.Button(btn_frame, text=text, command=cmd).pack(side="left", padx=(0, 4))

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for p in self._products:
            sels = ", ".join(p.get("price_selectors", []))
            self._tree.insert("", "end", values=(p.get("name", ""), p.get("store", ""), sels))

    def _selected_index(self) -> Optional[int]:
        sel = self._tree.selection()
        return self._tree.index(sel[0]) if sel else None

    def _add(self) -> None:
        dlg = ProductDialog(self.winfo_toplevel())
        self.wait_window(dlg)
        if dlg.result:
            self._products.append(dlg.result)
            self._refresh_tree()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selecione um produto", "Clique em um produto antes de editar.", parent=self.winfo_toplevel())
            return
        dlg = ProductDialog(self.winfo_toplevel(), product=self._products[idx])
        self.wait_window(dlg)
        if dlg.result:
            self._products[idx] = dlg.result
            self._refresh_tree()

    def _remove(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selecione um produto", "Clique em um produto antes de remover.", parent=self.winfo_toplevel())
            return
        name = self._products[idx].get("name", "?")
        if messagebox.askyesno("Confirmar remocao", f"Remover '{name}'?", parent=self.winfo_toplevel()):
            self._products.pop(idx)
            self._refresh_tree()

    def _move(self, direction: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(self._products):
            self._products[idx], self._products[new_idx] = self._products[new_idx], self._products[idx]
            self._refresh_tree()
            children = self._tree.get_children()
            if children:
                self._tree.selection_set(children[new_idx])

    def load(self, config: dict) -> None:
        self._products = [dict(p) for p in config.get("products", [])]
        self._refresh_tree()

    def flush(self, config: dict) -> None:
        config["products"] = self._products


# ─────────────────────────────────────────────────────────────────────────────

class StoresTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=16)
        self._store_map: dict = {}

        ttk.Label(
            self,
            text=(
                "O bot detecta a loja pela URL e usa um scraper dedicado (Camada 2).\n"
                "Adicione novas lojas para que sejam reconhecidas automaticamente."
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)

        cols = ("dominio", "scraper_id", "status")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", height=12)
        self._tree.heading("dominio",    text="Fragmento do Dominio")
        self._tree.heading("scraper_id", text="ID do Scraper")
        self._tree.heading("status",     text="Arquivo de Scraper")
        self._tree.column("dominio",    width=180, minwidth=120)
        self._tree.column("scraper_id", width=160, minwidth=100)
        self._tree.column("status",     width=160, minwidth=120)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(10, 0))
        self._btn_add      = ttk.Button(btn_frame, text="Adicionar",              command=self._add)
        self._btn_remove   = ttk.Button(btn_frame, text="Remover",                command=self._remove)
        self._btn_template = ttk.Button(btn_frame, text="Criar / Abrir Template", command=self._open_or_create_template)
        self._btn_add.pack(side="left", padx=(0, 4))
        self._btn_remove.pack(side="left", padx=4)
        self._btn_template.pack(side="left", padx=4)

        ttk.Label(
            self,
            text='Os scrapers builtin (Kabum, Pichau, Amazon, Terabyte) nao podem ser removidos aqui.',
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(8, 0))

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for domain, scraper_id in self._store_map.items():
            self._tree.insert("", "end", values=(domain, scraper_id, _scraper_status(scraper_id)))

    def _selected(self) -> Optional[tuple]:
        sel = self._tree.selection()
        if not sel:
            return None
        vals = self._tree.item(sel[0], "values")
        return vals[0], vals[1]

    def _on_select(self, _event=None) -> None:
        item = self._selected()
        if item:
            self._btn_remove.configure(state="disabled" if item[1] in _BUILTIN_SCRAPER_IDS else "normal")

    def _add(self) -> None:
        dlg = StoreDialog(self.winfo_toplevel(), existing_keys=set(self._store_map))
        self.wait_window(dlg)
        if dlg.result is None:
            return
        domain, scraper_id, create = dlg.result["domain"], dlg.result["scraper_id"], dlg.result["create_file"]
        self._store_map[domain] = scraper_id
        if create:
            dest = SCRAPERS_DIR / f"{scraper_id}.py"
            if dest.exists():
                messagebox.showinfo("Arquivo ja existe", f"{dest.name} ja existe.", parent=self.winfo_toplevel())
            else:
                try:
                    create_scraper_template(scraper_id)
                    self._refresh_tree()
                    ed = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
                    self.wait_window(ed)
                except Exception as exc:
                    messagebox.showwarning("Erro ao criar template", str(exc), parent=self.winfo_toplevel())
                return
        self._refresh_tree()

    def _remove(self) -> None:
        item = self._selected()
        if item is None:
            messagebox.showinfo("Selecione uma loja", "Clique em uma loja antes de remover.", parent=self.winfo_toplevel())
            return
        domain, scraper_id = item
        if scraper_id in _BUILTIN_SCRAPER_IDS:
            messagebox.showwarning("Loja builtin", f'"{domain}" e builtin e nao pode ser removida.', parent=self.winfo_toplevel())
            return
        if messagebox.askyesno("Confirmar remocao", f'Remover "{domain}" -> "{scraper_id}"?\nO arquivo .py NAO sera excluido.', parent=self.winfo_toplevel()):
            self._store_map.pop(domain, None)
            self._refresh_tree()

    def _open_or_create_template(self) -> None:
        item = self._selected()
        if item is None:
            messagebox.showinfo("Selecione uma loja", "Clique em uma loja primeiro.", parent=self.winfo_toplevel())
            return
        _domain, scraper_id = item
        dest = SCRAPERS_DIR / f"{scraper_id}.py"
        if dest.exists():
            ed = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
            self.wait_window(ed)
        else:
            if messagebox.askyesno("Arquivo nao encontrado", f"{dest.name} nao existe. Criar template?", parent=self.winfo_toplevel()):
                try:
                    create_scraper_template(scraper_id)
                    self._refresh_tree()
                    ed = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
                    self.wait_window(ed)
                except Exception as exc:
                    messagebox.showwarning("Erro", str(exc), parent=self.winfo_toplevel())

    def load(self, config: dict) -> None:
        self._store_map = dict(_BUILTIN_STORE_MAP)
        self._store_map.update(config.get("store_map", {}))
        self._refresh_tree()

    def flush(self, config: dict) -> None:
        save_store_map(self._store_map, config)


# ─────────────────────────────────────────────────────────────────────────────

class SearchTab(ttk.Frame):
    """
    Aba de busca por palavras-chave em múltiplas lojas.
    Exibe resultados em tempo real e permite salvar no Google Sheets.
    """

    _SOURCE_LABELS = [
        ("mercadolivre", "Mercado Livre"),
        ("zoom",         "Zoom"),
        ("kabum",        "KaBuM"),
        ("pichau",       "Pichau"),
        ("terabyte",     "Terabyte"),
        ("amazon",       "Amazon"),
    ]

    def __init__(self, parent, app: "App"):
        super().__init__(parent)
        self._app    = app
        self._offers: list[dict] = []
        self._lock   = __import__("threading").Lock()
        self._build()

    def _build(self) -> None:
        # ── Barra de busca ────────────────────────────────────────────────
        search_bar = tk.Frame(self, bg=BG, pady=10)
        search_bar.pack(fill="x", padx=16)

        tk.Label(search_bar, text="Produto:", font=FONT_LABEL, bg=BG, fg=FG).pack(side="left")
        self._query_var = tk.StringVar()
        self._query_entry = ttk.Entry(search_bar, textvariable=self._query_var, width=46)
        self._query_entry.pack(side="left", padx=(6, 8))
        self._query_entry.bind("<Return>", lambda _e: self._on_search())

        self._search_btn = tk.Button(
            search_bar, text="🔎  Buscar",
            bg=ACCENT, fg=FG_DARK, activebackground=ACCENT, activeforeground=FG_DARK,
            relief="flat", padx=14, pady=5, font=("Segoe UI", 10, "bold"),
            cursor="hand2", command=self._on_search,
        )
        self._search_btn.pack(side="left")

        # ── Filtros de preço ──────────────────────────────────────────────
        filters_bar = tk.Frame(self, bg=BG)
        filters_bar.pack(fill="x", padx=16, pady=(0, 4))

        for label, attr in [("Preço mín (R$):", "_min_price_var"), ("Preço máx (R$):", "_max_price_var")]:
            tk.Label(filters_bar, text=label, font=FONT_SMALL, bg=BG, fg=FG_DIM).pack(side="left")
            var = tk.StringVar()
            setattr(self, attr, var)
            ttk.Entry(filters_bar, textvariable=var, width=10).pack(side="left", padx=(4, 16))

        tk.Label(filters_bar, text="Max por fonte:", font=FONT_SMALL, bg=BG, fg=FG_DIM).pack(side="left")
        self._max_results_var = tk.StringVar(value="25")
        ttk.Entry(filters_bar, textvariable=self._max_results_var, width=6).pack(side="left", padx=(4, 16))

        # ── Fontes de busca ───────────────────────────────────────────────
        src_frame = tk.Frame(self, bg=BG, pady=4)
        src_frame.pack(fill="x", padx=16)
        tk.Label(src_frame, text="Fontes:", font=FONT_SMALL, bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 8))
        self._src_vars: dict[str, tk.BooleanVar] = {}
        for key, label in self._SOURCE_LABELS:
            var = tk.BooleanVar(value=True)
            self._src_vars[key] = var
            ttk.Checkbutton(src_frame, text=label, variable=var).pack(side="left", padx=4)

        # ── Progresso ─────────────────────────────────────────────────────
        self._progress_lbl = tk.Label(self, text="", font=FONT_SMALL, bg=BG, fg=FG_DIM)
        self._progress_lbl.pack(anchor="w", padx=16, pady=(4, 0))

        # ── Tabela de resultados ──────────────────────────────────────────
        tree_frame = tk.Frame(self, bg=BG)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        cols = ("produto", "loja", "preco", "fonte")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            selectmode="extended", height=16,
        )
        self._tree.heading("produto", text="Produto")
        self._tree.heading("loja",    text="Loja")
        self._tree.heading("preco",   text="Preço (R$)")
        self._tree.heading("fonte",   text="Fonte")
        self._tree.column("produto", width=380, minwidth=180)
        self._tree.column("loja",    width=140, minwidth=80)
        self._tree.column("preco",   width=110, minwidth=70, anchor="e")
        self._tree.column("fonte",   width=120, minwidth=70)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(side="left", fill="both", expand=True)

        # ── Rodapé da aba ─────────────────────────────────────────────────
        bottom = tk.Frame(self, bg=BG, pady=8)
        bottom.pack(fill="x", padx=16)

        self._result_lbl = tk.Label(bottom, text="", font=FONT_SMALL, bg=BG, fg=FG_DIM)
        self._result_lbl.pack(side="left")

        self._save_btn = tk.Button(
            bottom, text="💾  Salvar selecionados no Sheets",
            bg=BG_PANEL, fg=FG, activebackground=SEL_BG, activeforeground=FG,
            relief="flat", padx=14, pady=5, font=("Segoe UI", 9),
            cursor="hand2", command=self._on_save,
            state="disabled",
        )
        self._save_btn.pack(side="right")

        tk.Button(
            bottom, text="Selecionar todos",
            bg=BG_PANEL, fg=FG, activebackground=SEL_BG, activeforeground=FG,
            relief="flat", padx=10, pady=5, font=("Segoe UI", 9),
            cursor="hand2", command=lambda: self._tree.selection_set(self._tree.get_children()),
        ).pack(side="right", padx=8)

    # ── Busca ─────────────────────────────────────────────────────────────────

    def _on_search(self) -> None:
        query = self._query_var.get().strip()
        if not query:
            messagebox.showinfo("Campo vazio", "Digite o nome do produto para buscar.", parent=self.winfo_toplevel())
            return

        sources = [k for k, v in self._src_vars.items() if v.get()]
        if not sources:
            messagebox.showinfo("Sem fontes", "Selecione ao menos uma fonte de busca.", parent=self.winfo_toplevel())
            return

        try:
            max_results = int(self._max_results_var.get().strip() or "25")
        except ValueError:
            max_results = 25

        def _parse_price(s: str) -> Optional[float]:
            s = s.strip().replace(",", ".")
            try:
                return float(s) if s else None
            except ValueError:
                return None

        min_price = _parse_price(self._min_price_var.get())
        max_price = _parse_price(self._max_price_var.get())

        # Reset UI
        self._tree.delete(*self._tree.get_children())
        self._offers.clear()
        self._result_lbl.configure(text="Buscando...", fg=FG_DIM)
        self._search_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")

        n_sources   = len(sources)
        done_count  = [0]
        src_status: dict[str, str] = {}

        def _on_source_done(source_name: str, n_results: int, elapsed: float) -> None:
            with self._lock:
                done_count[0] += 1
                src_status[source_name] = f"{n_results} resultados ({elapsed:.1f}s)"
            status_text = "  ".join(f"{k}: {v}" for k, v in src_status.items())
            self.after(0, self._progress_lbl.configure, {"text": f"[{done_count[0]}/{n_sources}]  {status_text}"})

        def _worker() -> None:
            from price_tracker.search.aggregator import search as agg_search
            try:
                result = agg_search(
                    query,
                    max_results=max_results,
                    min_price=min_price,
                    max_price=max_price,
                    sources=sources,
                    on_source_done=_on_source_done,
                )
                offers = result.get("offers", [])
            except Exception as exc:
                offers = []
                self.after(0, messagebox.showerror, "Erro na busca", str(exc))
            self.after(0, self._populate_results, offers, query)

        __import__("threading").Thread(target=_worker, daemon=True).start()

    def _populate_results(self, offers: list[dict], query: str) -> None:
        self._offers = offers
        self._tree.delete(*self._tree.get_children())

        for offer in offers:
            price = offer.get("price")
            price_fmt = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if price is not None else ""
            self._tree.insert("", "end", values=(
                offer.get("name",   ""),
                offer.get("store",  ""),
                price_fmt,
                offer.get("source", ""),
            ))

        total = len(offers)
        self._result_lbl.configure(
            text=f"{total} oferta(s) encontrada(s) para \"{query}\"",
            fg=SUCCESS if total > 0 else WARNING,
        )
        self._search_btn.configure(state="normal")
        self._save_btn.configure(state="normal" if total > 0 else "disabled")
        self._app.set_status(f"Busca concluída: {total} resultado(s)", SUCCESS if total > 0 else FG_DIM)

    # ── Salvar no Sheets ──────────────────────────────────────────────────────

    def _on_save(self) -> None:
        sel_indices = [self._tree.index(iid) for iid in self._tree.selection()]
        if not sel_indices:
            # If nothing selected, save all
            sel_indices = list(range(len(self._offers)))

        to_save = [self._offers[i] for i in sel_indices if i < len(self._offers)]
        if not to_save:
            messagebox.showinfo("Nada selecionado", "Selecione as ofertas que deseja salvar.", parent=self.winfo_toplevel())
            return

        cfg = load_config()
        gs_cfg = cfg.get("google_sheets", {})
        creds_file  = gs_cfg.get("credentials_file", "credentials.json")
        sheet_name  = gs_cfg.get("spreadsheet_name", "Price Tracker")

        if not creds_file or not sheet_name:
            messagebox.showwarning(
                "Configuração incompleta",
                "Configure o arquivo de credenciais e o nome da planilha na aba Configurações.",
                parent=self.winfo_toplevel(),
            )
            return

        self._save_btn.configure(state="disabled", text="Salvando...")
        self._app.set_status("Salvando no Google Sheets...", WARNING)

        def _worker() -> None:
            try:
                from sheets import connect_to_sheets, append_search_results
                creds_path = BASE_DIR / creds_file
                sheet = connect_to_sheets(str(creds_path), sheet_name)
                written = append_search_results(sheet, to_save)
                self.after(0, self._after_save, written, None)
            except Exception as exc:
                self.after(0, self._after_save, 0, exc)

        __import__("threading").Thread(target=_worker, daemon=True).start()

    def _after_save(self, written: int, error: Optional[Exception]) -> None:
        self._save_btn.configure(state="normal", text="💾  Salvar selecionados no Sheets")
        if error:
            messagebox.showerror("Erro ao salvar", str(error), parent=self.winfo_toplevel())
            self._app.set_status("Erro ao salvar no Sheets.", ERROR_C)
        else:
            msg = f"{written} linha(s) gravada(s) na planilha."
            messagebox.showinfo("Salvo!", msg, parent=self.winfo_toplevel())
            self._app.set_status(msg, SUCCESS)


# =============================================================================
# Janela principal
# =============================================================================

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Price Checker Bot")
        self.geometry("1080x720")
        self.minsize(800, 560)
        self.configure(bg=BG)
        self.resizable(True, True)

        _ico = BASE_DIR / "icon.ico"
        if _ico.exists():
            try:
                self.iconbitmap(str(_ico))
            except Exception:
                pass

        self._log_queue: queue.Queue = queue.Queue()
        self._config: dict = load_config()

        self._apply_theme()
        self._build_ui()
        self._poll_queue()

    # ── Tema ttk ─────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("App.Horizontal.TProgressbar",
                    troughcolor=BG_PANEL, background=ACCENT,
                    bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=14)

        s.configure("TNotebook",     background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        s.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG_DIM,
                    padding=[16, 7], font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", FG)])

        s.configure("TFrame",          background=BG)
        s.configure("TLabelframe",     background=BG, foreground=FG, bordercolor=BG_PANEL)
        s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        s.configure("TLabel",          background=BG, foreground=FG, font=FONT_LABEL)
        s.configure("TCheckbutton",    background=BG, foreground=FG, font=FONT_LABEL)
        s.map("TCheckbutton",          background=[("active", BG)])
        s.configure("TEntry",
                    fieldbackground=BG_INPUT, foreground=FG,
                    insertcolor=FG, bordercolor=BG_PANEL, relief="flat", padding=4)
        s.configure("TButton",
                    background=BG_PANEL, foreground=FG,
                    borderwidth=0, relief="flat", font=FONT_LABEL, padding=[10, 5])
        s.map("TButton",
              background=[("active", SEL_BG), ("pressed", SEL_BG)],
              foreground=[("active", FG)])
        s.configure("Treeview",
                    background=BG_INPUT, foreground=FG,
                    fieldbackground=BG_INPUT, borderwidth=0, font=FONT_LABEL, rowheight=22)
        s.configure("Treeview.Heading",
                    background=BG_PANEL, foreground=ACCENT,
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", FG_DARK)])
        s.configure("TScrollbar",
                    background=BG_PANEL, troughcolor=BG_INPUT,
                    arrowcolor=FG_DIM, bordercolor=BG)

    # ── Construção da UI ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Cabeçalho
        hdr = tk.Frame(self, bg=BG_PANEL, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Price Checker Bot", font=FONT_TITLE, bg=BG_PANEL, fg=ACCENT).pack(side="left", padx=20)
        self._hdr_status = tk.Label(hdr, text="Pronto", font=FONT_SMALL, bg=BG_PANEL, fg=FG_DIM)
        self._hdr_status.pack(side="right", padx=20)

        # Notebook
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)

        self._monitor_tab  = MonitorTab(self._nb, app=self)
        self._general_tab  = GeneralTab(self._nb)
        self._products_tab = ProductsTab(self._nb)
        self._stores_tab   = StoresTab(self._nb)
        self._search_tab   = SearchTab(self._nb, app=self)

        self._nb.add(self._monitor_tab,  text="  Monitoramento  ")
        self._nb.add(self._general_tab,  text="  Configuracoes  ")
        self._nb.add(self._products_tab, text="  Produtos  ")
        self._nb.add(self._stores_tab,   text="  Lojas  ")
        self._nb.add(self._search_tab,   text="  Busca  ")

        self._monitor_tab.setup_logging(self._log_queue)
        self._load_config_tabs()
        self._monitor_tab.refresh_info()

        # Rodapé
        footer = tk.Frame(self, bg=BG_PANEL, pady=5)
        footer.pack(fill="x", side="bottom")

        self._save_btn = tk.Button(
            footer, text="  Salvar Configuracoes",
            bg=ACCENT, fg=FG_DARK, activebackground=ACCENT, activeforeground=FG_DARK,
            relief="flat", padx=14, pady=4, font=("Segoe UI", 9, "bold"),
            cursor="hand2", command=self._save_config,
        )
        self._reload_btn = tk.Button(
            footer, text="  Recarregar",
            bg=BG_PANEL, fg=FG, activebackground=SEL_BG, activeforeground=FG,
            relief="flat", padx=14, pady=4, font=("Segoe UI", 9),
            cursor="hand2", command=self._reload_config,
        )

        self._footer_status = tk.Label(footer, text="Pronto.", font=FONT_SMALL, bg=BG_PANEL, fg=FG_DIM)
        self._footer_status.pack(side="left", padx=12)

        self._footer_time = tk.Label(footer, text="", font=FONT_SMALL, bg=BG_PANEL, fg=FG_DIM)
        self._footer_time.pack(side="right", padx=12)
        self._tick_clock()

        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_change)
        self._update_footer_btns()

    # ── Relógio ───────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        self._footer_time.configure(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ── Controle do rodapé (Salvar/Recarregar) ────────────────────────────────

    def _on_tab_change(self, _event=None) -> None:
        self._update_footer_btns()

    def _update_footer_btns(self) -> None:
        try:
            idx = self._nb.index(self._nb.select())
        except Exception:
            idx = 0
        # Only show Salvar/Recarregar on config tabs (Configuracoes, Produtos, Lojas)
        if idx in (0, 4):
            # Monitoramento and Busca — operational tabs, no config saving needed
            self._save_btn.pack_forget()
            self._reload_btn.pack_forget()
        else:
            self._save_btn.pack(side="right", padx=(6, 10))
            self._reload_btn.pack(side="right")

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config_tabs(self) -> None:
        self._general_tab.load(self._config)
        self._products_tab.load(self._config)
        self._stores_tab.load(self._config)

    def _save_config(self) -> None:
        self._general_tab.flush(self._config)
        self._products_tab.flush(self._config)

        gs = self._config.get("google_sheets", {})
        if not gs.get("credentials_file", "").strip():
            messagebox.showwarning("Campo obrigatorio", "Informe o arquivo de credenciais do Google.")
            return
        if not gs.get("spreadsheet_name", "").strip():
            messagebox.showwarning("Campo obrigatorio", "Informe o nome da planilha.")
            return

        self._stores_tab.flush(self._config)
        save_config(self._config)
        self.set_status("Configuracoes salvas.", SUCCESS)
        self._monitor_tab.refresh_info()
        messagebox.showinfo("Salvo!", f"config.json atualizado.\n\n{CONFIG_PATH}")

    def _reload_config(self) -> None:
        if messagebox.askyesno("Recarregar", "Descartar alteracoes e recarregar o config.json?"):
            self._config = load_config()
            self._load_config_tabs()
            self.set_status("Configuracao recarregada.", FG_DIM)

    # ── Status público ────────────────────────────────────────────────────────

    def set_status(self, text: str, color: str = FG_DIM) -> None:
        self._hdr_status.configure(text=text, fg=color)
        self._footer_status.configure(text=text)

    # ── Polling da fila de logs ───────────────────────────────────────────────

    def _poll_queue(self) -> None:
        for _ in range(50):
            try:
                self._monitor_tab.write_log(self._log_queue.get_nowait())
            except queue.Empty:
                break
        self.after(80, self._poll_queue)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
