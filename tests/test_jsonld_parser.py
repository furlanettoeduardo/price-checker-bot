"""
tests/test_jsonld_parser.py
---------------------------
Testes unitários para price_tracker.core.jsonld_parser.

Execute com:
    python -m pytest tests/
    # ou
    python -m unittest discover tests/
"""

import unittest

from bs4 import BeautifulSoup

from price_tracker.core.jsonld_parser import extract_price_jsonld


def _soup(json_body: str) -> BeautifulSoup:
    """Helper: cria BeautifulSoup com um único bloco JSON-LD."""
    html = (
        '<html><head>'
        f'<script type="application/ld+json">{json_body}</script>'
        '</head><body></body></html>'
    )
    return BeautifulSoup(html, "lxml")


class TestJsonLdParser(unittest.TestCase):

    def test_product_with_price(self):
        """Caso básico: Product com offers.price."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","name":"RTX 4070","offers":{"price":"3899.90","priceCurrency":"BRL"}}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 3899.90)
        self.assertEqual(result["currency"], "BRL")
        self.assertEqual(result["method"], "jsonld")
        self.assertGreaterEqual(result["confidence"], 0.95)

    def test_product_low_price(self):
        """Fallback para lowPrice quando price está ausente."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","offers":{"lowPrice":"2799.00","priceCurrency":"BRL"}}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 2799.00)

    def test_product_list_format(self):
        """JSON-LD como lista de objetos."""
        result = extract_price_jsonld(_soup(
            '[{"@type":"WebPage"},{"@type":"Product","offers":{"price":"1299.00"}}]'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 1299.00)

    def test_graph_format(self):
        """JSON-LD com @graph contendo o Product."""
        result = extract_price_jsonld(_soup(
            '{"@graph":[{"@type":"Organization"},{"@type":"Product","offers":{"price":"4599.99"}}]}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 4599.99)

    def test_br_price_string(self):
        """Preço no formato de string com vírgula (que algumas lojas usam)."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","offers":{"price":"3.499,90","priceCurrency":"BRL"}}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 3499.90)

    def test_offers_as_list(self):
        """offers como lista (AggregateOffer): usa o primeiro elemento."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","offers":[{"price":"999.00"},{"price":"1099.00"}]}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 999.00)

    def test_type_as_list(self):
        """@type como lista de tipos."""
        result = extract_price_jsonld(_soup(
            '{"@type":["Product","Thing"],"offers":{"price":"750.00"}}'
        ))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 750.00)

    def test_no_jsonld(self):
        """Página sem bloco JSON-LD retorna None."""
        soup = BeautifulSoup("<html><body><p>Sem JSON-LD</p></body></html>", "lxml")
        self.assertIsNone(extract_price_jsonld(soup))

    def test_jsonld_not_product(self):
        """JSON-LD do tipo Organization não é Product — retorna None."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Organization","name":"Kabum"}'
        ))
        self.assertIsNone(result)

    def test_invalid_json(self):
        """JSON inválido no script é ignorado silenciosamente."""
        soup = BeautifulSoup(
            '<html><head><script type="application/ld+json">{invalid json}</script></head></html>',
            "lxml",
        )
        self.assertIsNone(extract_price_jsonld(soup))

    def test_product_without_offers(self):
        """Product sem campo 'offers' retorna None."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","name":"Produto sem preço"}'
        ))
        self.assertIsNone(result)

    def test_default_currency_brl(self):
        """Quando priceCurrency ausente, assume BRL."""
        result = extract_price_jsonld(_soup(
            '{"@type":"Product","offers":{"price":"500.00"}}'
        ))
        self.assertIsNotNone(result)
        self.assertEqual(result["currency"], "BRL")


if __name__ == "__main__":
    unittest.main()
