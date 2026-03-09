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

from price_tracker.core.heuristics import extract_price_heuristic, extract_supplementary_fields
from price_tracker.core.jsonld_parser import extract_price_jsonld
from price_tracker.core.store_detector import detect_store
from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price
from price_tracker.scrapers import universal as _universal_scraper

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
    use_playwright: bool = False,
) -> dict:
    """
    Extrai o preço de um produto de forma robusta usando estratégia em camadas.

    Parâmetros
    ----------
    url            : URL completa da página do produto
    css_selectors  : Seletores CSS do config.json (usados na camada 3)
    use_playwright : Se True, usa Playwright+stealth para baixar a página —
                     necessário para sites que renderizam preços via JavaScript
                     ou que bloqueiam requests/cloudscraper com Cloudflare UAM.

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
    soup = fetch_page(url, use_playwright=use_playwright)
    if soup is None:
        logger.error(f"Impossível acessar: {url}")
        return base

    # Detecta loja uma vez — reutilizada em todas as camadas abaixo
    store_id = detect_store(url)

    # ── Camada 1: JSON-LD ─────────────────────────────────────────────────
    result = extract_price_jsonld(soup)
    if result and result.get("price"):
        return _fill_supplementary({**base, **result}, soup, store_id)

    # ── Camada 2: Scraper específico de loja ──────────────────────────────
    if store_id:
        result = extract_price_store(soup, store_id)
        if result and result.get("price"):
            result["method"] = "store"
            return _fill_supplementary({**base, **result}, soup, store_id)

    # ── Camada 2b: Scraper universal (Shopify, VTEX, WooCommerce, CSS genérico) ─
    result = _universal_scraper.extract(soup)
    if result and result.get("price"):
        result["method"] = "universal"
        return _fill_supplementary({**base, **result}, soup, store_id)

    # ── Camada 3: Seletores CSS do config.json ────────────────────────────
    if css_selectors:
        result = _extract_price_css(soup, css_selectors)
        if result and result.get("price"):
            return _fill_supplementary({**base, **result}, soup, store_id)

    # ── Camada 4: Heurística (fallback) ───────────────────────────────────
    result = extract_price_heuristic(soup)
    if result and result.get("price"):
        return _fill_supplementary({**base, **result}, soup, store_id)

    logger.error(f"Todos os métodos de extração falharam para: {url}")
    return base

def _fill_supplementary(
    result: dict,
    soup: BeautifulSoup,
    store_id: Optional[str] = None,
) -> dict:
    """
    Preenche preco_pix, preco_parcelado e parcelas em duas etapas:
      1. Chama extract_supplementary() do scraper específico da loja (se existir)
      2. Fallback genérico: regex no texto completo da página
    Campos já preenchidos não são sobrescritos.
    """
    SUPP_FIELDS = ("preco_sem_promocao", "preco_pix", "preco_parcelado", "parcelas")

    if all(result.get(f) is not None for f in SUPP_FIELDS):
        return result  # tudo já preenchido

    # ── Etapa 1: scraper específico da loja (ex: Kabum → __NEXT_DATA__) ─────
    if store_id:
        try:
            module = importlib.import_module(f"price_tracker.scrapers.{store_id}")
            if hasattr(module, "extract_supplementary"):
                store_supp = module.extract_supplementary(soup)
                for field, value in store_supp.items():
                    if result.get(field) is None and value is not None:
                        result[field] = value
                        logger.debug(
                            f"[Supplementary/{store_id}] {field} = {value}"
                        )
        except Exception as exc:
            logger.debug(f"[Supplementary] Erro no scraper de '{store_id}': {exc}")

    # ── Valida campos suplementares ──────────────────────────────────────
    price = result.get("price")

    # preco_sem_promocao deve ser MAIOR que o preço atual
    sem_promo = result.get("preco_sem_promocao")
    if sem_promo is not None and price is not None and sem_promo <= price:
        logger.debug(
            f"[Supplementary] preco_sem_promocao R$ {sem_promo:.2f} descartado "
            f"(não é maior que price R$ {price:.2f})"
        )
        result["preco_sem_promocao"] = None

    # preco_pix deve ser MENOR que o preço atual (é sempre um desconto)
    pix = result.get("preco_pix")
    if pix is not None and price is not None and pix >= price:
        logger.debug(
            f"[Supplementary] preco_pix R$ {pix:.2f} descartado "
            f"(não é menor que price R$ {price:.2f})"
        )
        result["preco_pix"] = None

    if all(result.get(f) is not None for f in SUPP_FIELDS):
        return result

    # ── Etapa 2: fallback genérico (regex no texto) ──────────────────────
    supplementary = extract_supplementary_fields(soup)
    for field, value in supplementary.items():
        if result.get(field) is None and value is not None:
            result[field] = value
    return result