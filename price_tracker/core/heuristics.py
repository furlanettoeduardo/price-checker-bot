"""
heuristics.py
-------------
Camada 3 — extração heurística de preços (último recurso / fallback).

Estratégia:
  1. Busca todos os nós de texto da página com padrão de preço brasileiro
  2. Aplica filtros de exclusão:
       - Parcelamentos  ("12x de R$ 208,32")
       - Preços antigos (elemento com classe "old-price", "preco-de" etc.)
       - Seções irrelevantes (carrossel, rodapé, recomendações…)
  3. Pontua cada candidato por sinais de relevância (tag HTML, classe CSS…)
  4. Retorna o candidato com maior pontuação

Logging:
  - [WARNING] Heurística acionada (sempre que esse módulo é usado)
  - [DEBUG]   Candidatos filtrados e seus motivos
  - [INFO]    Melhor candidato selecionado com score
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from price_tracker.utils.price_parser import (
    is_installment_text,
    is_old_price,
    normalize_price,
)

logger = logging.getLogger(__name__)

# Padrão de preço brasileiro: "R$ 3.899,90" ou "3.899,90" ou "R$389,90"
_PRICE_RE = re.compile(
    r"R\$\s*\d[\d.]*,\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}",
    re.IGNORECASE,
)

# Palavras-chave em id/class dos ancestrais que indicam seção a ignorar
_IGNORE_SECTIONS = {
    "related", "similar", "carousel", "recommendation", "suggest",
    "compare", "also", "previously", "viewed", "shelf", "banner",
    "footer", "header", "nav", "breadcrumb", "menu", "sidebar",
    "installment", "parcel", "parcela",
}

# Classes CSS que sugerem que o elemento é o preço principal
_PRICE_SIGNAL_CLASSES = {
    "price", "preco", "valor", "final", "sale",
    "current", "destaque", "principal", "buy",
}


def extract_price_heuristic(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extração heurística: busca e pontua candidatos de preço no HTML.

    Retorna
    -------
    {
        "price"     : float,
        "currency"  : "BRL",
        "confidence": float,   # 0.0 – 1.0
        "method"    : "heuristic"
    }
    ou None se nenhum candidato plausível for encontrado.
    """
    logger.warning("[Heurística] Iniciando extração heurística de preço.")

    candidates: list[dict] = []

    # Itera sobre todos os nós de texto que contêm padrão de preço
    for text_node in soup.find_all(string=_PRICE_RE):
        parent = text_node.parent
        if not isinstance(parent, Tag):
            continue

        text = text_node.strip()

        # ── Filtros de exclusão ──────────────────────────────────────────
        if is_installment_text(text):
            logger.debug(f"Heurística: ignorando parcelamento — '{text[:60]}'")
            continue

        if is_old_price(parent):
            logger.debug(f"Heurística: ignorando preço antigo — '{text[:60]}'")
            continue

        if _in_ignored_section(parent):
            logger.debug(f"Heurística: ignorando seção irrelevante — '{text[:60]}'")
            continue

        # ── Extração e pontuação ────────────────────────────────────────
        for match in _PRICE_RE.findall(text):
            price = normalize_price(match)
            if price is None:
                continue

            score = _score_candidate(price, parent, text)
            candidates.append({
                "price": price,
                "currency": "BRL",
                "confidence": round(score, 3),
                "method": "heuristic",
                # Campos internos para debug (removidos antes de retornar)
                "_debug_text": text[:80],
                "_debug_tag": parent.name,
                "_debug_classes": parent.get("class", []),
            })

    if not candidates:
        logger.warning("[Heurística] Nenhum candidato de preço encontrado na página.")
        return None

    # Ordena por score (maior primeiro) e retorna o melhor
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    best = candidates[0]

    logger.info(
        f"[Heurística] Melhor candidato: R$ {best['price']:.2f} "
        f"(score={best['confidence']:.2f}, "
        f"tag=<{best['_debug_tag']}>, "
        f"classes={best['_debug_classes']})"
    )

    return {k: v for k, v in best.items() if not k.startswith("_")}


