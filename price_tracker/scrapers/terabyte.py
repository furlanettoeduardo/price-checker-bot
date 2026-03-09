"""
scrapers/terabyte.py
--------------------
Scraper específico para terabyteshop.com.br.

A Terabyte Shop usa estrutura HTML mais tradicional com IDs e classes
semânticas, o que torna os seletores relativamente estáveis.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price, parse_installment

logger = logging.getLogger(__name__)

_SELECTORS = [
    "#prod-new-price",             # ID do preço principal — mais estável
    ".prod-new-price span",        # Span dentro do container de preço
    ".val_principal",              # Classe de valor principal
    "#price-view-default",
    "[class*='new-price']",
    "[itemprop='price']",          # Microdata
    ".preco-original",
    "span[id*='price']",
]

_OLD_PRICE_SELECTORS = [
    ".prod-old-price span",
    "#prod-old-price",
    "[class*='old-price']",
    ".preco-antigo",
    "del[class*='price']",
    "s[class*='price']",
]

_PIX_SELECTORS = [
    "#prod-pix-price span",
    ".prod-pix-price span",
    "#prod-pix-price",
    ".prod-pix-price",
    "[class*='pix-price']",
    "[class*='pixPrice']",
    "[id*='pix-price']",
]

_INSTALLMENT_SELECTORS = [
    ".prod-parcel span",
    "#prod-parcel",
    ".prod-parcel",
    "[class*='parcel']",
    "[id*='parcel']",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai preço e campos adicionais de uma página de produto da Terabyte Shop.

    Retorna
    -------
    {
        "price"            : float,
        "preco_sem_promocao": float | None,
        "preco_parcelado"  : float | None,
        "parcelas"         : int | None,
        "preco_pix"        : float | None,
        "currency"         : "BRL",
        "confidence"       : float,
    }
    ou None se nenhum seletor retornar preço válido.
    """
    price = None
    for selector in _SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)
            if price is not None:
                logger.info(f"[Terabyte] Preço R$ {price:.2f} — seletor: '{selector}'")
                break
        except Exception as exc:
            logger.debug(f"[Terabyte] Erro no seletor '{selector}': {exc}")

    if price is None:
        logger.warning("[Terabyte] Nenhum seletor retornou preço válido.")
        return None

    result: dict = {
        "price": price,
        "preco_sem_promocao": None,
        "preco_parcelado": None,
        "parcelas": None,
        "preco_pix": None,
        "currency": "BRL",
        "confidence": 0.90,
    }

    # ── Preço sem promoção (riscado) ─────────────────────────────────────
    for selector in _OLD_PRICE_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            old = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
            if old is not None and old > price:
                result["preco_sem_promocao"] = old
                logger.info(f"[Terabyte] Preço sem promoção R$ {old:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Terabyte] Erro seletor preço antigo '{selector}': {exc}")

    # ── Preço Pix ────────────────────────────────────────────────────────
    for selector in _PIX_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            pix = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
            if pix is not None and pix > 0:
                result["preco_pix"] = pix
                logger.info(f"[Terabyte] Preço Pix R$ {pix:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Terabyte] Erro seletor Pix '{selector}': {exc}")

    # ── Parcelamento ─────────────────────────────────────────────────────
    for selector in _INSTALLMENT_SELECTORS:
        try:
            for el in soup.select(selector):
                text = el.get_text(separator=" ", strip=True)
                count, value = parse_installment(text)
                if count is not None and value is not None:
                    result["parcelas"] = count
                    result["preco_parcelado"] = value
                    logger.info(f"[Terabyte] Parcelamento: {count}x R$ {value:.2f}")
                    break
            if result["parcelas"] is not None:
                break
        except Exception as exc:
            logger.debug(f"[Terabyte] Erro seletor parcelamento '{selector}': {exc}")

    return result

