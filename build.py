"""
build.py
--------
Script de empacotamento do Price Checker Bot.
Detecta automaticamente os caminhos do Tcl/Tk e chama o PyInstaller.

Execute com:
    venv\\Scripts\\python.exe build.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Caminhos
# ─────────────────────────────────────────────────────────────────────────────
VENV_PYTHON = Path("venv/Scripts/python.exe")
VENV_PIP    = Path("venv/Scripts/pip.exe")
ROOT        = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────────────────
# 1. Verifica venv
# ─────────────────────────────────────────────────────────────────────────────
if not VENV_PYTHON.exists():
    print("ERRO: venv não encontrado. Rode primeiro:")
    print("  python -m venv venv")
    print("  venv\\Scripts\\pip install -r requirements.txt")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Atualiza PyInstaller
# ─────────────────────────────────────────────────────────────────────────────
print("[1/4] Instalando / atualizando PyInstaller...")
subprocess.check_call([str(VENV_PIP), "install", "--quiet", "--upgrade", "pyinstaller"])

# ─────────────────────────────────────────────────────────────────────────────
# 3. Detecta Tcl/Tk a partir do Python base do venv
# ─────────────────────────────────────────────────────────────────────────────
print("[2/4] Detectando caminhos Tcl/Tk...")

base_prefix = subprocess.check_output(
    [str(VENV_PYTHON), "-c", "import sys; print(sys.base_prefix)"],
    text=True
).strip()

tcl_dir = Path(base_prefix) / "tcl"
tcl_data = tk_data = None

if tcl_dir.is_dir():
    for item in tcl_dir.iterdir():
        name = item.name.lower()
        if name.startswith("tcl") and item.is_dir() and tcl_data is None:
            tcl_data = item
        if name.startswith("tk") and item.is_dir() and tk_data is None:
            tk_data = item

print(f"   TCL: {tcl_data}")
print(f"   TK:  {tk_data}")

if not tcl_data or not tk_data:
    print("AVISO: Tcl/Tk não encontrado no Python base. O .exe pode não abrir.")
    print("       Tente instalar o Python com Tcl/Tk via python.org (não Microsoft Store).")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Limpa builds anteriores
# ─────────────────────────────────────────────────────────────────────────────
print("[3/4] Limpando builds anteriores...")
for folder in ["build", "dist"]:
    p = ROOT / folder
    if p.exists():
        shutil.rmtree(p)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Monta o comando PyInstaller
# ─────────────────────────────────────────────────────────────────────────────
print("[4/4] Compilando app.py...")

cmd = [
    str(VENV_PYTHON), "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onedir",
    "--noconsole",
    "--name", "PriceCheckerBot",
    "--distpath", str(ROOT / "dist" / "PriceCheckerBot_tmp"),

    # Tcl/Tk — inclui explicitamente no local esperado pelo hook do PyInstaller
    *(["--add-data", f"{tcl_data};_tcl_data"] if tcl_data else []),
    *(["--add-data", f"{tk_data};_tk_data"]   if tk_data  else []),

    # collect-all: copia TODOS os arquivos dos pacotes (incl. binários mypyc)
    "--collect-all", "playwright",
    "--collect-all", "cloudscraper",
    "--collect-all", "price_tracker",
    "--collect-all", "gspread",
    "--collect-all", "tldextract",
    "--collect-all", "charset_normalizer",

    # hidden imports
    "--hidden-import", "price_tracker",
    "--hidden-import", "price_tracker.core",
    "--hidden-import", "price_tracker.core.price_extractor",
    "--hidden-import", "price_tracker.core.heuristics",
    "--hidden-import", "price_tracker.core.jsonld_parser",
    "--hidden-import", "price_tracker.core.store_detector",
    "--hidden-import", "price_tracker.scrapers",
    "--hidden-import", "price_tracker.scrapers.kabum",
    "--hidden-import", "price_tracker.scrapers.pichau",
    "--hidden-import", "price_tracker.scrapers.terabyte",
    "--hidden-import", "price_tracker.scrapers.amazon",
    "--hidden-import", "price_tracker.scrapers.universal",
    "--hidden-import", "price_tracker.utils",
    "--hidden-import", "price_tracker.utils.html_fetcher",
    "--hidden-import", "price_tracker.utils.price_parser",
    "--hidden-import", "cloudscraper",
    "--hidden-import", "gspread",
    "--hidden-import", "oauth2client",
    "--hidden-import", "oauth2client.service_account",
    "--hidden-import", "bs4",
    "--hidden-import", "lxml",
    "--hidden-import", "lxml.etree",
    "--hidden-import", "tldextract",
    "--hidden-import", "playwright",
    "--hidden-import", "playwright.sync_api",
    "--hidden-import", "playwright_stealth",
    "--hidden-import", "charset_normalizer",
    "--hidden-import", "chardet",

    "app.py",
]

result = subprocess.run(cmd, cwd=str(ROOT))

if result.returncode != 0:
    print("\nERRO: PyInstaller falhou. Veja o log acima.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 6. Organiza a pasta de saída
# ─────────────────────────────────────────────────────────────────────────────
src  = ROOT / "dist" / "PriceCheckerBot_tmp" / "PriceCheckerBot"
dest = ROOT / "dist" / "PriceCheckerBot"

if dest.exists():
    shutil.rmtree(dest)
shutil.move(str(src), str(dest))
shutil.rmtree(ROOT / "dist" / "PriceCheckerBot_tmp", ignore_errors=True)

# Copia arquivos de dados
for fname in ["config.json", "credentials.json", "icon.ico"]:
    src_f = ROOT / fname
    if src_f.exists():
        shutil.copy2(str(src_f), str(dest / fname))

(dest / "logs").mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 7. Copia binários do Playwright (Chromium) para o bundle
#    O Playwright armazena browsers em %LOCALAPPDATA%\ms-playwright\ (Windows).
#    O .exe espera encontrá-los em _internal\playwright\driver\package\.local-browsers\
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/5] Copiando binários do Playwright/Chromium para o bundle...")

_ms_pw_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
_pw_dst_base = dest / "_internal" / "playwright" / "driver" / "package" / ".local-browsers"
_pw_dst_base.mkdir(parents=True, exist_ok=True)

_browser_prefixes = ("chromium_headless_shell", "chromium", "ffmpeg", "winldd")
_copied = []

if _ms_pw_dir.is_dir():
    for item in _ms_pw_dir.iterdir():
        if item.is_dir() and item.name.startswith(_browser_prefixes):
            dst = _pw_dst_base / item.name
            if dst.exists():
                shutil.rmtree(dst)
            print(f"   Copiando: {item.name}  …")
            shutil.copytree(str(item), str(dst))
            _copied.append(item.name)
    if _copied:
        total_mb = sum(f.stat().st_size for f in _pw_dst_base.rglob("*") if f.is_file()) / (1024 * 1024)
        print(f"   Copiados: {', '.join(_copied)}")
        print(f"   Tamanho total: {total_mb:.0f} MB")
    else:
        print(f"   AVISO: nenhum browser encontrado em {_ms_pw_dir}")
        print("   Execute 'venv\\Scripts\\playwright install chromium' e recompile.")
else:
    print(f"   AVISO: pasta ms-playwright não encontrada em {_ms_pw_dir}")
    print("   Execute 'venv\\Scripts\\playwright install chromium' e recompile.")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Resumo
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("  Build concluido!")
print(f"\n  Pasta de saida: dist\\PriceCheckerBot\\")
print("  Executavel:     PriceCheckerBot.exe")
print("\n  IMPORTANTE:")
print("   1. Copie credentials.json para dist\\PriceCheckerBot\\")
print("   2. Ajuste config.json em dist\\PriceCheckerBot\\")
print("   3. O Chromium ja esta embutido — nao e necessario instalar nas")
print("      maquinas de destino.")
print("═" * 60)
