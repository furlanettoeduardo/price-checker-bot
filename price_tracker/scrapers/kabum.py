"""
scrapers/kabum.py
-----------------
Scraper específico para kabum.com.br.

Kabum usa uma SPA React com classes geradas dinamicamente.
Os seletores abaixo foram validados e listados do mais ao menos estável.
Se um seletor quebrar, basta ajustá-lo aqui — sem tocar no restante do código.
"""

import json
import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price, parse_installment

logger = logging.getLogger(__name__)

# Seletores em ordem de prioridade (mais estável → menos estável)
_SELECTORS = [
    "h4.finalPrice",               # Histórico mais estável
    "[class*='finalPrice']",       # Variante por substring de classe
    "[data-testid='new-price']",   # Atributo de teste — relativamente estável
    ".sc-fzoLsD.dHatnu",           # Classe interna (pode mudar com deploy)
    ".priceCard",
    "[class*='priceCard']",
    ".regularPrice",
    "[itemprop='price']",          # Microdata — alternativa ao JSON-LD
]

_OLD_PRICE_SELECTORS = [
    "[class*='oldPrice']",
    "[class*='old-price']",
    "[class*='regularPrice'] del",
    "del[class*='price']",
    "s[class*='price']",
    "[data-testid='old-price']",
]

_PIX_SELECTORS = [
    "[class*='pix']",
    "[class*='Pix']",
    "[data-testid='pix-price']",
    "[class*='pixPrice']",
    "[class*='pix-price']",
]

_INSTALLMENT_SELECTORS = [
    "[class*='installment']",
    "[class*='parcel']",
    "[class*='Installment']",
    "[class*='parcelas']",
    "[data-testid='installment']",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai preço e campos adicionais de uma página de produto da Kabum.

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
                logger.info(f"[Kabum] Preço R$ {price:.2f} — seletor: '{selector}'")
                break
        except Exception as exc:
            logger.debug(f"[Kabum] Erro no seletor '{selector}': {exc}")

    if price is None:
        logger.warning("[Kabum] Nenhum seletor retornou preço válido.")
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
                logger.info(f"[Kabum] Preço sem promoção R$ {old:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Kabum] Erro seletor preço antigo '{selector}': {exc}")

    # ── Preço Pix ────────────────────────────────────────────────────────
    for selector in _PIX_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            pix = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
            if pix is not None and pix > 0:
                result["preco_pix"] = pix
                logger.info(f"[Kabum] Preço Pix R$ {pix:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Kabum] Erro seletor Pix '{selector}': {exc}")

    # ── Parcelamento ─────────────────────────────────────────────────────
    for selector in _INSTALLMENT_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            text = el.get_text(separator=" ", strip=True)
            count, value = parse_installment(text)
            if count is not None and value is not None:
                result["parcelas"] = count
                result["preco_parcelado"] = value
                logger.info(f"[Kabum] Parcelamento: {count}x R$ {value:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Kabum] Erro seletor parcelamento '{selector}': {exc}")

    # ── Suplementa com dados do Next.js (__NEXT_DATA__) ──────────────────
    # Kabum usa Next.js: prices.price = preço regular, priceWithDiscount = promocional
    next_extra = _extract_from_next_data(soup)
    for field, value in next_extra.items():
        if result.get(field) is None and value is not None:
            result[field] = value

    return result


def _extract_from_next_data(soup: BeautifulSoup) -> dict:
    """
    Extrai preços adicionais do bloco __NEXT_DATA__ injetado pelo Next.js.

    Kabum inclui em `pageProps.product.prices`:
      - price             : preço regular (sem desconto)
      - priceWithDiscount : preço promocional (o que o cliente paga)
      - discountPercentage: percentual de desconto
    Quando há desconto, `price` é o `preco_sem_promocao` que buscamos.
    """
    extra: dict = {}
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return extra

    try:
        data = json.loads(script.string)
        prices = (
            data.get("props", {})
                .get("pageProps", {})
                .get("product", {})
                .get("prices", {})
        )
        regular  = prices.get("price")
        promo    = prices.get("priceWithDiscount")
        discount = prices.get("discountPercentage", 0)

        if discount and discount > 0 and regular and promo and regular != promo:
            old = normalize_price(str(regular))
            if old is not None and old > 0:
                extra["preco_sem_promocao"] = old
                logger.info(
                    f"[Kabum/__NEXT_DATA__] Preço sem promoção: R$ {old:.2f} "
                    f"(desconto {discount}%)"
                )
    except Exception as exc:
        logger.debug(f"[Kabum] Erro ao parsear __NEXT_DATA__: {exc}")

    return extra

