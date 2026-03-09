"""
main.py
-------
Ponto de entrada do Price Checker Bot.

Fluxo de execução:
1. Carrega configurações do config.json
2. Configura o sistema de logs
3. Conecta ao Google Sheets
4. Para cada produto na lista:
   a. Verifica se já existe registro do dia (evita duplicatas)
   b. Raspa o preço atual da página
   c. Calcula o menor preço histórico
   d. Grava na planilha
   e. Envia alerta no Telegram (se habilitado e for novo mínimo)
5. Exibe resumo da execução
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Módulos internos do projeto
# ──────────────────────────────────────────────────────────────────────────────
# Extrator de preço com estratégia em camadas (JSON-LD → loja → CSS → heurística)
from price_tracker.core.price_extractor import get_product_price
from sheets import append_row, connect_to_sheets, get_min_price, is_duplicate
from notifier import notify_new_low, notify_error

# ──────────────────────────────────────────────────────────────────────────────
# Caminhos e constantes
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "price_tracker.log"


# ──────────────────────────────────────────────────────────────────────────────
# Configuração de logging
# ──────────────────────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    """
    Configura o sistema de logging para gravar tanto no console
    quanto em arquivo rotativo dentro da pasta logs/.
    """
    LOG_DIR.mkdir(exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de arquivo (persiste logs em disco)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)

    # Handler de console (saída em tempo real)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)

    logging.basicConfig(
        level=numeric_level,
        handlers=[file_handler, console_handler],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Carregamento de configuração
# ──────────────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    """
    Lê e valida o arquivo config.json.
    Encerra o programa com mensagem clara em caso de erro.
    """
    if not path.exists():
        print(f"[ERRO] Arquivo de configuração não encontrado: {path}")
        print("Crie o config.json a partir do exemplo no README.")
        sys.exit(1)

    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERRO] config.json inválido: {exc}")
        sys.exit(1)

    # Validação mínima
    if "products" not in config:
        print("[ERRO] config.json não contém a chave 'products'.")
        sys.exit(1)

    if "google_sheets" not in config:
        print("[ERRO] config.json não contém a chave 'google_sheets'.")
        sys.exit(1)

    return config


# ──────────────────────────────────────────────────────────────────────────────
# Validação de produto individual
# ──────────────────────────────────────────────────────────────────────────────

def validate_product(product: dict) -> Optional[str]:
    """
    Valida se um produto do config.json tem todos os campos obrigatórios.
    Retorna None se válido, ou uma string de erro se inválido.

    Apenas 'url' é obrigatório. 'name' e 'store' são preenchidos
    automaticamente se omitidos. 'price_selectors' é sempre opcional.
    """
    if not product.get("url", "").strip():
        return "Campo 'url' ausente ou vazio"
    selectors = product.get("price_selectors")
    if selectors is not None and not isinstance(selectors, list):
        return "price_selectors deve ser uma lista de strings (ou omitido)"
    return None


def _auto_name(url: str, idx: int) -> str:
    """Gera um nome legível a partir da URL quando 'name' não é informado."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Pega o último segmento não-vazio do path
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            slug = parts[-1].replace("-", " ").replace("_", " ").strip()
            if slug and not slug.isdigit():
                return slug[:80].title()
        # Fallback para o domínio
        host = parsed.netloc.lstrip("www.").split(".")[0]
        return f"{host.title()} #{idx}"
    except Exception:
        return f"Produto #{idx}"


