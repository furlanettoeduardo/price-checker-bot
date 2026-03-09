"""
scrapers/universal.py
---------------------
Scraper universal — funciona em qualquer loja sem configuração adicional.

Tenta extrair preço principal + campos suplementares (pix, parcelado, parcelas)
usando as seguintes estratégias em ordem de confiabilidade:

  1. Microdata  (itemprop="price")
  2. Meta tags  (Open Graph Commerce / Facebook Product tags)
  3. Shopify    (window.ShopifyAnalytics / JSON do script #ProductJson-*)
  4. VTEX       (__RUNTIME__.product.items[0].sellers[0].commertialOffer)
  5. WooCommerce(script[type="application/ld+json"] do tipo Product)
  6. CSS patterns comuns de frameworks BR (maior cobertura, menor precisão)

Cada método retorna confiança proporcional à sua especificidade.
Os campos de parcelamento e Pix são extraídos por regex sobre o texto completo
da página, aproveitando extract_supplementary_fields() de heuristics.py.
"""

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.core.heuristics import extract_supplementary_fields
from price_tracker.utils.price_parser import normalize_price, parse_installment

logger = logging.getLogger(__name__)

# ── Seletores CSS por framework / padrão comum ───────────────────────────────
# Cada tupla: (seletor, confiança, atributo_ou_None_para_text)
_PRICE_CANDIDATES: list[tuple[str, float, Optional[str]]] = [
    # ── WooCommerce (preço principal em resumo do produto) ──────────────
    (".product .summary .price .woocommerce-Price-amount", 0.92, None),
    (".summary .price .woocommerce-Price-amount",          0.90, None),
    (".product .price .woocommerce-Price-amount",          0.88, None),
    # ── Microdata ─────────────────────────────────────────────────────────
    ("[itemprop='price'][content]",    0.92, "content"),
    ("[itemprop='price']",             0.88, None),
    # ── Meta tags Open Graph Commerce ─────────────────────────────────────
    ("meta[property='product:price:amount']", 0.92, "content"),
    ("meta[property='og:price:amount']",       0.90, "content"),
    # ── IDs semânticos comuns (Shopify, VTEX, lojas BR) ───────────────────
    ("#product-price",                 0.85, None),
    ("#ProductPrice",                  0.85, None),
    ("#precoVenda",                    0.85, None),
    ("#preco-venda",                   0.85, None),
    ("#prod-new-price",                0.85, None),
    ("#price",                         0.80, None),
    ("#Price",                         0.80, None),
    ("#price_display",                 0.82, None),
    # ── Classes semânticas comuns ─────────────────────────────────────────
    (".product__price",                0.82, None),
    (".product-price",                 0.82, None),
    (".price--main",                   0.82, None),
    (".price-item--sale",              0.82, None),   # Shopify
    (".price-item--regular",           0.78, None),   # Shopify
    (".price__current",                0.80, None),
    (".current-price",                 0.80, None),
    (".sale-price",                    0.78, None),
    (".final-price",                   0.80, None),
    (".preco-por",                     0.82, None),
    (".preco_por",                     0.82, None),
    (".preco-venda",                   0.82, None),
    (".val_principal",                 0.82, None),
    (".skuBestPrice",                  0.85, None),   # VTEX
    (".best-price",                    0.80, None),
    ("[class*='bestPrice']",           0.80, None),
    ("[class*='BestPrice']",           0.80, None),
    ("[class*='finalPrice']",          0.82, None),
    ("[class*='priceBox']",            0.75, None),
    ("[class*='product-price']",       0.75, None),
    ("[class*='ProductPrice']",        0.75, None),
    # ── Preços em elementos de destaque ───────────────────────────────────
    ("h1[class*='price']",             0.85, None),
    ("h2[class*='price']",             0.82, None),
    ("strong[class*='price']",         0.80, None),
    ("span[class*='price']:not([class*='old']):not([class*='was']):not([class*='de'])", 0.72, None),
]

_OLD_PRICE_SELECTORS: list[str] = [
    "[itemprop='price'][class*='old']",
    ".price--compare",                # Shopify
    ".price__compare",
    ".compare-at-price",
    ".regular-price del",
    ".preco-de",
    ".preco_de",
    ".skuListPrice",                  # VTEX
    "[class*='oldPrice']",
    "[class*='old-price']",
    "[class*='OldPrice']",
    "del[class*='price']",
    "s[class*='price']",
    ".line-through",
]

_PIX_SELECTORS: list[str] = [
    "[class*='pix']",
    "[class*='Pix']",
    "[id*='pix']",
    "[class*='vista']",
    "[class*='avista']",
    "[class*='a-vista']",
]

