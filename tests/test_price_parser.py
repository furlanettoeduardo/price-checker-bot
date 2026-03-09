"""
tests/test_price_parser.py
--------------------------
Testes unitários para price_tracker.utils.price_parser.

Execute com:
    python -m pytest tests/
    # ou
    python -m unittest discover tests/
"""

import unittest

from price_tracker.utils.price_parser import (
    is_installment_text,
    is_old_price,
    normalize_price,
)


class TestNormalizePrice(unittest.TestCase):
    """Testa a conversão de strings de preço brasileiras para float."""

    def test_full_br_format(self):
        """R$ 3.899,90 → 3899.90"""
        self.assertAlmostEqual(normalize_price("R$ 3.899,90"), 3899.90)

    def test_no_symbol(self):
        """1.234,56 → 1234.56"""
        self.assertAlmostEqual(normalize_price("1.234,56"), 1234.56)

    def test_comma_only_decimal(self):
        """389,90 → 389.90"""
        self.assertAlmostEqual(normalize_price("389,90"), 389.90)

    def test_no_decimal(self):
        """R$ 1500 → 1500.0"""
        self.assertAlmostEqual(normalize_price("R$ 1500"), 1500.0)

    def test_international_dot_decimal(self):
        """3899.90 → 3899.90 (formato sem milhar)"""
        self.assertAlmostEqual(normalize_price("3899.90"), 3899.90)

    def test_nbsp_whitespace(self):
        """R$\xa02.099,90 → 2099.90 (espaço não-separável)"""
        self.assertAlmostEqual(normalize_price("R$\xa02.099,90"), 2099.90)

    def test_with_surrounding_text(self):
        """Extrai número mesmo com texto ao redor"""
        self.assertAlmostEqual(normalize_price("Por apenas R$ 999,99!"), 999.99)

    def test_empty_string(self):
        self.assertIsNone(normalize_price(""))

    def test_none_equivalent(self):
        self.assertIsNone(normalize_price("Preço indisponível"))

    def test_letters_only(self):
        self.assertIsNone(normalize_price("Consulte"))


class TestIsInstallmentText(unittest.TestCase):
    """Testa a detecção de textos de parcelamento."""

    def test_typical_installment(self):
        self.assertTrue(is_installment_text("12x de R$ 208,32"))

    def test_uppercase_x(self):
        self.assertTrue(is_installment_text("10X R$389,90"))

    def test_no_space(self):
        self.assertTrue(is_installment_text("6xR$649,90"))

    def test_normal_price(self):
        self.assertFalse(is_installment_text("R$ 3.899,90"))

    def test_empty(self):
        self.assertFalse(is_installment_text(""))


class TestIsOldPrice(unittest.TestCase):
    """Testa a detecção de elementos de preço antigo por classe CSS."""

    def _make_tag(self, classes: list[str]):
        """Cria um Tag fake com as classes especificadas."""
        from bs4 import BeautifulSoup
        cls_str = " ".join(classes)
        soup = BeautifulSoup(f'<span class="{cls_str}">R$ 4.299,00</span>', "lxml")
        return soup.find("span")

    def test_old_price_class(self):
        tag = self._make_tag(["price-old"])
        self.assertTrue(is_old_price(tag))

    def test_preco_de_class(self):
        tag = self._make_tag(["preco-de", "text-strike"])
        self.assertTrue(is_old_price(tag))

    def test_normal_price_class(self):
        tag = self._make_tag(["finalPrice", "highlight"])
        self.assertFalse(is_old_price(tag))

    def test_no_classes(self):
        tag = self._make_tag([])
        self.assertFalse(is_old_price(tag))


if __name__ == "__main__":
    unittest.main()