def extract_supplementary_fields(soup: BeautifulSoup) -> dict:
    """
    Extrai campos suplementares de precificacao de qualquer pagina HTML:
      - preco_pix   : preco a vista / Pix
      - preco_parcelado : valor de cada parcela
      - parcelas    : numero de parcelas

    Funciona por regex sobre o texto completo da pagina — independe de
    seletores CSS especificos, portanto cobre qualquer loja.
    Deve ser chamada apos o preco principal ja ter sido encontrado; so
    preenche campos que ainda estejam None.
    """
    result = {"preco_pix": None, "preco_parcelado": None, "parcelas": None}

    full_text = soup.get_text(separator=" ", strip=True)

    # ── Preco Pix / A vista ──────────────────────────────────────────────
    # Padroes: "R$ 1.299,90 no Pix", "Pix R$ 1.299,90", "R$ 1.299,90 a vista"
    _PIX_RE = re.compile(
        r"(?:"
        r"(?:pix|\bvista\b|\ba\svista\b)[^\d]{0,20}R?\$?\s*([\d.,]+)"
        r"|"
        r"R?\$?\s*([\d.,]+)[^\d]{0,30}(?:pix|no\s+pix|\ba\s+vista\b|\bvista\b)"
        r")",
        re.IGNORECASE,
    )
    for m in _PIX_RE.finditer(full_text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        pix = normalize_price(raw)
        # Ignora valores absurdos (< R$ 20 ou > R$ 500.000)
        if pix is not None and pix >= 20.0 and pix <= 500_000:
            result["preco_pix"] = pix
            logger.info(f"[Suplementar] Preco Pix/Vista encontrado: R$ {pix:.2f}")
            break

    # ── Parcelamento ────────────────────────────────────────────────────
    # Padroes: "12x de R$ 208,32", "em 10x de R$389,90", "6X R$ 649,90"
    _INSTALL_RE = re.compile(
        r"(\d{1,2})\s*[xX]\s*(?:de\s+)?R?\$?\s*([\d.,]+)",
    )
    best_count = None
    best_value = None
    for m in _INSTALL_RE.finditer(full_text):
        count = int(m.group(1))
        value = normalize_price(m.group(2))
        # Limites realistas: 2–48 parcelas, valor por parcela R$ 5–50.000
        if value is None or count < 2 or count > 48:
            continue
        if value < 5.0 or value > 50_000:
            continue
        # Prefere o maior numero de parcelas (oferta principal da loja)
        if best_count is None or count > best_count:
            best_count = count
            best_value = value
    if best_count is not None:
        result["parcelas"] = best_count
        result["preco_parcelado"] = best_value
        logger.info(
            f"[Suplementar] Parcelamento encontrado: {best_count}x R$ {best_value:.2f}"
        )

    return result


def _in_ignored_section(element: Tag) -> bool:
    """
    Verifica se o elemento está dentro de uma seção que deve ser ignorada.
    Percorre os ancestrais analisando id e class.
    """
    for ancestor in element.parents:
        if not isinstance(ancestor, Tag):
            continue
        id_val = (ancestor.get("id") or "").lower()
        class_val = " ".join(ancestor.get("class") or []).lower()
        combined = f"{id_val} {class_val}"
        if any(kw in combined for kw in _IGNORE_SECTIONS):
            return True
    return False


def _score_candidate(price: float, element: Tag, text: str) -> float:
    """
    Atribui uma pontuação (0.0 – 1.0) ao candidato com base em sinais
    heurísticos de que é o preço principal do produto.

    Quanto maior o score, mais provável que seja o preço correto.
    """
    score = 0.30  # Pontuação base

    tag = element.name.lower() if element.name else ""
    class_str = " ".join(element.get("class") or []).lower()

    # ── Bônus por tipo de tag ────────────────────────────────────────────
    if tag in ("h1", "h2", "strong", "b"):
        score += 0.25
    elif tag in ("span", "div", "p", "ins"):
        score += 0.10

    # ── Bônus por classe CSS sugestiva de preço principal ───────────────
    if any(kw in class_str for kw in _PRICE_SIGNAL_CLASSES):
        score += 0.20

    # ── Bônus por "R$" explícito no texto ───────────────────────────────
    if re.search(r"R\$", text, re.IGNORECASE):
        score += 0.10

    # ── Penalidade por preço fora da faixa típica de hardware ───────────
    if not (30.0 <= price <= 60_000.0):
        score -= 0.20

    # ── Penalidade leve para preços suspeitosamente redondos ────────────
    if price % 100 == 0 and price > 1000:
        score -= 0.05

    return max(0.0, min(1.0, score))