_INSTALLMENT_SELECTORS: list[str] = [
    "[class*='installment']",
    "[class*='parcel']",
    "[class*='Parcel']",
    "[class*='parcela']",
    "[class*='Parcela']",
    "[id*='parcel']",
    ".skuInstallments",               # VTEX
    "[class*='Installment']",
]


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Estratégia 1 — Microdata + Meta tags + CSS comum                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _extract_css(soup: BeautifulSoup) -> Optional[dict]:
    for selector, confidence, attr in _PRICE_CANDIDATES:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            raw = el.get(attr) if attr else el.get_text(separator=" ", strip=True)
            if not raw:
                continue
            price = normalize_price(str(raw))
            if price is not None:
                logger.info(
                    f"[Universal/CSS] R$ {price:.2f} — seletor: '{selector}' "
                    f"(confiança: {confidence})"
                )
                return {"price": price, "currency": "BRL", "confidence": confidence}
        except Exception as exc:
            logger.debug(f"[Universal/CSS] Erro em '{selector}': {exc}")
    return None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Estratégia 2 — Shopify (JSON embutido em <script>)                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _extract_shopify(soup: BeautifulSoup) -> Optional[dict]:
    """
    Shopify injeta dados do produto em:
    - <script id="ProductJson-*" type="application/json">
    - window.ShopifyAnalytics.meta.product  (em <script> inline)

    O campo `price` está em centavos (ex: 139900 = R$ 1.399,00).
    """
    # Script JSON com id
    for script in soup.find_all("script", type="application/json"):
        sid = script.get("id", "")
        if not ("ProductJson" in sid or "product-json" in sid):
            continue
        try:
            data = json.loads(script.string or "")
            price_cents = (
                data.get("price")
                or (data.get("variants") or [{}])[0].get("price")
            )
            if price_cents:
                price = round(int(price_cents) / 100, 2)
                compare = (
                    data.get("compare_at_price")
                    or (data.get("variants") or [{}])[0].get("compare_at_price")
                )
                old = round(int(compare) / 100, 2) if compare else None
                logger.info(f"[Universal/Shopify-JSON] R$ {price:.2f}")
                return {
                    "price": price,
                    "preco_sem_promocao": old if old and old > price else None,
                    "currency": "BRL",
                    "confidence": 0.93,
                }
        except Exception as exc:
            logger.debug(f"[Universal/Shopify-JSON] Parse error: {exc}")

    # window.ShopifyAnalytics inline
    _SHOPIFY_ANALYTICS_RE = re.compile(
        r"ShopifyAnalytics\.meta\s*=\s*(\{.*?\});", re.DOTALL
    )
    for script in soup.find_all("script"):
        text = script.string or ""
        m = _SHOPIFY_ANALYTICS_RE.search(text)
        if not m:
            continue
        try:
            meta = json.loads(m.group(1))
            price_cents = meta.get("product", {}).get("price")
            if price_cents:
                price = round(int(price_cents) / 100, 2)
                logger.info(f"[Universal/ShopifyAnalytics] R$ {price:.2f}")
                return {"price": price, "currency": "BRL", "confidence": 0.91}
        except Exception as exc:
            logger.debug(f"[Universal/ShopifyAnalytics] Parse error: {exc}")

    return None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Estratégia 3 — VTEX (__RUNTIME__ / __STATE__)                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _extract_vtex(soup: BeautifulSoup) -> Optional[dict]:
    """
    VTEX injeta __RUNTIME__ e/ou __STATE__ em scripts inline.
    O preço está em:
      __RUNTIME__.product.items[0].sellers[0].commertialOffer.Price
    ou em queryData de __STATE__.
    """
    _RUNTIME_RE = re.compile(r"window\.__RUNTIME__\s*=\s*(\{.*?\})(?:;|$)", re.DOTALL)
    _STATE_RE   = re.compile(r"window\.__STATE__\s*=\s*(\{.*?\})(?:;|$)", re.DOTALL)

    for script in soup.find_all("script"):
        text = script.string or ""

        for pattern, label in ((_RUNTIME_RE, "RUNTIME"), (_STATE_RE, "STATE")):
            m = pattern.search(text)
            if not m:
                continue
            try:
                data = json.loads(m.group(1))
                # Navega estrutura VTEX
                items = (
                    data.get("product", {})
                        .get("items", [{}])
                )
                offer = (
                    items[0]
                    .get("sellers", [{}])[0]
                    .get("commertialOffer", {})
                )
                price = offer.get("Price") or offer.get("price")
                old   = offer.get("ListPrice") or offer.get("listPrice")
                if price:
                    logger.info(f"[Universal/VTEX-{label}] R$ {price:.2f}")
                    return {
                        "price": float(price),
                        "preco_sem_promocao": float(old) if old and float(old) > float(price) else None,
                        "currency": "BRL",
                        "confidence": 0.93,
                    }
            except Exception as exc:
                logger.debug(f"[Universal/VTEX-{label}] Parse error: {exc}")

    return None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Estratégia 4 — WooCommerce (variation_form / wc_add_to_cart_params)    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _extract_woocommerce(soup: BeautifulSoup) -> Optional[dict]:
    """
    WooCommerce injeta os dados de variação em atributo data-product_variations
    de um <form class="variations_form"> ou como wc_add_to_cart_params.
    """
    form = soup.select_one("form.variations_form[data-product_variations]")
    if form:
        try:
            variations = json.loads(form.get("data-product_variations", "[]"))
            if variations:
                v = variations[0]
                price = normalize_price(str(v.get("display_price", "")))
                old   = normalize_price(str(v.get("display_regular_price", "")))
                if price:
                    logger.info(f"[Universal/WooCommerce-variations] R$ {price:.2f}")
                    return {
                        "price": price,
                        "preco_sem_promocao": old if old and old > price else None,
                        "currency": "BRL",
                        "confidence": 0.92,
                    }
        except Exception as exc:
            logger.debug(f"[Universal/WooCommerce-variations] Parse error: {exc}")

    # Preço simples sem variações
    el = soup.select_one(".woocommerce-Price-amount.amount bdi")
    if el:
        raw = el.get_text(separator=" ", strip=True)
        price = normalize_price(raw)
        if price:
            logger.info(f"[Universal/WooCommerce-simple] R$ {price:.2f}")
            return {"price": price, "currency": "BRL", "confidence": 0.88}

    return None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Campos suplementares (pix, parcelado, parcelas)                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _extract_supplementary(soup: BeautifulSoup, price: float) -> dict:
    """
    Extrai pix, parcelado e parcelas combinando:
    1. Seletores CSS específicos de pix/installment
    2. extract_supplementary_fields() (regex no texto completo)
    """
    result: dict = {"preco_pix": None, "preco_parcelado": None, "parcelas": None}

    # Pix via seletores
    for selector in _PIX_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue
            pix = normalize_price(el.get_text(separator=" ", strip=True))
            if pix and 0 < pix < price:   # Pix sempre menor que o preço base
                result["preco_pix"] = pix
                logger.info(f"[Universal/Supplementary] Pix R$ {pix:.2f}")
                break
        except Exception:
            pass

    # Parcelamento via seletores
    for selector in _INSTALLMENT_SELECTORS:
        try:
            for el in soup.select(selector):
                text = el.get_text(separator=" ", strip=True)
                count, value = parse_installment(text)
                if count and value and count >= 2:
                    result["parcelas"] = count
                    result["preco_parcelado"] = value
                    logger.info(f"[Universal/Supplementary] {count}x R$ {value:.2f}")
                    break
            if result["parcelas"]:
                break
        except Exception:
            pass

    # Fallback: regex no texto completo
    fallback = extract_supplementary_fields(soup)
    for field, value in fallback.items():
        if result.get(field) is None and value is not None:
            result[field] = value

    return result


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Ponto de entrada: extract()                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Tenta extrair preço e campos suplementares de qualquer página de produto.

    Ordem de tentativa:
      1. Shopify JSON  (mais confiável quando disponível)
      2. VTEX __RUNTIME__ / __STATE__
      3. WooCommerce variation_form / wc-price
      4. Microdata + Meta tags + CSS patterns comuns

    Retorna o mesmo formato dos scrapers dedicados:
    {
        "price"             : float,
        "preco_sem_promocao": float | None,
        "preco_parcelado"   : float | None,
        "parcelas"          : int   | None,
        "preco_pix"         : float | None,
        "currency"          : "BRL",
        "confidence"        : float,
    }
    """
    result: Optional[dict] = None

    for strategy_fn, label in (
        (_extract_shopify,     "Shopify"),
        (_extract_vtex,        "VTEX"),
        (_extract_woocommerce, "WooCommerce"),
        (_extract_css,         "CSS"),
    ):
        result = strategy_fn(soup)
        if result and result.get("price"):
            logger.info(f"[Universal] Estratégia {label} bem-sucedida.")
            break

    if not result or not result.get("price"):
        logger.debug("[Universal] Nenhuma estratégia retornou preço.")
        return None

    # Preenche campos de parcelamento e Pix
    supplementary = _extract_supplementary(soup, result["price"])
    for field, value in supplementary.items():
        if result.get(field) is None:
            result[field] = value

    # Preço sem promoção via seletores CSS genéricos (se ainda não preenchido)
    if result.get("preco_sem_promocao") is None:
        for selector in _OLD_PRICE_SELECTORS:
            try:
                el = soup.select_one(selector)
                if el is None:
                    continue
                old = normalize_price(
                    el.get("content") or el.get_text(separator=" ", strip=True)
                )
                if old and old > result["price"]:
                    result["preco_sem_promocao"] = old
                    logger.info(f"[Universal] Preço sem promoção R$ {old:.2f}")
                    break
            except Exception:
                pass

    result.setdefault("preco_sem_promocao", None)
    result.setdefault("preco_parcelado", None)
    result.setdefault("parcelas", None)
    result.setdefault("preco_pix", None)

    return result
