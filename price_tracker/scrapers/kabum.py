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


def extract_supplementary(soup: BeautifulSoup) -> dict:
    """
    Extrai apenas os campos suplementares (sem exigir preço via CSS).
    Chamado pelo price_extractor quando JSON-LD ou outra camada já
    encontrou o preço principal mas ainda faltam preco_sem_promocao,
    preco_pix, parcelas e preco_parcelado.
    """
    return _extract_from_next_data(soup)


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

    # ── __NEXT_DATA__ primeiro (fonte mais confiável na Kabum) ────────────
    # Preenche preco_sem_promocao e preco_pix a partir do JSON injetado
    next_extra = _extract_from_next_data(soup)
    for field, value in next_extra.items():
        if value is not None:
            result[field] = value  # __NEXT_DATA__ tem prioridade

    # ── Preço sem promoção (riscado) — fallback CSS ───────────────────────
    if result["preco_sem_promocao"] is None:
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

    # ── Preço Pix — fallback CSS (só aceita se estritamente menor que o preço) ─
    if result["preco_pix"] is None:
        for selector in _PIX_SELECTORS:
            try:
                el = soup.select_one(selector)
                if el is None:
                    continue
                pix = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
                if pix is not None and 0 < pix < price:
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

    return result


def _extract_from_next_data(soup: BeautifulSoup) -> dict:
    """
    Extrai preços adicionais do bloco __NEXT_DATA__ injetado pelo Next.js.

    Estrutura real de `pageProps.product.prices` na Kabum:
      - oldPrice          : preço original sem desconto (= preco_sem_promocao)
      - priceWithDiscount : preço pix/à vista — JÁ é o preço final descontado
      - price             : total do parcelamento (preço no cartão)
      - discountPercentage: % de desconto JÁ aplicado sobre 'price' para
                            chegar em 'priceWithDiscount' (não é desconto extra)

    preco_pix = priceWithDiscount  (usar diretamente — não recalcular).
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

        old_price   = prices.get("oldPrice")           # preço riscado
        promo_price = prices.get("priceWithDiscount")  # preço atual com desconto
        card_total  = prices.get("price")              # total no cartão
        pix_pct     = prices.get("discountPercentage", 0)  # % já aplicado

        # ── Preço sem promoção (riscado) ─────────────────────────────────
        if old_price and promo_price and float(old_price) > float(promo_price):
            old = round(float(old_price), 2)
            extra["preco_sem_promocao"] = old
            logger.info(f"[Kabum/__NEXT_DATA__] Preço sem promoção: R$ {old:.2f}")

        # ── Preço Pix ─────────────────────────────────────────────────────
        # priceWithDiscount JÁ É o preço pix/à vista.
        # o discountPercentage descreve o desconto já aplicado para chegar
        # nesse valor a partir do preço no cartão (prices.price), não é
        # um desconto adicional a ser calculado.
        if promo_price:
            pix = round(float(promo_price), 2)
            extra["preco_pix"] = pix
            logger.info(
                f"[Kabum/__NEXT_DATA__] Preço Pix: R$ {pix:.2f} "
                f"(priceWithDiscount direto — {pix_pct}% já aplicado)"
            )

        # ── Preço total no cartão ───────────────────────────────────────
        if card_total:
            total = round(float(card_total), 2)
            extra["preco_cartao"] = total
            logger.info(f"[Kabum/__NEXT_DATA__] Preço Cartão (total): R$ {total:.2f}")

    except Exception as exc:
        logger.debug(f"[Kabum] Erro ao parsear __NEXT_DATA__: {exc}")

    return extra

