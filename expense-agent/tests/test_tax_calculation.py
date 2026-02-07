import pytest
from handlers.sheets_handler import calculate_tax


class TestTaxCalculation:
    def test_basic_11000(self):
        supply, tax = calculate_tax(11000)
        assert supply == 10000
        assert tax == 1000
        assert supply + tax == 11000

    def test_sample_8800(self):
        supply, tax = calculate_tax(8800)
        assert supply == 8000
        assert tax == 800
        assert supply + tax == 8800

    def test_sample_4900(self):
        supply, tax = calculate_tax(4900)
        assert supply + tax == 4900

    def test_sample_22400(self):
        supply, tax = calculate_tax(22400)
        assert supply + tax == 22400

    def test_sum_always_equals_total(self):
        """모든 금액에서 supply + tax == total 이 성립해야 함"""
        for amount in range(100, 100001, 100):
            supply, tax = calculate_tax(amount)
            assert supply + tax == amount, f"Failed for amount={amount}"

    def test_zero(self):
        supply, tax = calculate_tax(0)
        assert supply == 0
        assert tax == 0

    def test_supply_always_positive(self):
        for amount in [100, 1000, 5000, 10000, 50000]:
            supply, tax = calculate_tax(amount)
            assert supply > 0
            assert tax >= 0