def _auto_store(url: str) -> str:
    """Infere o nome de exibição da loja a partir do domínio da URL."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lstrip("www.")
        # Pega o nome antes do primeiro ponto e capitaliza
        name = host.split(".")[0]
        return name.title()
    except Exception:
        return "?"


# ──────────────────────────────────────────────────────────────────────────────
# Lógica principal
# ──────────────────────────────────────────────────────────────────────────────

def run() -> None:
    logger = logging.getLogger(__name__)
    today = str(date.today())  # Formato: "YYYY-MM-DD"

    logger.info("=" * 65)
    logger.info("  PRICE CHECKER BOT — Iniciando execução")
    logger.info(f"  Data: {today}")
    logger.info("=" * 65)

    # ── Carrega configurações ──────────────────────────────────────────────
    config = load_config(CONFIG_FILE)
    products = config["products"]
    sheets_cfg = config["google_sheets"]
    telegram_cfg = config.get("telegram", {})

    telegram_enabled = telegram_cfg.get("enabled", False)
    telegram_token = telegram_cfg.get("bot_token", "")
    telegram_chat = telegram_cfg.get("chat_id", "")
    alert_on_new_low = telegram_cfg.get("alert_on_new_low", True)

    if not products:
        logger.warning("Nenhum produto encontrado em config.json → encerrando.")
        return

    # ── Conecta ao Google Sheets ───────────────────────────────────────────
    logger.info("Conectando ao Google Sheets...")
    sheet = connect_to_sheets(
        credentials_file=sheets_cfg.get("credentials_file", "credentials.json"),
        spreadsheet_name=sheets_cfg.get("spreadsheet_name", "Price Tracker"),
    )

    # ── Contadores para o resumo final ────────────────────────────────────
    ok_count = 0
    skip_count = 0
    error_count = 0
    new_lows = []

    # ── Itera sobre os produtos ────────────────────────────────────────────
    for idx, product in enumerate(products, start=1):
        url      = product.get("url", "").strip()
        name     = product.get("name", "").strip() or _auto_name(url, idx)
        store    = product.get("store", "").strip() or _auto_store(url)
        selectors = product.get("price_selectors", [])

        logger.info(f"[{idx}/{len(products)}] Verificando: {name} ({store})")

        # Validação do produto
        error_msg = validate_product(product)
        if error_msg:
            logger.warning(f"  → Produto ignorado — {error_msg}: {product}")
            error_count += 1
            continue

        # Verifica duplicata
        if is_duplicate(sheet, today, name):
            logger.info(f"  → Já registrado hoje. Pulando.")
            skip_count += 1
            continue

        # Extrai o preço — tenta em ordem: JSON-LD → scraper de loja → CSS → heurística
        extraction = get_product_price(url, css_selectors=selectors)
        price = extraction.get("price")
        method = extraction.get("method", "?")
        confidence = extraction.get("confidence", 0.0)

        if price is None:
            logger.error(
                f"  → Falha ao extrair preço de '{name}'. "
                "Verifique a URL e os seletores CSS no config.json."
            )
            error_count += 1

            # Notifica erro via Telegram (opcional)
            if telegram_enabled:
                notify_error(
                    telegram_token,
                    telegram_chat,
                    name,
                    store,
                    "Todos os métodos de extração falharam (JSON-LD, scraper, CSS, heurística).",
                )
            continue

        logger.info(f"  → Método: {method} | Confiança: {confidence:.0%}")

        # Calcula mínimo histórico (antes de gravar o novo registro)
        previous_min = get_min_price(sheet, name)
        new_min = min(previous_min, price) if previous_min is not None else price
        is_new_low = (previous_min is None) or (price <= previous_min)

        # Grava na planilha
        success = append_row(
            sheet=sheet,
            data={
                "data": today,
                "produto": name,
                "loja": store,
                "preco": price,
                "preco_sem_promocao": extraction.get("preco_sem_promocao"),
                "preco_pix": extraction.get("preco_pix"),
                "preco_parcelado": extraction.get("preco_parcelado"),
                "parcelas": extraction.get("parcelas"),
                "url": url,
            },
            min_price=new_min,
        )

        if success:
            ok_count += 1
            if is_new_low:
                new_lows.append({"name": name, "store": store, "price": price, "url": url})
        else:
            error_count += 1

        # Alerta Telegram para novo mínimo histórico
        if telegram_enabled and alert_on_new_low and is_new_low:
            notify_new_low(
                bot_token=telegram_token,
                chat_id=telegram_chat,
                product_name=name,
                store=store,
                price=price,
                previous_min=previous_min,
                url=url,
            )

    # ── Resumo final ──────────────────────────────────────────────────────
    logger.info("=" * 65)
    logger.info("  RESUMO DA EXECUÇÃO")
    logger.info(f"  ✓ Registrados com sucesso : {ok_count}")
    logger.info(f"  → Pulados (já registrados): {skip_count}")
    logger.info(f"  ✗ Erros                   : {error_count}")

    if new_lows:
        logger.info("  🔥 Novos mínimos históricos:")
        for item in new_lows:
            logger.info(f"     • {item['name']} ({item['store']}): R$ {item['price']:,.2f}")

    logger.info("=" * 65)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Configura logs antes de qualquer outra coisa
    setup_logging(level="INFO")
    run()
