"""
price_tracker
-------------
Pacote principal do Price Checker Bot.

Ponto de entrada público:
    from price_tracker import get_product_price
"""

from price_tracker.core.price_extractor import get_product_price

__version__ = "2.0.0"
__all__ = ["get_product_price"]
