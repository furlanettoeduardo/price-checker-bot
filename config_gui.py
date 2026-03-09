"""
config_gui.py
-------------
Interface gráfica (Tkinter) para configurar o bot sem editar o config.json
diretamente. Execute com:

    python config_gui.py

A janela possui três abas:
  • Configurações Gerais — Google Sheets e Telegram
  • Produtos            — Adicionar / Editar / Remover produtos
  • Lojas               — Gerenciar mapeamento de lojas e scrapers
"""

import ast
import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

CONFIG_PATH         = Path(__file__).parent / "config.json"
STORE_DETECTOR_PATH = Path(__file__).parent / "price_tracker" / "core" / "store_detector.py"
SCRAPERS_DIR        = Path(__file__).parent / "price_tracker" / "scrapers"

# IDs dos scrapers que já vêm com o projeto
_BUILTIN_SCRAPER_IDS = {"kabum", "pichau", "amazon", "terabyte"}

# Template gerado ao criar scraper de nova loja
_SCRAPER_TEMPLATE = """\
\"\"\"
scrapers/{sid}.py
{dash}
Scraper específico para {sid}.

Personalize os seletores CSS abaixo com os elementos de preço da loja.
Dica: abra a página do produto, clique com o botão direito no preço
→ "Inspecionar" para descobrir as classes / IDs corretos.
\"\"\"

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

# Seletores CSS em ordem de prioridade (mais estável → menos estável).
# Substitua pelos seletores reais da loja.
_SELECTORS: list[str] = [
    # ".preco-produto",
    # "[data-testid='price']",
    # "#valorProduto span",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    \"\"\"
    Extrai o preço à vista de uma página de {sid}.

    Retorna
    -------
    {{"price": float, "currency": "BRL", "confidence": float}}
    ou None se nenhum seletor retornar preço válido.
    \"\"\"
    for selector in _SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)
            if price is not None:
                logger.info(f"[{sid}] Preço R$ {{price:.2f}} — seletor: '{{selector}}'")
                return {{"price": price, "currency": "BRL", "confidence": 0.88}}
        except Exception as exc:
            logger.debug(f"[{sid}] Erro no seletor '{{selector}}': {{exc}}")

    logger.warning("[{sid}] Nenhum seletor retornou preço válido.")
    return None
"""

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de I/O — config.json
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de I/O — store_detector.py (STORE_MAP)
# ──────────────────────────────────────────────────────────────────────────────

def load_store_map() -> dict[str, str]:
    """Lê STORE_MAP do store_detector.py usando ast.literal_eval."""
    if not STORE_DETECTOR_PATH.exists():
        return {}
    text = STORE_DETECTOR_PATH.read_text(encoding="utf-8")
    m = re.search(r'STORE_MAP\s*:\s*dict\[.*?\]\s*=\s*(\{[^}]+\})', text, re.DOTALL)
    if not m:
        return {}
    try:
        return ast.literal_eval(m.group(1))
    except Exception:
        return {}


def save_store_map(store_map: dict[str, str]) -> None:
    """Escreve STORE_MAP atualizado de volta no store_detector.py."""
    text = STORE_DETECTOR_PATH.read_text(encoding="utf-8")
    lines = []
    for k, v in store_map.items():
        pad = " " * max(1, 16 - len(k))
        lines.append(f'    "{k}":{pad}"{v}",')
    new_block = "{\n" + "\n".join(lines) + "\n}"
    new_text = re.sub(
        r'(STORE_MAP\s*:\s*dict\[.*?\]\s*=\s*)\{[^}]+\}',
        lambda m: m.group(1) + new_block,
        text,
        flags=re.DOTALL,
    )
    STORE_DETECTOR_PATH.write_text(new_text, encoding="utf-8")


def create_scraper_template(store_id: str) -> Path:
    """Cria price_tracker/scrapers/<store_id>.py com o template padrão."""
    dest = SCRAPERS_DIR / f"{store_id}.py"
    dash = "-" * (len(f"scrapers/{store_id}.py") + 1)
    content = _SCRAPER_TEMPLATE.format(sid=store_id, dash=dash)
    dest.write_text(content, encoding="utf-8")
    return dest


