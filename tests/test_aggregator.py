"""
tests/test_aggregator.py
------------------------
Testes unitários para price_tracker.search.aggregator.

Os testes mocam as funções de busca individuais (mercadolivre, zoom,
kabum, pichau, terabyte, amazon) para que nenhuma requisição de rede
seja feita durante a execução.

Execute com:
    python -m pytest tests/
    # ou
    python -m unittest discover tests/
"""

import unittest
from unittest.mock import patch

from price_tracker.search.aggregator import DEFAULT_SOURCES, search


# ---------------------------------------------------------------------------
# Fixtures reutilizáveis
# ---------------------------------------------------------------------------

def _ml_offers():
    return [
        {"name": "RTX 4070 ASUS", "price": 3299.90, "store": "ML/SELLER_A", "url": "https://ml.com/1", "source": "mercadolivre"},
        {"name": "RTX 4070 MSI",  "price": 3499.00, "store": "ML/SELLER_B", "url": "https://ml.com/2", "source": "mercadolivre"},
    ]


def _zoom_offers():
    return [
        {"name": "RTX 4070 Galax", "price": 3350.00, "store": "Zoom/StorX", "url": "https://zoom.com/1", "source": "zoom"},
    ]


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestAggregatorSearch(unittest.TestCase):

    def setUp(self):
        """Faz mock de todas as fontes novas para evitar chamadas de rede."""
        _new_sources = ["kabum", "pichau", "terabyte", "amazon"]
        for src in _new_sources:
            p = patch(f"price_tracker.search.{src}.search", return_value=[])
            p.start()
            self.addCleanup(p.stop)

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_merges_results_from_all_sources(self, mock_ml, mock_zoom):
        """Deve retornar ofertas de todas as fontes combinadas."""
        result = search("RTX 4070")
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["offers"]), 3)

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_sorted_by_price_ascending(self, mock_ml, mock_zoom):
        """Ofertas devem vir ordenadas pelo preço crescente."""
        result = search("RTX 4070")
        prices = [o["price"] for o in result["offers"]]
        self.assertEqual(prices, sorted(prices))

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_min_max_price_computed(self, mock_ml, mock_zoom):
        """min_price e max_price devem refletir a menor e maior oferta."""
        result = search("RTX 4070")
        self.assertAlmostEqual(result["min_price"], 3299.90)
        self.assertAlmostEqual(result["max_price"], 3499.00)

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_single_source_filter(self, mock_ml, mock_zoom):
        """Quando sources=['zoom'], apenas o zoom deve ser consultado."""
        result = search("RTX 4070", sources=["zoom"])
        self.assertEqual(result["total"], 1)
        mock_ml.assert_not_called()
        mock_zoom.assert_called_once()

    @patch("price_tracker.search.zoom.search", return_value=[])
    @patch("price_tracker.search.mercadolivre.search", return_value=[])
    def test_empty_results(self, mock_ml, mock_zoom):
        """Sem ofertas: min_price e max_price devem ser None."""
        result = search("produto inexistente xyz")
        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["min_price"])
        self.assertIsNone(result["max_price"])

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", side_effect=Exception("timeout"))
    def test_source_error_does_not_crash(self, mock_ml, mock_zoom):
        """Se uma fonte lançar exceção, as demais devem continuar funcionando."""
        result = search("RTX 4070")
        # mercadolivre falhou, zoom retornou 1 resultado
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["offers"][0]["source"], "zoom")

    def test_unknown_source_is_skipped(self):
        """Fonte desconhecida deve ser ignorada sem causar erro."""
        with patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers()):
            result = search("RTX 4070", sources=["mercadolivre", "nonexistent_source"])
        self.assertEqual(result["total"], len(_ml_offers()))

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_returns_correct_query(self, mock_ml, mock_zoom):
        """O campo 'query' deve refletir o texto de busca original."""
        result = search("RTX 4070 Super")
        self.assertEqual(result["query"], "RTX 4070 Super")

    @patch("price_tracker.search.zoom.search", return_value=_zoom_offers())
    @patch("price_tracker.search.mercadolivre.search", return_value=_ml_offers())
    def test_max_results_passed_to_sources(self, mock_ml, mock_zoom):
        """max_results deve ser repassado para cada fonte."""
        search("RTX 4070", max_results=5)
        mock_ml.assert_called_once_with("RTX 4070", max_results=5, min_price=None, max_price=None)
        mock_zoom.assert_called_once_with("RTX 4070", max_results=5, min_price=None, max_price=None)

    def test_default_sources_contains_expected(self):
        """DEFAULT_SOURCES deve ter ao menos mercadolivre e zoom."""
        self.assertIn("mercadolivre", DEFAULT_SOURCES)
        self.assertIn("zoom", DEFAULT_SOURCES)


if __name__ == "__main__":
    unittest.main()
