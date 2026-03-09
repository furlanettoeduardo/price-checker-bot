"""
scrapers/pichau.py
------------------
Scraper específico para pichau.com.br.

Pichau usa Material UI (MUI). As classes `.MuiTypography-*` são geradas
pelo framework e tendem a ser estáveis, mas o texto "R$" às vezes fica
separado do número em spans distintos — por isso verificamos o elemento
pai quando necessário.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price, parse_installment

logger = logging.getLogger(__name__)

_SELECTORS = [
    # Preço em texto completo dentro de H1 (layout desktop)
    "h1.MuiTypography-h1",
    ".MuiTypography-h1",
    # Containers de preço com classes semânticas
    "[class*='ProductPrice']",
    "[class*='productPrice']",
    ".productPrice",
    # Seletores genéricos de preço MUI
    "[class*='price'] .MuiTypography-root",
    "span[class*='price']",
    # Microdata
    "[itemprop='price']",
]

_OLD_PRICE_SELECTORS = [
    "[class*='oldPrice']",
    "[class*='old-price']",
    "[class*='WasPrice']",
    "[class*='wasPrice']",
    "s[class*='MuiTypography']",
    "del[class*='MuiTypography']",
    "s.MuiTypography-root",
    "del",
]

_PIX_SELECTORS = [
    "[class*='pix']",
    "[class*='Pix']",
    "[class*='pixPrice']",
    "[class*='pix-price']",
]

_INSTALLMENT_SELECTORS = [
    "[class*='installment']",
    "[class*='parcel']",
    "[class*='Parcel']",
    "[class*='parcela']",
    "p[class*='MuiTypography']",   # texto de parcelamento em parágrafo MUI
]


def extract_supplementary(soup: BeautifulSoup) -> dict:
    """
    Extrai campos suplementares específicos da Pichau.

    Pichau não exibe o preço Pix como número concreto — só como porcentagem
    de desconto no texto (ex: "no PIX com 15% desconto").
    O preço Pix é calculado: price_principal × (1 − desconto/100).
    O preço principal é obtido via JSON-LD ou seletores MUI.
    """
    extra: dict = {}

    full_text = soup.get_text(separator=" ", strip=True)

    # ── Preço sem promoção (riscado) ─────────────────────────────────────
    # Pichau usa classe MUI gerada dinâmicamente: 'mui-*-strikeThrough'
    for sel in ["[class*='strikeThrough']", "[class*='strike-through']",
                "[class*='oldPrice']", "[class*='old-price']",
                "s.MuiTypography-root", "del.MuiTypography-root", "del"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            old = normalize_price(el.get_text(separator=" ", strip=True))
            # Exige valor mínimo de R$ 10 para evitar capturar badges/cents
            if old and old >= 10.0:
                extra["preco_sem_promocao"] = old
                logger.info(f"[Pichau/Supplementary] Preço sem promoção: R$ {old:.2f}")
                break
        except Exception:
            pass

    # ── Preço principal para base do cálculo Pix ─────────────────────────
    base_price = None
    for selector in _SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            p = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
            if p:
                base_price = p
                break
        except Exception:
            pass

    # Fallback: JSON-LD
    if base_price is None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json as _json
                data = _json.loads(script.string or "")
                raw = data.get("offers", {}).get("price")
                if raw:
                    base_price = normalize_price(str(raw))
                    break
            except Exception:
                pass

    # ── Pix: extrai % de desconto do texto ───────────────────────────────
    # Padrões: "no PIX com 15% desconto", "PIX 15%", "15% no pix"
    pix_re = re.compile(
        r"(?:pix|piix)[^\d]{0,25}(\d{1,2})\s*%|"  # pix ... X%
        r"(\d{1,2})\s*%[^\d]{0,25}(?:pix|desconto.*pix)",
        re.IGNORECASE,
    )
    m = pix_re.search(full_text)
    if m and base_price:
        pct = int(m.group(1) or m.group(2))
        pix = round(base_price * (1 - pct / 100), 2)
        extra["preco_pix"] = pix
        logger.info(f"[Pichau/Supplementary] Pix: R$ {pix:.2f} ({pct}% sobre R$ {base_price:.2f})")

    # ── Parcelamento via seletores ────────────────────────────────────────
    for selector in _INSTALLMENT_SELECTORS:
        try:
            for el in soup.select(selector):
                text = el.get_text(separator=" ", strip=True)
                count, value = parse_installment(text)
                if count and value and count >= 2:
                    extra["parcelas"] = count
                    extra["preco_parcelado"] = value
                    logger.info(f"[Pichau/Supplementary] {count}x R$ {value:.2f}")
                    break
            if extra.get("parcelas"):
                break
        except Exception:
            pass

    # Fallback parcelas: regex no texto
    if not extra.get("parcelas"):
        inst_re = re.compile(r"(\d{1,2})x\s*(?:de\s*)?R?\$?\s*([\d.,]+)", re.IGNORECASE)
        best_count, best_value = None, None
        for m2 in inst_re.finditer(full_text):
            c = int(m2.group(1))
            v = normalize_price(m2.group(2))
            if v and c >= 2 and (best_count is None or c > best_count):
                best_count, best_value = c, v
        if best_count:
            extra["parcelas"] = best_count
            extra["preco_parcelado"] = best_value
            logger.info(f"[Pichau/Supplementary] Parcelamento (regex): {best_count}x R$ {best_value:.2f}")

    return extra


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai preço e campos adicionais de uma página de produto da Pichau.

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
                logger.info(f"[Pichau] Preço R$ {price:.2f} — seletor: '{selector}'")
                break
        except Exception as exc:
            logger.debug(f"[Pichau] Erro no seletor '{selector}': {exc}")

    if price is None:
        logger.warning("[Pichau] Nenhum seletor retornou preço válido.")
        return None

    result: dict = {
        "price": price,
        "preco_sem_promocao": None,
        "preco_parcelado": None,
        "parcelas": None,
        "preco_pix": None,
        "currency": "BRL",
        "confidence": 0.88,
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
                logger.info(f"[Pichau] Preço sem promoção R$ {old:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Pichau] Erro seletor preço antigo '{selector}': {exc}")

    # ── Preço Pix ────────────────────────────────────────────────────────
    for selector in _PIX_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            pix = normalize_price(el.get("content") or el.get_text(separator=" ", strip=True))
            if pix is not None and pix > 0:
                result["preco_pix"] = pix
                logger.info(f"[Pichau] Preço Pix R$ {pix:.2f}")
                break
        except Exception as exc:
            logger.debug(f"[Pichau] Erro seletor Pix '{selector}': {exc}")

    # ── Parcelamento ─────────────────────────────────────────────────────
    for selector in _INSTALLMENT_SELECTORS:
        try:
            for el in soup.select(selector):
                text = el.get_text(separator=" ", strip=True)
                count, value = parse_installment(text)
                if count is not None and value is not None:
                    result["parcelas"] = count
                    result["preco_parcelado"] = value
                    logger.info(f"[Pichau] Parcelamento: {count}x R$ {value:.2f}")
                    break
            if result["parcelas"] is not None:
                break
        except Exception as exc:
            logger.debug(f"[Pichau] Erro seletor parcelamento '{selector}': {exc}")

    return result

