"""
price_tracker/scrapers
-----------------------
Scrapers específicos de lojas disponíveis:

  kabum    → price_tracker.scrapers.kabum
  pichau   → price_tracker.scrapers.pichau
  amazon   → price_tracker.scrapers.amazon
  terabyte → price_tracker.scrapers.terabyte

Como adicionar uma nova loja
----------------------------
1. Crie price_tracker/scrapers/<nome_da_loja>.py
2. Implemente a função:

       def extract(soup: BeautifulSoup) -> dict | None:
           # retorne {"price": float, "currency": "BRL", "confidence": float}

3. Adicione o mapeamento em price_tracker/core/store_detector.py → STORE_MAP:

       "nomedoloja": "nome_da_loja",
"""
