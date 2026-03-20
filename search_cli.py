#!/usr/bin/env python3
"""
search_cli.py
-------------
Busca um produto por nome e exibe lista de preços ordenada por loja.

Uso:
    python search_cli.py "RTX 4070"
    python search_cli.py "RTX 4070" --max-results 20
    python search_cli.py "RTX 4070" --min-price 2000 --max-price 5000
    python search_cli.py "RTX 4070" --sources mercadolivre
    python search_cli.py "RTX 4070" --no-urls
"""

import argparse
import io
import json
import logging
import sys
from pathlib import Path

# Force UTF-8 output on Windows (avoids UnicodeEncodeError with emojis / box-chars)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure the repo root is in sys.path when running this file directly.
sys.path.insert(0, str(Path(__file__).parent))

from price_tracker.search.aggregator import DEFAULT_SOURCES, search


# ─────────────────────────────────────────────────────────────────────────────
# Formatação de saída
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_price(price: float) -> str:
    """Formata float para o padrão monetário brasileiro: R$ 3.499,90"""
    formatted = f"{price:,.2f}"  # 3,499.90  (locale EN)
    # Swap separators: 3,499.90 → 3.499,90
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _source_tag(source: str) -> str:
    """Retorna rótulo compacto da fonte."""
    tags = {
        "mercadolivre": "ML",
        "zoom": "ZM",
        "kabum": "KB",
        "pichau": "PI",
        "terabyte": "TB",
        "amazon": "AMZ",
    }
    return f"[{tags.get(source, source[:2].upper())}]"


def _print_table(result: dict, show_urls: bool = True) -> None:
    offers = result["offers"]

    if not offers:
        print("\nNenhuma oferta encontrada.")
        print("Sugestões:")
        print("  • Tente termos mais genéricos (ex: 'rtx 4070' em vez do nome completo)")
        print("  • Remova filtros de preço com --min-price / --max-price")
        print("  • Adicione mais fontes com --sources mercadolivre zoom\n")
        return

    # Dynamic column widths (capped to avoid very wide terminals)
    name_w = min(55, max(len(o["name"]) for o in offers))
    store_w = min(28, max(len(o["store"]) for o in offers))
    price_w = 14

    sep_w = name_w + store_w + price_w + 14
    separator = "─" * sep_w

    print()
    print(f'🔍  Busca: "{result["query"]}"')
    print(f"    {result['total']} oferta(s) encontrada(s)")
    if result["min_price"] is not None:
        print(
            f"    Menor: {_fmt_price(result['min_price'])}"
            f"   |   Maior: {_fmt_price(result['max_price'])}"
        )
    print()
    print(f"  {'#':>3}  {'Produto':<{name_w}}  {'Loja':<{store_w}}  {'Preço':>{price_w}}  Fonte")
    print(f"  {separator}")

    for i, offer in enumerate(offers, start=1):
        name = offer["name"][:name_w]
        store = offer["store"][:store_w]
        price = _fmt_price(offer["price"])
        tag = _source_tag(offer["source"])
        print(f"  {i:>3}  {name:<{name_w}}  {store:<{store_w}}  {price:>{price_w}}  {tag}")
        if show_urls and offer.get("url"):
            url = offer["url"]
            print(f"       → {url}")

    print(f"  {separator}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="search_cli.py",
        description="Busca preços de um produto em múltiplos sites brasileiros.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python search_cli.py "RTX 4070"
  python search_cli.py "Ryzen 7 9800X3D" --max-results 20
  python search_cli.py "SSD 1TB NVMe" --min-price 200 --max-price 600
  python search_cli.py "memória RAM DDR5" --sources mercadolivre
        """,
    )

    parser.add_argument(
        "query",
        help="Nome do produto a buscar (ex: 'RTX 4070')",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        metavar="N",
        help="Número máximo de resultados por fonte (padrão: 10)",
    )
    parser.add_argument(
        "--min-price",
        type=float,
        default=None,
        metavar="R$",
        help="Preço mínimo em R$ (opcional)",
    )
    parser.add_argument(
        "--max-price",
        type=float,
        default=None,
        metavar="R$",
        help="Preço máximo em R$ (opcional)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        choices=list(DEFAULT_SOURCES),
        metavar="FONTE",
        help=(
            f"Fontes a consultar (padrão: todas). "
            f"Disponíveis: {', '.join(DEFAULT_SOURCES)}"
        ),
    )
    parser.add_argument(
        "--no-urls",
        action="store_true",
        help="Omite os links das ofertas na saída",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de verbosidade do log interno (padrão: WARNING)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load optional API credentials from config.json if it exists alongside this script.
    source_kwargs: dict = {}
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            ml_kwargs: dict = {}
            if cfg.get("mercadolivre_access_token"):
                ml_kwargs["access_token"] = cfg["mercadolivre_access_token"]
            if cfg.get("mercadolivre_refresh_token"):
                ml_kwargs["refresh_token"] = cfg["mercadolivre_refresh_token"]
            if cfg.get("mercadolivre_app_id"):
                ml_kwargs["app_id"] = cfg["mercadolivre_app_id"]
            if cfg.get("mercadolivre_secret_key"):
                ml_kwargs["secret_key"] = cfg["mercadolivre_secret_key"]
            if ml_kwargs:
                source_kwargs["mercadolivre"] = ml_kwargs
        except (json.JSONDecodeError, OSError):
            pass

    print(f"Buscando '{args.query}'...", end=" ", flush=True)

    result = search(
        query=args.query,
        max_results=args.max_results,
        min_price=args.min_price,
        max_price=args.max_price,
        sources=args.sources,
        source_kwargs=source_kwargs,
    )

    print("pronto.")
    _print_table(result, show_urls=not args.no_urls)


if __name__ == "__main__":
    main()
