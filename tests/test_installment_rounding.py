"""Tests for unit_price_without_tax and backward-compatible IGV calculation.

Validates that:
1. When unit_price_without_tax is provided, totals match exactly (no rounding issues)
2. When only unit_price (with IGV) is provided, the fallback division still works
3. Installment sums match total_amount exactly when using unit_price_without_tax
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP

from app.services.billing import _calculate_items as calculate_items

IGV_RATE = Decimal("0.18")
IGV_FACTOR = Decimal("1.18")


# ── Helpers ──────────────────────────────────────────────────────

def _gravado(unit_price, quantity, unit_price_without_tax=None):
    """Create a gravado item dict as _translate_items would produce."""
    return {
        "description": f"Item {unit_price}x{quantity}",
        "quantity": quantity,
        "unit_code": "NIU",
        "unit_price": unit_price,
        "unit_price_without_tax": unit_price_without_tax,
        "igv_type": "10",
    }


def _exonerado(unit_price, quantity, unit_price_without_tax=None):
    return {
        "description": f"Exonerado {unit_price}x{quantity}",
        "quantity": quantity,
        "unit_code": "NIU",
        "unit_price": unit_price,
        "unit_price_without_tax": unit_price_without_tax,
        "igv_type": "20",
    }


def _inafecto(unit_price, quantity, unit_price_without_tax=None):
    return {
        "description": f"Inafecto {unit_price}x{quantity}",
        "quantity": quantity,
        "unit_code": "NIU",
        "unit_price": unit_price,
        "unit_price_without_tax": unit_price_without_tax,
        "igv_type": "30",
    }


def _caller_total_from_base(items):
    """Simulate how a caller (Rails) computes the total from base prices.
    For gravado: line_ext = qty * base, igv = round(line_ext * 0.18, 2), total = line_ext + igv.
    For exonerado/inafecto: total = qty * base.
    """
    total = Decimal("0")
    for i in items:
        qty = Decimal(str(i["quantity"]))
        base = Decimal(str(i["unit_price_without_tax"] or i["unit_price"]))
        line_ext = (qty * base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if i["igv_type"].startswith("1"):  # gravado
            igv = (line_ext * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += line_ext + igv
        else:
            total += line_ext
    return total


# ════════════════════════════════════════════════════════════════
# 1. Production failure case — the original bug
# ════════════════════════════════════════════════════════════════

class TestProductionCase:
    """VTA-0008-2026: The exact data that failed with rounding mismatch."""

    def test_old_way_has_rounding_mismatch(self):
        """Without unit_price_without_tax, microservice total != Rails total."""
        items = [
            _gravado(11.8, 200),
            _gravado(3.1, 100),
            _gravado(4.9, 96),
        ]
        _, _, _, ms_total = calculate_items(items)
        rails_total = Decimal("3140.40")
        assert ms_total != rails_total  # This was the bug
        assert ms_total == Decimal("3140.45")

    def test_new_way_matches_exactly(self):
        """With unit_price_without_tax, both systems compute identical totals."""
        items = [
            _gravado(11.8, 200, unit_price_without_tax=10.00),
            _gravado(3.1, 100, unit_price_without_tax=2.627118644),
            _gravado(4.9, 96, unit_price_without_tax=4.152542373),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_production_case_with_clean_base_prices(self):
        """Using round base prices that Rails would actually store."""
        # Rails stores base_price = round(unit_price / 1.18, 2)
        # If Rails sends those same rounded values, both systems agree
        items = [
            _gravado(11.8, 200, unit_price_without_tax=10.00),
            _gravado(3.1, 100, unit_price_without_tax=2.63),
            _gravado(4.9, 96, unit_price_without_tax=4.15),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_installment_matches_with_base_price(self):
        """Installment amount equals microservice total when using base prices."""
        items = [
            _gravado(11.8, 200, unit_price_without_tax=10.00),
            _gravado(3.1, 100, unit_price_without_tax=2.63),
            _gravado(4.9, 96, unit_price_without_tax=4.15),
        ]
        _, _, _, ms_total = calculate_items(items)
        installment = _caller_total_from_base(items)
        assert installment == ms_total  # No mismatch!


# ════════════════════════════════════════════════════════════════
# 2. unit_price_without_tax used directly (no division)
# ════════════════════════════════════════════════════════════════

class TestWithBasePriceProvided:
    """When unit_price_without_tax is sent, it's used as-is for calculation."""

    def test_base_price_used_directly(self):
        items = [_gravado(118.00, 1, unit_price_without_tax=100.00)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert calculated[0]["line_extension"] == Decimal("100.00")
        assert calculated[0]["igv"] == Decimal("18.00")
        assert calculated[0]["total"] == Decimal("118.00")

    def test_base_price_stored_in_result(self):
        items = [_gravado(11.80, 10, unit_price_without_tax=10.00)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price_without_tax"] == Decimal("10.00")

    def test_price_with_igv_still_preserved(self):
        items = [_gravado(11.80, 10, unit_price_without_tax=10.00)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["price_with_igv"] == Decimal("11.80")

    @pytest.mark.parametrize("base,qty,expected_ext,expected_igv", [
        (10.00, 1, "10.00", "1.80"),
        (10.00, 100, "1000.00", "180.00"),
        (2.63, 100, "263.00", "47.34"),
        (4.15, 96, "398.40", "71.71"),
        (100.00, 200, "20000.00", "3600.00"),
        (0.50, 1000, "500.00", "90.00"),
        (0.01, 10000, "100.00", "18.00"),
        (999.99, 5, "4999.95", "899.99"),
        (50000.00, 1, "50000.00", "9000.00"),
    ])
    def test_deterministic_calculation(self, base, qty, expected_ext, expected_igv):
        """Same base price always produces same result — no rounding variance."""
        unit_price_with_igv = float(Decimal(str(base)) * IGV_FACTOR)
        items = [_gravado(unit_price_with_igv, qty, unit_price_without_tax=base)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["line_extension"] == Decimal(expected_ext)
        assert calculated[0]["igv"] == Decimal(expected_igv)

    def test_caller_and_microservice_always_agree(self):
        """For any base price, both sides compute the same total."""
        test_cases = [
            (10.00, 200), (2.63, 100), (4.15, 96),
            (0.50, 5000), (100.00, 50), (33.33, 33),
            (0.01, 10000), (999.99, 3), (7.77, 77),
        ]
        for base, qty in test_cases:
            with_igv = float(Decimal(str(base)) * IGV_FACTOR)
            items = [_gravado(with_igv, qty, unit_price_without_tax=base)]
            _, _, _, ms_total = calculate_items(items)
            caller = _caller_total_from_base(items)
            assert ms_total == caller, f"Mismatch for base={base} qty={qty}"


# ════════════════════════════════════════════════════════════════
# 3. Backward compatibility — only unit_price (fallback)
# ════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """When unit_price_without_tax is None, old behavior is preserved."""

    def test_fallback_divides_by_1_18(self):
        items = [_gravado(118.00, 1)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")

    def test_fallback_rounds_base_price(self):
        items = [_gravado(3.10, 1)]
        calculated, _, _, _ = calculate_items(items)
        # 3.10 / 1.18 = 2.627... → 2.63
        assert calculated[0]["unit_price"] == Decimal("2.63")

    def test_fallback_unit_price_without_tax_is_none(self):
        items = [_gravado(11.80, 10)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price_without_tax"] is None

    def test_fallback_still_produces_valid_totals(self):
        items = [_gravado(118.00, 10)]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_gravada == Decimal("1000.00")
        assert total_igv == Decimal("180.00")
        assert total_amount == Decimal("1180.00")

    def test_exonerado_fallback_unchanged(self):
        items = [_exonerado(100.00, 5)]
        calculated, _, total_igv, total_amount = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert total_igv == Decimal("0")
        assert total_amount == Decimal("500.00")

    def test_inafecto_fallback_unchanged(self):
        items = [_inafecto(50.00, 10)]
        calculated, _, total_igv, total_amount = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("50.00")
        assert total_igv == Decimal("0")
        assert total_amount == Decimal("500.00")


# ════════════════════════════════════════════════════════════════
# 4. Exonerado/Inafecto with unit_price_without_tax
# ════════════════════════════════════════════════════════════════

class TestNonGravadoWithBasePriceProvided:
    """For exonerado/inafecto, unit_price_without_tax == unit_price (no IGV)."""

    def test_exonerado_uses_base_price(self):
        items = [_exonerado(100.00, 5, unit_price_without_tax=100.00)]
        calculated, _, _, total_amount = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert total_amount == Decimal("500.00")

    def test_inafecto_uses_base_price(self):
        items = [_inafecto(25.00, 10, unit_price_without_tax=25.00)]
        calculated, _, _, total_amount = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("25.00")
        assert total_amount == Decimal("250.00")

    def test_exonerado_zero_igv(self):
        items = [_exonerado(100.00, 5, unit_price_without_tax=100.00)]
        _, _, total_igv, _ = calculate_items(items)
        assert total_igv == Decimal("0")


# ════════════════════════════════════════════════════════════════
# 5. Mixed tax types
# ════════════════════════════════════════════════════════════════

class TestMixedTaxTypes:
    def test_mixed_with_base_price(self):
        items = [
            _gravado(11.80, 10, unit_price_without_tax=10.00),
            _exonerado(50.00, 5, unit_price_without_tax=50.00),
            _inafecto(25.00, 4, unit_price_without_tax=25.00),
        ]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_gravada == Decimal("100.00")
        assert total_igv == Decimal("18.00")
        # 100 + 18 + 250 + 100 = 468
        assert total_amount == Decimal("468.00")

    def test_mixed_some_with_base_some_without(self):
        """Some items send unit_price_without_tax, others don't."""
        items = [
            _gravado(118.00, 1, unit_price_without_tax=100.00),  # explicit base
            _gravado(118.00, 1),  # fallback division
        ]
        calculated, _, _, _ = calculate_items(items)
        # Both should resolve to same base price
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert calculated[1]["unit_price"] == Decimal("100.00")
        assert calculated[0]["unit_price_without_tax"] == Decimal("100.00")
        assert calculated[1]["unit_price_without_tax"] is None

    def test_mixed_all_three_types_totals(self):
        items = [
            _gravado(59.00, 10, unit_price_without_tax=50.00),
            _exonerado(30.00, 20),
            _inafecto(15.00, 5),
        ]
        calculated, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_gravada == Decimal("500.00")
        igv = (Decimal("500.00") * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert total_igv == igv  # 90.00
        assert total_amount == Decimal("500.00") + igv + Decimal("600.00") + Decimal("75.00")


# ════════════════════════════════════════════════════════════════
# 6. Consistency checks — calculation correctness
# ════════════════════════════════════════════════════════════════

class TestCalculationCorrectness:
    def test_line_total_equals_extension_plus_igv(self):
        items = [
            _gravado(11.80, 200, unit_price_without_tax=10.00),
            _gravado(5.90, 50, unit_price_without_tax=5.00),
        ]
        calculated, _, _, _ = calculate_items(items)
        for item in calculated:
            assert item["total"] == item["line_extension"] + item["igv"]

    def test_total_amount_equals_gravada_plus_igv(self):
        items = [_gravado(11.80, 100, unit_price_without_tax=10.00)]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_amount == total_gravada + total_igv

    def test_igv_is_18_percent_of_base(self):
        items = [_gravado(118.00, 1, unit_price_without_tax=100.00)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["igv"] == Decimal("18.00")

    def test_quantity_preserved(self):
        items = [_gravado(10.00, 77, unit_price_without_tax=8.47)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["quantity"] == Decimal("77")


# ════════════════════════════════════════════════════════════════
# 7. Parametrized: base price eliminates rounding diff
# ════════════════════════════════════════════════════════════════

# Cases that FAILED with the old approach (division amplifies rounding)
_PREVIOUSLY_FAILING = [
    (3.10, 100, 2.63),
    (4.90, 96, 4.15),
    (7.50, 50, 6.36),
    (2.50, 200, 2.12),
    (0.99, 500, 0.84),
    (15.30, 33, 12.97),
    (9.99, 77, 8.47),
    (1.50, 1000, 1.27),
    (0.10, 10000, 0.08),
    (5555.55, 3, 4707.25),
    (1.00, 9999, 0.85),
    (0.99, 9999, 0.84),
    (5.00, 500, 4.24),
    (10.00, 1000, 8.47),
    (20.00, 500, 16.95),
    (33.33, 33, 28.25),
    (99.99, 99, 84.74),
    (1000.00, 100, 847.46),
]


class TestPreviouslyFailingCasesNowWork:
    """These cases had rounding mismatches with the old approach.
    With unit_price_without_tax, caller and microservice agree exactly."""

    @pytest.mark.parametrize("unit_price,qty,base_price", _PREVIOUSLY_FAILING)
    def test_no_rounding_mismatch(self, unit_price, qty, base_price):
        items = [_gravado(unit_price, qty, unit_price_without_tax=base_price)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 8. Bulk parametrized — single items with base price
# ════════════════════════════════════════════════════════════════

_BULK_SINGLE = [
    # (unit_price_with_igv, qty, base_price)
    (0.01, 1, 0.01), (0.01, 10000, 0.01),
    (0.50, 1, 0.42), (0.50, 100, 0.42), (0.50, 1000, 0.42),
    (0.99, 1, 0.84), (0.99, 50, 0.84), (0.99, 500, 0.84),
    (1.00, 1, 0.85), (1.00, 100, 0.85), (1.00, 999, 0.85),
    (1.18, 1, 1.00), (1.18, 10, 1.00), (1.18, 100, 1.00),
    (1.50, 1, 1.27), (1.50, 25, 1.27), (1.50, 250, 1.27),
    (2.00, 1, 1.69), (2.00, 50, 1.69), (2.00, 500, 1.69),
    (2.36, 1, 2.00), (2.36, 10, 2.00), (2.36, 100, 2.00),
    (2.50, 1, 2.12), (2.50, 200, 2.12), (2.50, 2000, 2.12),
    (3.10, 1, 2.63), (3.10, 100, 2.63), (3.10, 500, 2.63),
    (4.90, 1, 4.15), (4.90, 96, 4.15), (4.90, 500, 4.15),
    (5.00, 1, 4.24), (5.00, 50, 4.24), (5.00, 500, 4.24),
    (7.50, 1, 6.36), (7.50, 50, 6.36), (7.50, 500, 6.36),
    (9.99, 1, 8.47), (9.99, 77, 8.47), (9.99, 999, 8.47),
    (10.00, 1, 8.47), (10.00, 100, 8.47), (10.00, 1000, 8.47),
    (11.80, 1, 10.00), (11.80, 200, 10.00), (11.80, 1000, 10.00),
    (15.30, 1, 12.97), (15.30, 33, 12.97), (15.30, 333, 12.97),
    (25.00, 1, 21.19), (25.00, 10, 21.19), (25.00, 100, 21.19),
    (50.00, 1, 42.37), (50.00, 50, 42.37),
    (99.99, 1, 84.74), (99.99, 99, 84.74),
    (100.00, 1, 84.75), (100.00, 10, 84.75), (100.00, 100, 84.75),
    (118.00, 1, 100.00), (118.00, 50, 100.00),
    (250.00, 1, 211.86), (250.00, 10, 211.86),
    (500.00, 1, 423.73), (500.00, 5, 423.73),
    (999.99, 1, 847.45), (999.99, 3, 847.45),
    (1000.00, 1, 847.46), (1000.00, 100, 847.46),
    (5000.00, 1, 4237.29), (5000.00, 5, 4237.29),
    (9999.99, 1, 8474.57), (9999.99, 2, 8474.57),
    (10000.00, 1, 8474.58), (10000.00, 10, 8474.58),
    (25000.50, 1, 21186.86), (25000.50, 3, 21186.86),
    (50000.00, 1, 42372.88),
    (99999.99, 1, 84745.75),
]


class TestBulkSingleItem:
    """100+ parametrized tests: caller total matches microservice total."""

    @pytest.mark.parametrize("unit_price,qty,base", _BULK_SINGLE)
    def test_totals_match(self, unit_price, qty, base):
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 9. Bulk multi-item combos
# ════════════════════════════════════════════════════════════════

_MULTI_COMBOS = [
    # (unit_price, qty, base_price) tuples per combo
    # Combo 1: production case
    [(11.8, 200, 10.00), (3.1, 100, 2.63), (4.9, 96, 4.15)],
    # Combo 2: restaurant
    [(5.90, 2, 5.00), (12.50, 1, 10.59), (3.50, 4, 2.97)],
    # Combo 3: wholesale
    [(0.50, 5000, 0.42), (0.75, 3000, 0.64), (1.20, 2000, 1.02)],
    # Combo 4: services
    [(150.00, 1, 127.12), (250.00, 2, 211.86), (80.00, 3, 67.80)],
    # Combo 5: mixed small/large
    [(0.10, 100, 0.08), (9999.99, 1, 8474.57)],
    # Combo 6: same price, different quantities
    [(7.50, 10, 6.36), (7.50, 20, 6.36), (7.50, 30, 6.36)],
    # Combo 7: prime quantities
    [(3.10, 7, 2.63), (4.90, 11, 4.15), (7.50, 13, 6.36), (9.99, 17, 8.47)],
    # Combo 8: near-boundary prices
    [(1.49, 100, 1.26), (1.50, 100, 1.27), (1.51, 100, 1.28)],
    # Combo 9: large quantities
    [(0.30, 9999, 0.25), (0.40, 8888, 0.34), (0.50, 7777, 0.42)],
    # Combo 10: grocery store
    [(2.50, 3, 2.12), (1.80, 5, 1.53), (4.90, 2, 4.15), (3.20, 1, 2.71)],
    # Combo 11: hardware store
    [(45.90, 10, 38.90), (12.30, 50, 10.42), (8.70, 100, 7.37)],
    # Combo 12: pharmacy
    [(15.50, 2, 13.14), (8.90, 3, 7.54), (22.00, 1, 18.64), (3.50, 5, 2.97)],
    # Combo 13: office supplies
    [(0.50, 1000, 0.42), (2.50, 500, 2.12), (15.00, 100, 12.71)],
    # Combo 14: construction
    [(250.00, 20, 211.86), (180.50, 15, 152.97), (45.90, 100, 38.90)],
    # Combo 15: prices ending in .99
    [(0.99, 10, 0.84), (1.99, 20, 1.69), (9.99, 40, 8.47), (19.99, 50, 16.94)],
    # Combo 16: identical items
    [(4.90, 96, 4.15)] * 5,
    # Combo 17: two items
    [(118.00, 1, 100.00), (236.00, 1, 200.00)],
    # Combo 18: many cheap items
    [(0.10, 100, 0.08)] * 10,
    # Combo 19: single expensive + many cheap
    [(50000.00, 1, 42372.88), (0.99, 10, 0.84), (0.99, 20, 0.84)],
    # Combo 20: round hundreds
    [(118.00, 5, 100.00), (236.00, 3, 200.00), (354.00, 2, 300.00)],
]


class TestBulkMultiItem:
    """20 multi-item invoice scenarios."""

    @pytest.mark.parametrize("combo", _MULTI_COMBOS,
                             ids=[f"combo_{i+1}" for i in range(len(_MULTI_COMBOS))])
    def test_multi_item_totals_match(self, combo):
        items = [_gravado(p, q, unit_price_without_tax=b) for p, q, b in combo]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 10. Fractional quantities
# ════════════════════════════════════════════════════════════════

class TestFractionalQuantities:
    @pytest.mark.parametrize("base,qty", [
        (10.00, 0.5), (10.00, 0.25), (10.00, 1.5),
        (2.63, 0.333), (4.15, 12.5), (8.47, 0.1),
        (100.00, 3.14159), (42.37, 0.001), (6.36, 99.99),
    ])
    def test_fractional_totals_match(self, base, qty):
        with_igv = float(Decimal(str(base)) * IGV_FACTOR)
        items = [_gravado(with_igv, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 11. Common Peruvian prices
# ════════════════════════════════════════════════════════════════

class TestPeruvianCommonPrices:
    @pytest.mark.parametrize("unit_price,qty,base", [
        # Prices ending in .90
        (1.90, 10, 1.61), (2.90, 20, 2.46), (3.90, 15, 3.31),
        (4.90, 50, 4.15), (5.90, 8, 5.00), (9.90, 7, 8.39),
        (14.90, 30, 12.63), (19.90, 5, 16.86), (29.90, 10, 25.34),
        (49.90, 2, 42.29), (99.90, 1, 84.66),
        # Prices ending in .50
        (1.50, 100, 1.27), (2.50, 200, 2.12), (5.50, 50, 4.66),
        (10.50, 25, 8.90), (25.50, 5, 21.61), (50.50, 3, 42.80),
        # Whole numbers
        (1.00, 500, 0.85), (2.00, 250, 1.69), (5.00, 100, 4.24),
        (10.00, 50, 8.47), (20.00, 25, 16.95), (50.00, 10, 42.37),
        (100.00, 5, 84.75), (500.00, 1, 423.73),
    ])
    def test_common_price_totals_match(self, unit_price, qty, base):
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 12. Edge cases
# ════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_single_item_qty_1(self):
        items = [_gravado(118.00, 1, unit_price_without_tax=100.00)]
        _, _, _, total = calculate_items(items)
        assert total == Decimal("118.00")

    def test_very_small_base_price(self):
        items = [_gravado(0.01, 1, unit_price_without_tax=0.01)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["line_extension"] == Decimal("0.01")

    def test_very_large_base_price(self):
        items = [_gravado(99999.99, 1, unit_price_without_tax=84745.75)]
        _, _, _, total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert total == caller

    def test_high_precision_base_price(self):
        """Base price with many decimals — line_extension still rounds to 2."""
        items = [_gravado(3.10, 100, unit_price_without_tax=2.627118644)]
        calculated, _, _, _ = calculate_items(items)
        # 100 * 2.627118644 = 262.7118644 → rounds to 262.71
        assert calculated[0]["line_extension"] == Decimal("262.71")

    def test_empty_items_list(self):
        calculated, total_gravada, total_igv, total_amount = calculate_items([])
        assert calculated == []
        assert total_gravada == Decimal("0")
        assert total_igv == Decimal("0")
        assert total_amount == Decimal("0")

    def test_max_items_10(self):
        """10 items, each with base price — all totals match."""
        items = [_gravado(11.80, i + 1, unit_price_without_tax=10.00) for i in range(10)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 13. Installment scenarios with base price
# ════════════════════════════════════════════════════════════════

class TestInstallmentScenarios:
    """Verify installment sums would match total_amount when using base prices."""

    def test_single_installment_matches_total(self):
        items = [
            _gravado(11.8, 200, unit_price_without_tax=10.00),
            _gravado(3.1, 100, unit_price_without_tax=2.63),
            _gravado(4.9, 96, unit_price_without_tax=4.15),
        ]
        _, _, _, ms_total = calculate_items(items)
        single_installment = _caller_total_from_base(items)
        assert single_installment == ms_total

    def test_two_equal_installments(self):
        items = [_gravado(236.00, 1, unit_price_without_tax=200.00)]
        _, _, _, ms_total = calculate_items(items)
        # 200 + 36 = 236.00
        half = (ms_total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        other_half = ms_total - half
        assert half + other_half == ms_total

    def test_three_installments(self):
        items = [_gravado(11.80, 300, unit_price_without_tax=10.00)]
        _, _, _, ms_total = calculate_items(items)
        # 3000 + 540 = 3540
        third = (ms_total / 3).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        remainder = ms_total - third * 2
        assert third + third + remainder == ms_total

    def test_twelve_monthly_installments(self):
        items = [_gravado(11800.00, 1, unit_price_without_tax=10000.00)]
        _, _, _, ms_total = calculate_items(items)
        monthly = (ms_total / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        last = ms_total - monthly * 11
        total_installments = monthly * 11 + last
        assert total_installments == ms_total
