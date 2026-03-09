"""
store_detector.py
-----------------
Detecta automaticamente a loja a partir da URL do produto.

Usa tldextract (quando instalado) para máxima precisão na extração do domínio.
Caso contrário, usa análise de string simples como fallback.

Para adicionar uma nova loja, basta inserir no dicionário STORE_MAP:
    "nomedadomínio": "id_interno_do_scraper"
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mapeamento: fragmento do domínio → identificador do scraper
# O fragmento é comparado com .lower() do domínio extraído da URL
STORE_MAP: dict[str, str] = {
    "kabum":           "kabum",
    "pichau":          "pichau",
    "terabyteshop":    "terabyte",
    "terabyte":        "terabyte",
    "amazon":          "amazon",
}


def detect_store(url: str) -> Optional[str]:
    """
    Retorna o identificador interno da loja (usado para importar o scraper),
    ou None se a loja não for reconhecida.

    Exemplos:
        "https://www.kabum.com.br/produto/..."  → "kabum"
        "https://www.pichau.com.br/..."         → "pichau"
        "https://www.amazon.com.br/..."         → "amazon"
        "https://www.desconhecida.com.br/..."   → None
    """
    domain = _extract_domain(url)
    if not domain:
        return None

    for key, store_id in STORE_MAP.items():
        if key in domain:
            logger.debug(f"Loja detectada: '{store_id}' (domínio: '{domain}')")
            return store_id

    logger.debug(f"Loja não reconhecida para domínio: '{domain}'")
    return None


def register_custom_stores(stores: dict) -> None:
    """
    Mescla lojas customizadas (vindas do config.json) no STORE_MAP em tempo
    de execução. Pode ser chamado múltiplas vezes sem problemas.
    """
    STORE_MAP.update(stores)


def _extract_domain(url: str) -> str:
    """
    Extrai o componente do domínio da URL.
    Tenta usar tldextract para precisão; usa fallback simples se não instalado.
    """
    try:
        import tldextract
        extracted = tldextract.extract(url)
        return extracted.domain.lower()
    except ImportError:
        return _simple_domain(url)


def _simple_domain(url: str) -> str:
    """
    Extrai o domínio de forma simplificada sem dependências externas.

    Estratégia: remove protocolo, pega o host, divide por ponto,
    e retorna a parte relevante (penúltima parte antes do TLD).

    www.kabum.com.br    → ["www", "kabum", "com", "br"] → "kabum"
    www.amazon.com.br   → ["www", "amazon", "com", "br"] → "amazon"
    terabyteshop.com.br → ["terabyteshop", "com", "br"]  → "terabyteshop"
    """
    # Remove protocolo
    without_scheme = url.split("//")[-1]
    # Pega apenas o host (sem path, query e fragment)
    host = without_scheme.split("/")[0].split("?")[0].split("#")[0]
    parts = host.split(".")

    # Para TLDs duplos (como .com.br), o domínio está em parts[-3];
    # para TLDs simples (como .com), está em parts[-2].
    if len(parts) >= 3:
        return parts[-3].lower()
    if len(parts) == 2:
        return parts[0].lower()
    return host.lower()
