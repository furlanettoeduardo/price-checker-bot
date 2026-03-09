"""
scrapers/amazon.py
------------------
Scraper específico para amazon.com.br.

A Amazon usa estrutura HTML complexa onde o preço é dividido em:
  - Parte inteira:  <span class="a-price-whole">3899</span>
  - Separador:      <span class="a-price-decimal">,</span>
  - Centavos:       <span class="a-price-fraction">90</span>

Esta implementação tenta extrair o preço composto e também testa
seletores de fallback que retornam o preço como texto único.

NOTA: A Amazon é conhecida por bloquear bots. Se o preço não for
encontrado, verifique se a página retornou um CAPTCHA.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price, parse_installment

logger = logging.getLogger(__name__)

# Seletores para preço como texto único
_SINGLE_SELECTORS = [
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    ".a-price .a-offscreen",   # Texto acessível (geralmente tem o valor completo)
    "#corePrice_feature_div .a-offscreen",
    "[data-a-color='price'] .a-offscreen",
    "#apex_offerDisplay_desktop .a-price .a-offscreen",
]

_OLD_PRICE_SELECTORS = [
    ".a-text-price .a-offscreen",          # Preço riscado (strike-through)
    ".a-price.a-text-price .a-offscreen",
    "#listPrice",
    "#priceblock_listprice",
    ".a-price[data-a-strike='true'] .a-offscreen",
]

_INSTALLMENT_SELECTORS = [
    "#installmentCalculator_feature_div span",
    ".best-offer-name",
    "#buyInstallments",
    "#installments_feature_div span",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai preço e campos adicionais de uma página de produto da Amazon Brasil.

    Estratégia para preço principal:
      1. Tenta compor preço a partir de whole + fraction
      2. Fallback para seletores de texto único

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
    ou None se nenhum método funcionar.
    """
    # ── Tentativa 1: preço composto (whole + fraction) ────────────────────
    price = _extract_composed(soup)
    confidence = 0.92 if price is not None else 0.88

    if price is None:
        # ── Tentativa 2: seletores de texto único ─────────────────────────
        for selector in _SINGLE_SELECTORS:
            try:
                el = soup.select_one(selector)
                if el is None:
                    continue
                raw = el.get_text(separator="", strip=True)
                price = normalize_price(raw)
                if price is not None:
                    logger.info(f"[Amazon] Preço R$ {price:.2f} — seletor: '{selector}'")
                    break
            except Exception as exc:
                logger.debug(f"[Amazon] Erro no seletor '{selector}': {exc}")
    else:
        logger.info(f"[Amazon] Preço R$ {price:.2f} — método: composto")

    if price is None:
        # ── Verifica se a Amazon retornou CAPTCHA ────────────────────────
        if soup.find("form", {"action": "/errors/validateCaptcha"}):
            logger.error("[Amazon] CAPTCHA detectado — requisição bloqueada.")
        logger.warning("[Amazon] Nenhum seletor retornou preço válido.")
        return None

    result: dict = {
        "price": price,
        "preco_sem_promocao": None,
        "preco_parcelado": None,
        "parcelas": None,
        "preco_pix": None,
        "currency": "BRL",
        "confidence": confidence,
    }

    # ── Preço sem promoção (listPrice / riscado) ──────────────────────────
    for selector in _OLD_PRICE_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            old = normalize_price(el.get_text(separator="", strip=True))
            if old is not None and old > price:
                result["preco_sem_promocao"] = old
                logger.info(f"[Amazon] Preço sem promoção R$ {old:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Amazon] Erro seletor preço antigo '{selector}': {exc}")

    # ── Parcelamento ─────────────────────────────────────────────────────
    for selector in _INSTALLMENT_SELECTORS:
        try:
            for el in soup.select(selector):
                text = el.get_text(separator=" ", strip=True)
                count, value = parse_installment(text)
                if count is not None and value is not None:
                    result["parcelas"] = count
                    result["preco_parcelado"] = value
                    logger.info(f"[Amazon] Parcelamento: {count}x R$ {value:.2f}")
                    break
            if result["parcelas"] is not None:
                break
        except Exception as exc:
            logger.debug(f"[Amazon] Erro seletor parcelamento '{selector}': {exc}")

    return result


def _extract_composed(soup: BeautifulSoup) -> Optional[float]:
    """
    Tenta montar o preço a partir dos spans de parte inteira e fração.
    Ex: <span class="a-price-whole">3.899</span><span class="a-price-fraction">90</span>
    → 3899.90
    """
    try:
        whole_el = soup.select_one(".a-price-whole")
        fraction_el = soup.select_one(".a-price-fraction")

        if whole_el is None or fraction_el is None:
            return None

        whole = whole_el.get_text(strip=True).replace(".", "").replace(",", "")
        fraction = fraction_el.get_text(strip=True)

        if whole.isdigit() and fraction.isdigit():
            return float(f"{whole}.{fraction}")
    except Exception as exc:
        logger.debug(f"[Amazon] Erro na extração composta: {exc}")

    return None
