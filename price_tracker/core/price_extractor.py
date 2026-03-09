"""
price_extractor.py
------------------
Orquestrador principal — implementa a função central get_product_price().

Ordem de tentativa (do mais ao menos confiável):
  1. JSON-LD        — dados estruturados; independe de CSS
  2. Scraper de loja— seletores calibrados por loja conhecida
  3. Seletores CSS  — lista fornecida no config.json pelo usuário
  4. Heurística     — regex + pontuação automática (último recurso)

Retorno padronizado de get_product_price():
    {
        "price"     : float | None,
        "currency"  : "BRL",
        "confidence": float,   # 0.0–1.0
        "method"    : str,     # "jsonld" | "store" | "css" | "heuristic" | "failed"
        "url"       : str,
    }
"""

import importlib
import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.core.heuristics import extract_price_heuristic
from price_tracker.core.jsonld_parser import extract_price_jsonld
from price_tracker.core.store_detector import detect_store
from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)


# ── Funções públicas de cada camada ──────────────────────────────────────────

def extract_price_store(soup: BeautifulSoup, store_id: str) -> Optional[dict]:
    """
    Camada 2: carrega dinamicamente o scraper da loja e executa a extração.

    Parâmetros
    ----------
    soup     : BeautifulSoup da página já baixada
    store_id : Identificador da loja (ex: "kabum", "pichau")

    Retorna dict com price/currency/confidence/method ou None.
    """
    try:
        module = importlib.import_module(f"price_tracker.scrapers.{store_id}")
    except ModuleNotFoundError:
        logger.debug(f"Scraper para '{store_id}' não encontrado.")
        return None

    try:
        result = module.extract(soup)
        if result and result.get("price") is not None:
            result["method"] = "store"
            logger.info(
                f"[Store:{store_id}] Preço extraído: "
                f"R$ {result['price']:.2f} "
                f"(confiança: {result.get('confidence', '?')})"
            )
            return result
    except Exception as exc:
        logger.error(
            f"Erro no scraper de loja '{store_id}': {exc}",
            exc_info=True,
        )

    return None


def _extract_price_css(
    soup: BeautifulSoup,
    selectors: list[str],
) -> Optional[dict]:
    """
    Camada 3: tenta extrair o preço com seletores CSS fornecidos no config.json.
    """
    for selector in selectors:
        try:
            element = soup.select_one(selector)
            if element is None:
                continue
            raw_text = element.get_text(separator=" ", strip=True)
            price = normalize_price(raw_text)
            if price is not None:
                logger.info(
                    f"[CSS] Preço extraído com seletor '{selector}': "
                    f"R$ {price:.2f}"
                )
                return {
                    "price": price,
                    "currency": "BRL",
                    "confidence": 0.75,
                    "method": "css",
                }
        except Exception as exc:
            logger.warning(f"Erro ao aplicar seletor CSS '{selector}': {exc}")

    return None


# ── Função principal ──────────────────────────────────────────────────────────

def get_product_price(
    url: str,
    css_selectors: Optional[list[str]] = None,
) -> dict:
    """
    Extrai o preço de um produto de forma robusta usando estratégia em camadas.

    Parâmetros
    ----------
    url           : URL completa da página do produto
    css_selectors : Seletores CSS do config.json (usados na camada 3)

    Retorna
    -------
    {
        "price"     : float | None,
        "currency"  : "BRL",
        "confidence": float,
        "method"    : "jsonld" | "store" | "css" | "heuristic" | "failed",
        "url"       : str,
    }
    """
    base = {
        "price": None,
        "preco_sem_promocao": None,
        "preco_parcelado": None,
        "parcelas": None,
        "preco_pix": None,
        "currency": "BRL",
        "confidence": 0.0,
        "method": "failed",
        "url": url,
    }

    # ── Download da página (com cache) ────────────────────────────────────
    soup = fetch_page(url)
    if soup is None:
        logger.error(f"Impossível acessar: {url}")
        return base

    # ── Camada 1: JSON-LD ─────────────────────────────────────────────────
    result = extract_price_jsonld(soup)
    if result and result.get("price"):
        return {**base, **result}

    # ── Camada 2: Scraper específico de loja ──────────────────────────────
    store_id = detect_store(url)
    if store_id:
        result = extract_price_store(soup, store_id)
        if result and result.get("price"):
            return {**base, **result}
    else:
        logger.debug("Loja não reconhecida — pulando scraper de loja.")

    # ── Camada 3: Seletores CSS do config.json ────────────────────────────
    if css_selectors:
        result = _extract_price_css(soup, css_selectors)
        if result and result.get("price"):
            return {**base, **result}

    # ── Camada 4: Heurística (fallback) ───────────────────────────────────
    result = extract_price_heuristic(soup)
    if result and result.get("price"):
        return {**base, **result}

    logger.error(f"Todos os métodos de extração falharam para: {url}")
    return base
