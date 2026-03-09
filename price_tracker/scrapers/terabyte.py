"""
scrapers/terabyte.py
--------------------
Scraper específico para terabyteshop.com.br.

A Terabyte Shop usa estrutura HTML mais tradicional com IDs e classes
semânticas, o que torna os seletores relativamente estáveis.
"""

import logging
import re
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


def extract_supplementary(soup: BeautifulSoup) -> dict:
    """
    Extrai campos suplementares específicos da Terabyte Shop.

    Estratégia em duas camadas:
    1) Seletores CSS diretos no HTML estático (presentes mesmo sem executar JS):
       - del / [class*='old-price']  → preco_sem_promocao
       - p.valVista / p.val-prod     → preco_pix (valor real)
       - span.valParc                → preco_parcelado (total no cartão)
       - span.nParc / .Parc         → parcelas / valor-por-parcela
    2) Extração via regex no script JS inline (fallback ou JS-rendered).
    """
    extra: dict = {}

    # Preço base do produto (para filtrar preço riscado de relacionados)
    base_price = None
    for sel in _SELECTORS + [".val-prod", "p.valVista", "[itemprop='price']"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            base_price = normalize_price(el.get_text(separator=" ", strip=True))
            if base_price:
                break
        except Exception:
            pass

    # ── 1) Seletores CSS diretos no HTML estático ──────────────────────────

    # Preço sem promoção (riscado)
    candidates = []
    for sel in [".prod-old-price span", "#prod-old-price", "[class*='old-price']", ".preco-antigo", "del", "s"]:
        try:
            for el in soup.select(sel):
                old = normalize_price(el.get_text(separator=" ", strip=True))
                if old and old > 0:
                    candidates.append(old)
        except Exception:
            pass

    if candidates:
        if base_price:
            candidates = [c for c in candidates if c > base_price]
        if candidates:
            chosen = min(candidates)
            extra["preco_sem_promocao"] = chosen
            logger.info(f"[Terabyte/Supplementary] Preço sem promoção: R$ {chosen:.2f}")

    # Preço pix/vista (classe valVista presente no HTML estático)
    for sel in ["p.valVista", ".val-prod.valVista", "[class*='valVista']",
                "#prod-pix-price span", ".prod-pix-price span", "[class*='pix-price']"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            pix = normalize_price(el.get_text(separator=" ", strip=True))
            if pix and pix > 0:
                extra["preco_pix"] = pix
                logger.info(f"[Terabyte/Supplementary] Pix (CSS): R$ {pix:.2f}")
                break
        except Exception:
            pass

    # Total no cartão (valParc presente no HTML estático)
    for sel in ["span.valParc", "[class*='valParc']"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            total = normalize_price(el.get_text(separator=" ", strip=True))
            if total and total > 0:
                extra["preco_cartao"] = total
                break
        except Exception:
            pass

    # Valor por parcela (Parc)
    for sel in ["span.Parc", ".Parc"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            v = normalize_price(el.get_text(separator=" ", strip=True))
            if v and v > 0:
                extra["preco_parcelado"] = v
                break
        except Exception:
            pass

    # Número de parcelas (nParc)
    for sel in ["span.nParc", "[class*='nParc']"]:
        try:
            el = soup.select_one(sel)
            if el is None:
                continue
            m = re.search(r"(\d+)", el.get_text(strip=True))
            if m:
                extra["parcelas"] = int(m.group(1))
                break
        except Exception:
            pass

    if extra.get("parcelas") and extra.get("preco_parcelado"):
        logger.info(f"[Terabyte/Supplementary] {extra['parcelas']}x R$ {extra['preco_parcelado']:.2f}")

    # ── 2) Fallback: extrai do script JS inline ──────────────────────────
    for script in soup.find_all("script"):
        text = script.string or ""
        if ".valParc" not in text and ".nParc" not in text:
            continue

        # Parcelas: $('.nParc').text('12x');
        if not extra.get("parcelas"):
            m = re.search(r"\.nParc'\)\.text\('(\d+)x'\)", text)
            if m:
                extra["parcelas"] = int(m.group(1))

        # Valor por parcela: $('.Parc').text('R$ 67,16');
        if not extra.get("preco_parcelado"):
            m = re.search(r"\.Parc'\)\.text\('([^']+)'\)", text)
            if m:
                v = normalize_price(m.group(1))
                if v:
                    extra["preco_parcelado"] = v

        # Total no cartão: $('.valParc').text('R$ 805,87');
        if not extra.get("preco_cartao"):
            m = re.search(r"\.valParc'\)\.text\('([^']+)'\)", text)
            if m:
                total = normalize_price(m.group(1))
                if total:
                    extra["preco_cartao"] = total

        # Pix/boleto: $('.val-prod').text('R$ 684,99') — valor já é pix/à vista.
        # O label '15% de desconto' descreve o desconto já aplicado;
        # não recalcular.
        if not extra.get("preco_pix"):
            price_m = re.search(r"\.val-prod'\)\.text\('([^']+)'\)", text)
            if price_m:
                base = normalize_price(price_m.group(1))
                if base:
                    extra["preco_pix"] = base
                    logger.info(f"[Terabyte/Supplementary] Pix (JS): R$ {base:.2f} (val-prod direto)")
        break  # script encontrado — sai do loop

    # ── Fallback CSS para parcelas (quando JS executou via Playwright) ────
    if not extra.get("parcelas"):
        for selector in _INSTALLMENT_SELECTORS:
            try:
                for el in soup.select(selector):
                    text = el.get_text(separator=" ", strip=True)
                    count, value = parse_installment(text)
                    if count and value and count >= 2:
                        extra["parcelas"] = count
                        extra["preco_parcelado"] = value
                        logger.info(f"[Terabyte/Supplementary] CSS: {count}x R$ {value:.2f}")
                        break
                if extra.get("parcelas"):
                    break
            except Exception:
                pass

    if extra.get("parcelas"):
        logger.info(f"[Terabyte/Supplementary] {extra['parcelas']}x R$ {extra.get('preco_parcelado')}")

    return extra


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