def _scraper_status(scraper_id: str) -> str:
    py_file = SCRAPERS_DIR / f"{scraper_id}.py"
    if py_file.exists():
        return "✅ Builtin" if scraper_id in _BUILTIN_SCRAPER_IDS else "📁 Personalizado"
    return "⚠️ Sem arquivo"


def _read_scraper_selectors(path: Path) -> list[str]:
    """Extrai a lista _SELECTORS (não comentada) de um arquivo de scraper."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r'_SELECTORS\s*(?::\s*list\[str\])?\s*=\s*\[(.*?)\]', text, re.DOTALL)
    if not m:
        return []
    selectors: list[str] = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m2 = re.match(r'^["\'](.+?)["\'],?\s*$', stripped)
        if m2:
            selectors.append(m2.group(1))
    return selectors


def _write_scraper_selectors(path: Path, selectors: list[str]) -> None:
    """Substitui o bloco _SELECTORS no arquivo de scraper preservando o restante."""
    text = path.read_text(encoding="utf-8")
    if selectors:
        inner = "\n".join(f'    "{s}",' for s in selectors)
        new_block = f"[\n{inner}\n]"
    else:
        new_block = "[]"
    new_text = re.sub(
        r'(_SELECTORS\s*(?::\s*list\[str\])?\s*=\s*)\[.*?\]',
        lambda mo: mo.group(1) + new_block,
        text,
        flags=re.DOTALL,
    )
    path.write_text(new_text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo de edição de scraper (seletores CSS)
# ──────────────────────────────────────────────────────────────────────────────

class ScraperEditorDialog(tk.Toplevel):
    """Janela modal para editar os seletores CSS de um scraper."""

    def __init__(self, parent, scraper_id: str, path: Path):
        super().__init__(parent)
        self.title(f"Editar Scraper — {scraper_id}")
        self.resizable(True, True)
        self.minsize(520, 380)
        self.grab_set()
        self._path = path

        # ── Arquivo ───────────────────────────────────────────────────────
        hdr = ttk.LabelFrame(self, text="Arquivo", padding=8)
        hdr.pack(fill="x", padx=12, pady=(12, 4))
        try:
            rel = path.relative_to(Path(__file__).parent)
        except ValueError:
            rel = path
        ttk.Label(hdr, text=str(rel), foreground="#555").pack(anchor="w")

        # ── Seletores CSS ─────────────────────────────────────────────────
        sel_frame = ttk.LabelFrame(
            self,
            text="Seletores CSS (um por linha, do mais ao menos específico)",
            padding=10,
        )
        sel_frame.pack(fill="both", expand=True, padx=12, pady=4)

        self._sel_text = tk.Text(sel_frame, width=64, height=10, font=("Consolas", 10))
        vsb = ttk.Scrollbar(sel_frame, command=self._sel_text.yview)
        self._sel_text.configure(yscrollcommand=vsb.set)
        self._sel_text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        selectors = _read_scraper_selectors(path)
        if selectors:
            self._sel_text.insert("1.0", "\n".join(selectors))

        # ── Dica ──────────────────────────────────────────────────────────
        ttk.Label(
            self,
            text=(
                "\u2139\ufe0f  O bot testa cada seletor em ordem até encontrar um preço válido.\n"
                "   Deixe em branco para depender apenas de JSON-LD e heurística automática."
            ),
            foreground="#555",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        # ── Botões ────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Salvar", command=self._save).pack(side="right")

        self._center(parent)

    def _save(self) -> None:
        raw = self._sel_text.get("1.0", "end").strip()
        selectors = [s.strip() for s in raw.splitlines() if s.strip()]
        try:
            _write_scraper_selectors(self._path, selectors)
            self.destroy()
        except Exception as exc:
            messagebox.showwarning(
                "Erro ao salvar",
                f"Não foi possível salvar o arquivo:\n{exc}",
                parent=self,
            )

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de auto-preenchimento de nome/loja (espelham main.py)
# ──────────────────────────────────────────────────────────────────────────────

def _gui_auto_name(url: str) -> str:
    """Gera um nome legível a partir do último segmento do path da URL."""
    try:
        from urllib.parse import urlparse
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            slug = parts[-1].replace("-", " ").replace("_", " ").strip()
            if slug and not slug.isdigit():
                return slug[:80].title()
        host = urlparse(url).netloc.lstrip("www.").split(".")[0]
        return host.title()
    except Exception:
        return "Produto"


def _gui_auto_store(url: str) -> str:
    """Infere o nome da loja a partir do domínio da URL."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lstrip("www.").split(".")[0]
        return host.title()
    except Exception:
        return "?"


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo de Produto (Adicionar / Editar)
# ──────────────────────────────────────────────────────────────────────────────

