"""
config_gui.py
-------------
Interface gráfica (Tkinter) para configurar o bot sem editar o config.json
diretamente. Execute com:

    python config_gui.py

A janela possui três abas:
  • Configurações Gerais — Google Sheets e Telegram
  • Produtos            — Adicionar / Editar / Remover produtos
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

CONFIG_PATH = Path(__file__).parent / "config.json"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de I/O
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

        labels = ["Nome do produto:", "Loja:", "URL da página:"]
        self._entries: list[ttk.Entry] = []
        for row, label in enumerate(labels):
            ttk.Label(fields_frame, text=label).grid(row=row, column=0, sticky="w", **pad)
            entry = ttk.Entry(fields_frame, width=55)
            entry.grid(row=row, column=1, sticky="ew", **pad)
            self._entries.append(entry)
        fields_frame.columnconfigure(1, weight=1)

        self._name_entry, self._store_entry, self._url_entry = self._entries

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

        # ── Preenche com dados existentes ────────────────────────────────
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

    def _save(self) -> None:
        name = self._name_entry.get().strip()
        store = self._store_entry.get().strip()
        url = self._url_entry.get().strip()
        raw_selectors = self._sel_text.get("1.0", "end").strip()
        selectors = [s.strip() for s in raw_selectors.splitlines() if s.strip()]

        if not name:
            messagebox.showwarning("Campo obrigatório", "Informe o nome do produto.", parent=self)
            return
        if not store:
            messagebox.showwarning("Campo obrigatório", "Informe a loja.", parent=self)
            return
        if not url:
            messagebox.showwarning("Campo obrigatório", "Informe a URL.", parent=self)
            return
        self.result = {
            "name": name,
            "store": store,
            "url": url,
            "price_selectors": selectors,
        }
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
# Janela Principal
# ──────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Price Checker Bot — Configurações")
        self.resizable(True, True)
        self.minsize(680, 520)

        self._config: dict = load_config()

        # ── Notebook (abas) ───────────────────────────────────────────────
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self._general_tab = GeneralTab(notebook)
        self._products_tab = ProductsTab(notebook)
        notebook.add(self._general_tab, text="  ⚙️  Configurações Gerais  ")
        notebook.add(self._products_tab, text="  📦  Produtos  ")

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
