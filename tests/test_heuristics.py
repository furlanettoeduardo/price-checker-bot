"""
tests/test_heuristics.py
------------------------
Testes unitários para price_tracker.core.heuristics.

Execute com:
    python -m pytest tests/
    # ou
    python -m unittest discover tests/
"""

import unittest

from bs4 import BeautifulSoup

from price_tracker.core.heuristics import extract_price_heuristic


def _soup(body: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body>{body}</body></html>", "lxml")


class TestHeuristics(unittest.TestCase):

    def test_detects_price_in_span(self):
        """Preço em span com classe 'price' deve ser detectado."""
        result = extract_price_heuristic(
            _soup('<span class="price">R$ 2.499,90</span>')
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 2499.90)
        self.assertEqual(result["method"], "heuristic")
        self.assertIn("confidence", result)

    def test_detects_price_in_strong(self):
        """Preço em <strong> deve ter score favorável."""
        result = extract_price_heuristic(
            _soup('<strong>R$ 1.899,90</strong>')
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 1899.90)

    def test_ignores_installment(self):
        """Parcelamento '12x de R$ 208,32' deve ser filtrado."""
        result = extract_price_heuristic(
            _soup('<span>12x de R$ 208,32</span>')
        )
        self.assertIsNone(result)

    def test_ignores_related_section(self):
        """Preço dentro de seção 'related' deve ser ignorado."""
        result = extract_price_heuristic(
            _soup('<div id="related"><span>R$ 999,00</span></div>')
        )
        self.assertIsNone(result)

    def test_ignores_carousel_section(self):
        """Preço dentro de seção 'carousel' deve ser ignorado."""
        result = extract_price_heuristic(
            _soup('<div class="carousel"><p>R$ 1.299,90</p></div>')
        )
        self.assertIsNone(result)

    def test_ignores_old_price_class(self):
        """Elemento com classe 'price-old' deve ser ignorado."""
        result = extract_price_heuristic(
            _soup('<span class="price-old">R$ 4.299,00</span>')
        )
        self.assertIsNone(result)

    def test_prefers_main_price_over_secondary(self):
        """Quando há dois preços, o principal deve ter maior score."""
        html = """
            <div id="related"><span>R$ 899,00</span></div>
            <h1 class="price">R$ 3.499,90</h1>
        """
        result = extract_price_heuristic(_soup(html))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 3499.90)

    def test_empty_page(self):
        """Página sem preços retorna None."""
        result = extract_price_heuristic(_soup("<p>Sem preço aqui.</p>"))
        self.assertIsNone(result)

    def test_confidence_is_float(self):
        """Confidence deve ser float entre 0 e 1."""
        result = extract_price_heuristic(
            _soup('<span class="price">R$ 500,00</span>')
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result["confidence"], float)
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_no_internal_debug_keys(self):
        """O resultado não deve conter chaves internas (_debug_*)."""
        result = extract_price_heuristic(
            _soup('<span class="price">R$ 799,99</span>')
        )
        if result:
            for key in result:
                self.assertFalse(key.startswith("_"), f"Chave interna exposta: {key}")


if __name__ == "__main__":
    unittest.main()