class ProductDialog(tk.Toplevel):
    """Janela modal para criar ou editar um produto."""

    def __init__(self, parent, product: dict | None = None):
        super().__init__(parent)
        self.title("Produto" if product is None else "Editar Produto")
        self.resizable(False, False)
        self.grab_set()  # modal
        self.result: dict | None = None

        pad = {"padx": 8, "pady": 4}

        # ── Campos básicos ────────────────────────────────────────────────
        fields_frame = ttk.LabelFrame(self, text="Dados do Produto", padding=10)
        fields_frame.pack(fill="x", padx=12, pady=(12, 4))

        # (opcional) aparece em cinza no placeholder
        labels = [
            "Nome do produto (opcional):",
            "Loja (opcional):",
            "URL da página:",
        ]
        self._entries: list[ttk.Entry] = []
        for row, label in enumerate(labels):
            ttk.Label(fields_frame, text=label).grid(row=row, column=0, sticky="w", **pad)
            entry = ttk.Entry(fields_frame, width=55)
            entry.grid(row=row, column=1, sticky="ew", **pad)
            self._entries.append(entry)
        fields_frame.columnconfigure(1, weight=1)

        self._name_entry, self._store_entry, self._url_entry = self._entries

        # Auto-preenche loja quando a URL perde foco
        self._url_entry.bind("<FocusOut>", self._auto_fill_store)

        # Nota sobre campos opcionais
        ttk.Label(
            fields_frame,
            text="ℹ️  Nome e Loja são opcionais: se omitidos, o bot preenche automaticamente pela URL.",
            foreground="#666",
            font=("TkDefaultFont", 8),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 2))

        # ── Seletores CSS ────────────────────────────────────────────────
        sel_frame = ttk.LabelFrame(self, text="Seletores CSS — opcionais (um por linha, do mais ao menos específico)", padding=10)
        sel_frame.pack(fill="both", expand=True, padx=12, pady=4)

        hint = (
            "ℹ️  A extração usa 4 camadas em sequência:\n"
            "  1. JSON-LD (dados estruturados da página)\n"
            "  2. Scraper dedicado da loja (Kabum, Pichau, Amazon, Terabyte)\n"
            "  3. Seletores CSS abaixo (se informados)\n"
            "  4. Heurística automática — fallback final"
        )
        ttk.Label(sel_frame, text=hint, justify="left", foreground="#555").pack(
            anchor="w", padx=4, pady=(0, 6)
        )

        self._sel_text = tk.Text(sel_frame, width=60, height=7, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(sel_frame, command=self._sel_text.yview)
        self._sel_text.configure(yscrollcommand=scrollbar.set)
        self._sel_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


        if product:
            self._name_entry.insert(0, product.get("name", ""))
            self._store_entry.insert(0, product.get("store", ""))
            self._url_entry.insert(0, product.get("url", ""))
            selectors = product.get("price_selectors", [])
            self._sel_text.insert("1.0", "\n".join(selectors))

        # ── Botões ───────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Salvar", command=self._save).pack(side="right")

        self._center(parent)

    def _auto_fill_store(self, _event=None) -> None:
        """Preenche o campo Loja automaticamente a partir do domínio da URL, se vazio."""
        if self._store_entry.get().strip():
            return  # Usuário já preencheu manualmente
        url = self._url_entry.get().strip()
        if not url:
            return
        store = _gui_auto_store(url)
        if store and store != "?":
            self._store_entry.insert(0, store)

    def _save(self) -> None:
        name = self._name_entry.get().strip()
        store = self._store_entry.get().strip()
        url = self._url_entry.get().strip()
        raw_selectors = self._sel_text.get("1.0", "end").strip()
        selectors = [s.strip() for s in raw_selectors.splitlines() if s.strip()]

        if not url:
            messagebox.showwarning("Campo obrigatório", "Informe a URL do produto.", parent=self)
            return

        # Auto-preenche nome e loja se não informados, usando a mesma lógica do main.py
        if not name:
            name = _gui_auto_name(url)
        if not store:
            store = _gui_auto_store(url)

        result: dict = {"url": url, "name": name, "store": store}
        if selectors:
            result["price_selectors"] = selectors
        self.result = result
        self.destroy()

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")


# ──────────────────────────────────────────────────────────────────────────────
# Aba — Configurações Gerais
# ──────────────────────────────────────────────────────────────────────────────

class GeneralTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        # ── Google Sheets ────────────────────────────────────────────────
        gs_frame = ttk.LabelFrame(self, text="Google Sheets", padding=10)
        gs_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(gs_frame, text="Arquivo de credenciais:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.creds_var = tk.StringVar()
        ttk.Entry(gs_frame, textvariable=self.creds_var, width=50).grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(gs_frame, text="Nome da planilha:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.sheet_var = tk.StringVar()
        ttk.Entry(gs_frame, textvariable=self.sheet_var, width=50).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        gs_frame.columnconfigure(1, weight=1)

        # ── Telegram ─────────────────────────────────────────────────────
        tg_frame = ttk.LabelFrame(self, text="Telegram (opcional)", padding=10)
        tg_frame.pack(fill="x")

        self.tg_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(
            tg_frame, text="Ativar alertas Telegram", variable=self.tg_enabled_var
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        ttk.Label(tg_frame, text="Bot Token:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.tg_token_var = tk.StringVar()
        ttk.Entry(tg_frame, textvariable=self.tg_token_var, width=50, show="").grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(tg_frame, text="Chat ID:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.tg_chat_var = tk.StringVar()
        ttk.Entry(tg_frame, textvariable=self.tg_chat_var, width=50).grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        self.tg_low_var = tk.BooleanVar()
        ttk.Checkbutton(
            tg_frame, text="Alertar ao atingir novo mínimo histórico", variable=self.tg_low_var
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4)
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
            "enabled": self.tg_enabled_var.get(),
            "bot_token": self.tg_token_var.get().strip(),
            "chat_id": self.tg_chat_var.get().strip(),
            "alert_on_new_low": self.tg_low_var.get(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Aba — Produtos
# ──────────────────────────────────────────────────────────────────────────────

class ProductsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._products: list[dict] = []

        # ── Tabela de produtos ───────────────────────────────────────────
        cols = ("nome", "loja", "seletores")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse", height=14)
        self._tree.heading("nome", text="Produto")
        self._tree.heading("loja", text="Loja")
        self._tree.heading("seletores", text="Seletores CSS")
        self._tree.column("nome", width=220, minwidth=140)
        self._tree.column("loja", width=110, minwidth=80)
        self._tree.column("seletores", width=300, minwidth=160)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<Double-1>", lambda _e: self._edit())

        # ── Botões ───────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Button(btn_frame, text="➕  Adicionar", command=self._add).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="✏️  Editar", command=self._edit).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️  Remover", command=self._remove).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="⬆  Mover acima", command=lambda: self._move(-1)).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="⬇  Mover abaixo", command=lambda: self._move(1)).pack(side="left", padx=4)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    # ── Helpers internos ─────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for p in self._products:
            sels = ", ".join(p.get("price_selectors", []))
            self._tree.insert("", "end", values=(p.get("name", ""), p.get("store", ""), sels))

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.index(sel[0])

    def _add(self) -> None:
        dlg = ProductDialog(self.winfo_toplevel())
        self.wait_window(dlg)
        if dlg.result:
            self._products.append(dlg.result)
            self._refresh_tree()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selecione um produto", "Clique em um produto na lista antes de editar.", parent=self.winfo_toplevel())
            return
        dlg = ProductDialog(self.winfo_toplevel(), product=self._products[idx])
        self.wait_window(dlg)
        if dlg.result:
            self._products[idx] = dlg.result
            self._refresh_tree()

    def _remove(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selecione um produto", "Clique em um produto na lista antes de remover.", parent=self.winfo_toplevel())
            return
        name = self._products[idx].get("name", "?")
        if messagebox.askyesno("Confirmar remoção", f"Remover '{name}'?", parent=self.winfo_toplevel()):
            self._products.pop(idx)
            self._refresh_tree()

    def _move(self, direction: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._products):
            return
        self._products[idx], self._products[new_idx] = self._products[new_idx], self._products[idx]
        self._refresh_tree()
        # Re-seleciona o item na nova posição
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children[new_idx])

    # ── API pública ──────────────────────────────────────────────────────

    def load(self, config: dict) -> None:
        self._products = [dict(p) for p in config.get("products", [])]
        self._refresh_tree()

    def flush(self, config: dict) -> None:
        config["products"] = self._products


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo de Nova Loja
# ──────────────────────────────────────────────────────────────────────────────

class StoreDialog(tk.Toplevel):
    """Janela modal para cadastrar uma nova loja no STORE_MAP."""

    def __init__(self, parent, existing_keys: set[str]):
        super().__init__(parent)
        self.title("Adicionar Loja")
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None
        self._existing = existing_keys

        pad = {"padx": 8, "pady": 5}

        fields_frame = ttk.LabelFrame(self, text="Mapeamento de Domínio", padding=12)
        fields_frame.pack(fill="x", padx=12, pady=(12, 4))

        # Domínio
        ttk.Label(fields_frame, text="Domínio da loja:").grid(
            row=0, column=0, sticky="w", **pad
        )
        self._domain_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self._domain_var, width=30).grid(
            row=0, column=1, sticky="ew", **pad
        )
        ttk.Label(
            fields_frame,
            text='Ex: "americanas" para americanas.com.br',
            foreground="#666",
            font=("TkDefaultFont", 8),
        ).grid(row=1, column=1, sticky="w", padx=8)

        # ID do scraper
        ttk.Label(fields_frame, text="ID do scraper:").grid(
            row=2, column=0, sticky="w", **pad
        )
        self._id_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self._id_var, width=30).grid(
            row=2, column=1, sticky="ew", **pad
        )
        ttk.Label(
            fields_frame,
            text='Nome do arquivo em price_tracker/scrapers/ (sem ".py")',
            foreground="#666",
            font=("TkDefaultFont", 8),
        ).grid(row=3, column=1, sticky="w", padx=8)
        fields_frame.columnconfigure(1, weight=1)

        # Preencher ID automaticamente quando o domínio é digitado
        self._domain_var.trace_add("write", self._auto_fill_id)

        # Opção de criar template
        opt_frame = ttk.Frame(self, padding=(12, 4))
        opt_frame.pack(fill="x")
        self._create_file_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text="Criar arquivo de scraper template  (price_tracker/scrapers/<id>.py)",
            variable=self._create_file_var,
        ).pack(anchor="w")

        # Botões
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Adicionar", command=self._save).pack(side="right")

        self._center(parent)

    def _auto_fill_id(self, *_) -> None:
        # Só preenche automaticamente se o usuário não tocou no campo ID
        domain = self._domain_var.get().strip().lower()
        # Sanitiza: apenas letras, dígitos, underscore, hífen
        safe = re.sub(r"[^a-z0-9_-]", "", domain)
        # Só preenche se o campo ainda está vazio ou igual ao último auto-fill
        current = self._id_var.get().strip()
        if not current or current == getattr(self, "_last_auto", ""):
            self._id_var.set(safe)
            self._last_auto = safe

    def _save(self) -> None:
        domain = self._domain_var.get().strip().lower()
        scraper_id = self._id_var.get().strip().lower()

        if not domain:
            messagebox.showwarning("Campo obrigatório", "Informe o domínio da loja.", parent=self)
            return
        if not scraper_id:
            messagebox.showwarning("Campo obrigatório", "Informe o ID do scraper.", parent=self)
            return
        if domain in self._existing:
            messagebox.showwarning(
                "Domínio duplicado",
                f'O domínio "{domain}" já existe no mapeamento.',
                parent=self,
            )
            return

        self.result = {
            "domain": domain,
            "scraper_id": scraper_id,
            "create_file": self._create_file_var.get(),
        }
        self.destroy()

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")


# ──────────────────────────────────────────────────────────────────────────────
# Aba — Lojas
# ──────────────────────────────────────────────────────────────────────────────

class StoresTab(ttk.Frame):
    """
    Gerencia o STORE_MAP definido em price_tracker/core/store_detector.py.
    Permite adicionar novos domínios e criar templates de scraper.
    """

    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._store_map: dict[str, str] = {}

        # ── Descrição ────────────────────────────────────────────────────
        info = (
            "O bot detecta a loja pela URL e usa um scraper dedicado (Camada 2).\n"
            "Adicione novas lojas aqui para que sejam reconhecidas automaticamente."
        )
        ttk.Label(self, text=info, foreground="#444", justify="left").pack(
            anchor="w", pady=(0, 8)
        )

        # ── Tabela + scrollbar num frame próprio ──────────────────────────
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)

        cols = ("dominio", "scraper_id", "status")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="browse", height=12
        )
        self._tree.heading("dominio",    text="Fragmento do Domínio")
        self._tree.heading("scraper_id", text="ID do Scraper")
        self._tree.heading("status",     text="Arquivo de Scraper")
        self._tree.column("dominio",    width=180, minwidth=120)
        self._tree.column("scraper_id", width=160, minwidth=100)
        self._tree.column("status",     width=160, minwidth=120)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # ── Botões ────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(8, 0))

        self._btn_add      = ttk.Button(btn_frame, text="➕  Adicionar",             command=self._add)
        self._btn_remove   = ttk.Button(btn_frame, text="🗑️  Remover",               command=self._remove)
        self._btn_template = ttk.Button(btn_frame, text="📄  Criar / Abrir Template", command=self._open_or_create_template)

        self._btn_add.pack(side="left", padx=(0, 4))
        self._btn_remove.pack(side="left", padx=4)
        self._btn_template.pack(side="left", padx=4)

        # ── Nota inferior ─────────────────────────────────────────────────
        note = (
            "Após adicionar, edite o arquivo .py gerado e preencha os seletores CSS.\n"
            'Os "builtins" (Kabum, Pichau, Amazon, Terabyte) não podem ser removidos aqui.'
        )
        ttk.Label(self, text=note, foreground="#888", font=("TkDefaultFont", 8)).pack(
            anchor="w", pady=(6, 0)
        )

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    # ── Internos ─────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for domain, scraper_id in self._store_map.items():
            status = _scraper_status(scraper_id)
            self._tree.insert("", "end", values=(domain, scraper_id, status))

    def _selected(self) -> tuple[str, str] | None:
        """Retorna (domain, scraper_id) do item selecionado, ou None."""
        sel = self._tree.selection()
        if not sel:
            return None
        vals = self._tree.item(sel[0], "values")
        return vals[0], vals[1]

    def _on_select(self, _event=None) -> None:
        item = self._selected()
        if item is None:
            return
        _domain, scraper_id = item
        # Não permite remover builtins
        is_builtin = scraper_id in _BUILTIN_SCRAPER_IDS
        self._btn_remove.configure(state="disabled" if is_builtin else "normal")

    def _add(self) -> None:
        dlg = StoreDialog(self.winfo_toplevel(), existing_keys=set(self._store_map))
        self.wait_window(dlg)
        if dlg.result is None:
            return

        domain     = dlg.result["domain"]
        scraper_id = dlg.result["scraper_id"]
        create     = dlg.result["create_file"]

        self._store_map[domain] = scraper_id

        if create:
            dest = SCRAPERS_DIR / f"{scraper_id}.py"
            if dest.exists():
                messagebox.showinfo(
                    "Arquivo já existe",
                    f"O arquivo {dest.name} já existe e não foi substituído.",
                    parent=self.winfo_toplevel(),
                )
            else:
                try:
                    create_scraper_template(scraper_id)
                    self._refresh_tree()
                    dlg = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
                    self.wait_window(dlg)
                except Exception as exc:
                    messagebox.showwarning(
                        "Erro ao criar template",
                        f"Não foi possível criar o arquivo:\n{exc}",
                        parent=self.winfo_toplevel(),
                    )
                return

        self._refresh_tree()

    def _remove(self) -> None:
        item = self._selected()
        if item is None:
            messagebox.showinfo(
                "Selecione uma loja",
                "Clique em uma loja na lista antes de remover.",
                parent=self.winfo_toplevel(),
            )
            return
        domain, scraper_id = item
        if scraper_id in _BUILTIN_SCRAPER_IDS:
            messagebox.showwarning(
                "Loja builtin",
                f'"{domain}" é uma loja builtin e não pode ser removida aqui.',
                parent=self.winfo_toplevel(),
            )
            return
        if messagebox.askyesno(
            "Confirmar remoção",
            f'Remover o domínio "{domain}" → "{scraper_id}" do mapeamento?\n\n'
            "O arquivo .py do scraper NÃO será excluído.",
            parent=self.winfo_toplevel(),
        ):
            self._store_map.pop(domain, None)
            self._refresh_tree()

    def _open_or_create_template(self) -> None:
        item = self._selected()
        if item is None:
            messagebox.showinfo(
                "Selecione uma loja",
                "Clique em uma loja na lista primeiro.",
                parent=self.winfo_toplevel(),
            )
            return
        _domain, scraper_id = item
        dest = SCRAPERS_DIR / f"{scraper_id}.py"
        if dest.exists():
            dlg = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
            self.wait_window(dlg)
        else:
            if messagebox.askyesno(
                "Arquivo não encontrado",
                f"{dest.name} ainda não existe.\nCriar template agora?",
                parent=self.winfo_toplevel(),
            ):
                try:
                    create_scraper_template(scraper_id)
                    self._refresh_tree()
                    dlg = ScraperEditorDialog(self.winfo_toplevel(), scraper_id, dest)
                    self.wait_window(dlg)
                except Exception as exc:
                    messagebox.showwarning("Erro", str(exc), parent=self.winfo_toplevel())

    # ── API pública ───────────────────────────────────────────────────────

    def load(self) -> None:
        self._store_map = load_store_map()
        self._refresh_tree()

    def flush(self) -> None:
        """Salva STORE_MAP em store_detector.py (independente do config.json)."""
        if not STORE_DETECTOR_PATH.exists():
            messagebox.showwarning(
                "Arquivo não encontrado",
                f"Não foi possível salvar: {STORE_DETECTOR_PATH} não existe.",
            )
            return
        save_store_map(self._store_map)


# ──────────────────────────────────────────────────────────────────────────────
# Janela Principal
# ──────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Price Checker Bot — Configurações")
        self.resizable(True, True)
        self.minsize(680, 560)

        self._config: dict = load_config()

        # ── Notebook (abas) ───────────────────────────────────────────────
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self._general_tab  = GeneralTab(notebook)
        self._products_tab = ProductsTab(notebook)
        self._stores_tab   = StoresTab(notebook)
        notebook.add(self._general_tab,  text="  ⚙️  Configurações Gerais  ")
        notebook.add(self._products_tab, text="  📦  Produtos  ")
        notebook.add(self._stores_tab,   text="  🏪  Lojas  ")

        # ── Barra inferior ────────────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))

        self._status_var = tk.StringVar(value="Pronto.")
        ttk.Label(bar, textvariable=self._status_var, foreground="gray").pack(side="left")
        ttk.Button(bar, text="Salvar configurações", command=self._save).pack(side="right")
        ttk.Button(bar, text="Recarregar", command=self._reload).pack(side="right", padx=(0, 6))

        # ── Carrega dados ────────────────────────────────────────────────
        self._load_all()
        self._center()

    def _load_all(self) -> None:
        self._general_tab.load(self._config)
        self._products_tab.load(self._config)
        self._stores_tab.load()

    def _reload(self) -> None:
        if messagebox.askyesno("Recarregar", "Descartar alterações e recarregar o config.json?"):
            self._config = load_config()
            self._load_all()
            self._status_var.set("Configuração recarregada.")

    def _save(self) -> None:
        self._general_tab.flush(self._config)
        self._products_tab.flush(self._config)

        # Validação mínima
        gs = self._config.get("google_sheets", {})
        if not gs.get("credentials_file", "").strip():
            messagebox.showwarning("Campo obrigatório", "Informe o arquivo de credenciais do Google.")
            return
        if not gs.get("spreadsheet_name", "").strip():
            messagebox.showwarning("Campo obrigatório", "Informe o nome da planilha.")
            return

        save_config(self._config)
        # Salva STORE_MAP em store_detector.py
        self._stores_tab.flush()
        self._status_var.set(f"✔  Salvo em {CONFIG_PATH.name}")
        messagebox.showinfo("Salvo!", f"config.json atualizado com sucesso.\n\nCaminho: {CONFIG_PATH}")

    def _center(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
