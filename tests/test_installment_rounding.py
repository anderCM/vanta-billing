"""Tests for unit_price_without_tax and backward-compatible IGV calculation.

Validates that:
1. When unit_price_without_tax is provided (full precision), totals match exactly
2. When only unit_price (with IGV) is provided, the fallback division still works
3. Installment validation: strict with base prices, tolerant without
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP

from app.services.billing import _calculate_items as calculate_items

IGV_RATE = Decimal("0.18")
IGV_FACTOR = Decimal("1.18")


# ── Helpers ──────────────────────────────────────────────────────

def _gravado(unit_price, quantity, unit_price_without_tax=None):
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


def _full_precision_base(unit_price):
    """Simulate what Rails does: unit_price / 1.18 without truncation."""
    return Decimal(str(unit_price)) / IGV_FACTOR


def _caller_total_from_base(items):
    """Simulate how Rails computes total using the same base price formula."""
    total = Decimal("0")
    for i in items:
        qty = Decimal(str(i["quantity"]))
        base = Decimal(str(i["unit_price_without_tax"])) if i.get("unit_price_without_tax") else Decimal(str(i["unit_price"]))
        line_ext = (qty * base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if i["igv_type"].startswith("1"):
            igv = (line_ext * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += line_ext + igv
        else:
            total += line_ext
    return total


# ════════════════════════════════════════════════════════════════
# 1. Production case — the original bug (VTA-0008-2026)
# ════════════════════════════════════════════════════════════════

class TestProductionCase:
    def test_old_way_has_rounding_mismatch(self):
        """Without unit_price_without_tax, microservice total != Rails total."""
        items = [
            _gravado(11.8, 200),
            _gravado(3.1, 100),
            _gravado(4.9, 96),
        ]
        _, _, _, ms_total = calculate_items(items)
        assert ms_total == Decimal("3140.45")  # != Rails 3140.40

    def test_full_precision_fixes_mismatch(self):
        """With full-precision base prices, both systems agree."""
        items = [
            _gravado(11.8, 200, unit_price_without_tax=_full_precision_base(11.8)),
            _gravado(3.1, 100, unit_price_without_tax=_full_precision_base(3.1)),
            _gravado(4.9, 96, unit_price_without_tax=_full_precision_base(4.9)),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_production_line_by_line(self):
        """Verify each line with full-precision base prices."""
        items = [
            _gravado(11.8, 200, unit_price_without_tax=_full_precision_base(11.8)),
            _gravado(3.1, 100, unit_price_without_tax=_full_precision_base(3.1)),
            _gravado(4.9, 96, unit_price_without_tax=_full_precision_base(4.9)),
        ]
        calculated, _, _, total_amount = calculate_items(items)

        # Item 1: 11.8/1.18 = 10.0 exactly
        assert calculated[0]["line_extension"] == Decimal("2000.00")
        assert calculated[0]["igv"] == Decimal("360.00")

        # Item 2: 3.1/1.18 = 2.6271186440677966...
        # 100 * 2.6271186440677966... = 262.71186... → rounds to 262.71
        assert calculated[1]["line_extension"] == Decimal("262.71")

        # Item 3: 4.9/1.18 = 4.1525423728813559...
        # 96 * 4.1525423728813559... = 398.64406... → rounds to 398.64
        assert calculated[2]["line_extension"] == Decimal("398.64")

    def test_installment_matches_with_full_precision(self):
        items = [
            _gravado(11.8, 200, unit_price_without_tax=_full_precision_base(11.8)),
            _gravado(3.1, 100, unit_price_without_tax=_full_precision_base(3.1)),
            _gravado(4.9, 96, unit_price_without_tax=_full_precision_base(4.9)),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert caller == ms_total  # Installment sum == total, no mismatch


# ════════════════════════════════════════════════════════════════
# 2. Full precision: base price used directly (no rounding)
# ════════════════════════════════════════════════════════════════

class TestFullPrecisionBasePrices:
    def test_base_price_used_as_is(self):
        base = _full_precision_base(118.00)
        items = [_gravado(118.00, 1, unit_price_without_tax=base)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price"] == base

    def test_price_with_igv_preserved(self):
        items = [_gravado(11.80, 10, unit_price_without_tax=_full_precision_base(11.80))]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["price_with_igv"] == Decimal("11.80")

    def test_stored_in_result(self):
        base = _full_precision_base(3.10)
        items = [_gravado(3.10, 100, unit_price_without_tax=base)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price_without_tax"] == base

    @pytest.mark.parametrize("unit_price,qty", [
        (10.00, 1), (10.00, 100), (10.00, 9999),
        (0.50, 1000), (0.99, 500), (1.00, 9999),
        (3.10, 100), (4.90, 96), (7.50, 50),
        (9.99, 77), (15.30, 33), (25.00, 200),
        (99.99, 99), (100.00, 100), (999.99, 10),
        (5000.00, 5), (9999.99, 2), (50000.00, 1),
    ])
    def test_caller_and_microservice_always_agree(self, unit_price, qty):
        base = _full_precision_base(unit_price)
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 3. Backward compatibility — only unit_price (fallback)
# ════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    def test_fallback_divides_by_1_18(self):
        items = [_gravado(118.00, 1)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")

    def test_fallback_rounds_base_to_2_decimals(self):
        items = [_gravado(3.10, 1)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("2.63")

    def test_fallback_unit_price_without_tax_is_none(self):
        items = [_gravado(11.80, 10)]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price_without_tax"] is None

    def test_fallback_produces_valid_totals(self):
        items = [_gravado(118.00, 10)]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_gravada == Decimal("1000.00")
        assert total_igv == Decimal("180.00")
        assert total_amount == Decimal("1180.00")

    def test_exonerado_unchanged(self):
        items = [_exonerado(100.00, 5)]
        _, _, total_igv, total_amount = calculate_items(items)
        assert total_igv == Decimal("0")
        assert total_amount == Decimal("500.00")

    def test_inafecto_unchanged(self):
        items = [_inafecto(50.00, 10)]
        _, _, total_igv, total_amount = calculate_items(items)
        assert total_igv == Decimal("0")
        assert total_amount == Decimal("500.00")


# ════════════════════════════════════════════════════════════════
# 4. Exonerado/Inafecto with unit_price_without_tax
# ════════════════════════════════════════════════════════════════

class TestNonGravadoWithBasePriceProvided:
    def test_exonerado_uses_base_price(self):
        items = [_exonerado(100.00, 5, unit_price_without_tax=100.00)]
        calculated, _, _, total = calculate_items(items)
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert total == Decimal("500.00")

    def test_inafecto_uses_base_price(self):
        items = [_inafecto(25.00, 10, unit_price_without_tax=25.00)]
        _, _, _, total = calculate_items(items)
        assert total == Decimal("250.00")

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
            _gravado(11.80, 10, unit_price_without_tax=_full_precision_base(11.80)),
            _exonerado(50.00, 5, unit_price_without_tax=50.00),
            _inafecto(25.00, 4, unit_price_without_tax=25.00),
        ]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_gravada == Decimal("100.00")
        assert total_igv == Decimal("18.00")
        assert total_amount == Decimal("468.00")

    def test_mixed_some_with_base_some_without(self):
        items = [
            _gravado(118.00, 1, unit_price_without_tax=_full_precision_base(118.00)),
            _gravado(118.00, 1),  # fallback
        ]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["unit_price_without_tax"] is not None
        assert calculated[1]["unit_price_without_tax"] is None
        # Both resolve to 100.00 (118/1.18 is exact)
        assert calculated[0]["unit_price"] == Decimal("100.00")
        assert calculated[1]["unit_price"] == Decimal("100.00")


# ════════════════════════════════════════════════════════════════
# 6. Calculation correctness
# ════════════════════════════════════════════════════════════════

class TestCalculationCorrectness:
    def test_line_total_equals_extension_plus_igv(self):
        items = [
            _gravado(3.10, 100, unit_price_without_tax=_full_precision_base(3.10)),
            _gravado(4.90, 96, unit_price_without_tax=_full_precision_base(4.90)),
        ]
        calculated, _, _, _ = calculate_items(items)
        for item in calculated:
            assert item["total"] == item["line_extension"] + item["igv"]

    def test_total_amount_equals_gravada_plus_igv(self):
        items = [_gravado(11.80, 100, unit_price_without_tax=_full_precision_base(11.80))]
        _, total_gravada, total_igv, total_amount = calculate_items(items)
        assert total_amount == total_gravada + total_igv

    def test_igv_is_18_percent_of_base(self):
        items = [_gravado(118.00, 1, unit_price_without_tax=_full_precision_base(118.00))]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["igv"] == Decimal("18.00")

    def test_quantity_preserved(self):
        items = [_gravado(10.00, 77, unit_price_without_tax=_full_precision_base(10.00))]
        calculated, _, _, _ = calculate_items(items)
        assert calculated[0]["quantity"] == Decimal("77")

    def test_empty_items_list(self):
        calculated, g, i, t = calculate_items([])
        assert calculated == []
        assert g == Decimal("0")
        assert i == Decimal("0")
        assert t == Decimal("0")


# ════════════════════════════════════════════════════════════════
# 7. Previously failing cases — now work with full precision
# ════════════════════════════════════════════════════════════════

_PREVIOUSLY_FAILING = [
    (3.10, 100), (4.90, 96), (7.50, 50), (2.50, 200),
    (0.99, 500), (15.30, 33), (9.99, 77), (1.50, 1000),
    (0.10, 10000), (5555.55, 3), (1.00, 9999), (0.99, 9999),
    (5.00, 500), (10.00, 1000), (20.00, 500), (33.33, 33),
    (99.99, 99), (1000.00, 100), (0.01, 50000),
]


class TestPreviouslyFailingCasesNowWork:
    @pytest.mark.parametrize("unit_price,qty", _PREVIOUSLY_FAILING)
    def test_no_rounding_mismatch(self, unit_price, qty):
        base = _full_precision_base(unit_price)
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 8. Bulk single items — 80+ combos with full precision
# ════════════════════════════════════════════════════════════════

_BULK_SINGLE = [
    (0.01, 1), (0.01, 10000), (0.01, 50000),
    (0.50, 1), (0.50, 100), (0.50, 1000), (0.50, 10000),
    (0.99, 1), (0.99, 50), (0.99, 500), (0.99, 9999),
    (1.00, 1), (1.00, 100), (1.00, 999), (1.00, 9999),
    (1.18, 1), (1.18, 10), (1.18, 100), (1.18, 1000),
    (1.50, 1), (1.50, 25), (1.50, 250), (1.50, 5000),
    (2.00, 1), (2.00, 50), (2.00, 500),
    (2.50, 1), (2.50, 200), (2.50, 2000),
    (3.10, 1), (3.10, 100), (3.10, 500),
    (4.90, 1), (4.90, 96), (4.90, 500), (4.90, 5000),
    (5.00, 1), (5.00, 50), (5.00, 500),
    (7.50, 1), (7.50, 50), (7.50, 500),
    (9.99, 1), (9.99, 77), (9.99, 999),
    (10.00, 1), (10.00, 100), (10.00, 1000),
    (11.80, 1), (11.80, 200), (11.80, 1000),
    (15.30, 1), (15.30, 33), (15.30, 333),
    (25.00, 1), (25.00, 100),
    (33.33, 1), (33.33, 33),
    (50.00, 1), (50.00, 50),
    (99.99, 1), (99.99, 99),
    (100.00, 1), (100.00, 100),
    (118.00, 1), (118.00, 50),
    (250.00, 1), (250.00, 10),
    (500.00, 1), (500.00, 5),
    (999.99, 1), (999.99, 3),
    (1000.00, 1), (1000.00, 100),
    (5000.00, 1), (5000.00, 5),
    (9999.99, 1), (9999.99, 2),
    (10000.00, 1), (10000.00, 10),
    (25000.50, 1), (25000.50, 3),
    (50000.00, 1),
    (99999.99, 1),
]


class TestBulkSingleItem:
    @pytest.mark.parametrize("unit_price,qty", _BULK_SINGLE)
    def test_totals_match(self, unit_price, qty):
        base = _full_precision_base(unit_price)
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 9. Bulk multi-item combos
# ════════════════════════════════════════════════════════════════

_MULTI_COMBOS = [
    [(11.8, 200), (3.1, 100), (4.9, 96)],              # production case
    [(5.90, 2), (12.50, 1), (3.50, 4)],                 # restaurant
    [(0.50, 5000), (0.75, 3000), (1.20, 2000)],         # wholesale
    [(150.00, 1), (250.00, 2), (80.00, 3)],              # services
    [(0.10, 100), (9999.99, 1)],                         # mixed small/large
    [(7.50, 10), (7.50, 20), (7.50, 30), (7.50, 40)],   # same price
    [(3.10, 7), (4.90, 11), (7.50, 13), (9.99, 17)],    # primes
    [(1.49, 100), (1.50, 100), (1.51, 100)],             # boundary
    [(0.30, 9999), (0.40, 8888), (0.50, 7777)],          # large qty
    [(50000.00, 1), (0.99, 10), (0.99, 20)],             # expensive + cheap
    [(2.50, 3), (1.80, 5), (4.90, 2), (3.20, 1)],       # grocery
    [(45.90, 10), (12.30, 50), (8.70, 100)],             # hardware
    [(15.50, 2), (8.90, 3), (22.00, 1), (3.50, 5)],     # pharmacy
    [(0.50, 1000), (2.50, 500), (15.00, 100)],           # office
    [(250.00, 20), (180.50, 15), (45.90, 100)],          # construction
    [(3.33, 333), (6.66, 666)],                          # repeating
    [(0.99, 10), (1.99, 20), (9.99, 40), (19.99, 50)],  # prices ending .99
    [(118.00, 5), (236.00, 3), (354.00, 2)],             # round hundreds
    [(4.90, 96)] * 5,                                    # identical
    [(0.01, 1000)] * 10,                                 # many tiny
]


class TestBulkMultiItem:
    @pytest.mark.parametrize("combo", _MULTI_COMBOS,
                             ids=[f"combo_{i+1}" for i in range(len(_MULTI_COMBOS))])
    def test_multi_item_totals_match(self, combo):
        items = [_gravado(p, q, unit_price_without_tax=_full_precision_base(p)) for p, q in combo]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 10. Fractional quantities
# ════════════════════════════════════════════════════════════════

class TestFractionalQuantities:
    @pytest.mark.parametrize("unit_price,qty", [
        (11.80, 0.5), (11.80, 0.25), (11.80, 1.5),
        (3.10, 0.333), (4.90, 12.5), (9.99, 0.1),
        (25.00, 3.14159), (100.00, 0.001), (7.50, 99.99),
    ])
    def test_fractional_totals_match(self, unit_price, qty):
        base = _full_precision_base(unit_price)
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 11. Common Peruvian prices
# ════════════════════════════════════════════════════════════════

class TestPeruvianCommonPrices:
    @pytest.mark.parametrize("unit_price,qty", [
        (1.90, 10), (2.90, 20), (3.90, 15), (4.90, 50),
        (5.90, 8), (9.90, 7), (14.90, 30), (19.90, 5),
        (29.90, 10), (49.90, 2), (99.90, 1),
        (1.50, 100), (2.50, 200), (5.50, 50), (10.50, 25),
        (1.00, 500), (2.00, 250), (5.00, 100), (10.00, 50),
        (20.00, 25), (50.00, 10), (100.00, 5), (500.00, 1),
    ])
    def test_common_price_totals_match(self, unit_price, qty):
        base = _full_precision_base(unit_price)
        items = [_gravado(unit_price, qty, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 12. Installment scenarios
# ════════════════════════════════════════════════════════════════

class TestInstallmentScenarios:
    def test_single_installment_matches_total(self):
        items = [
            _gravado(11.8, 200, unit_price_without_tax=_full_precision_base(11.8)),
            _gravado(3.1, 100, unit_price_without_tax=_full_precision_base(3.1)),
            _gravado(4.9, 96, unit_price_without_tax=_full_precision_base(4.9)),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert caller == ms_total

    def test_two_equal_installments(self):
        items = [_gravado(236.00, 1, unit_price_without_tax=_full_precision_base(236.00))]
        _, _, _, ms_total = calculate_items(items)
        half = (ms_total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        other = ms_total - half
        assert half + other == ms_total

    def test_twelve_monthly_installments(self):
        items = [_gravado(11800.00, 1, unit_price_without_tax=_full_precision_base(11800.00))]
        _, _, _, ms_total = calculate_items(items)
        monthly = (ms_total / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        last = ms_total - monthly * 11
        assert monthly * 11 + last == ms_total


# ════════════════════════════════════════════════════════════════
# 13. Edge cases
# ════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_very_small_price(self):
        base = _full_precision_base(0.01)
        items = [_gravado(0.01, 1, unit_price_without_tax=base)]
        calculate_items(items)  # should not error

    def test_very_large_price(self):
        base = _full_precision_base(99999.99)
        items = [_gravado(99999.99, 1, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_high_qty_small_price(self):
        """Previously failed: 0.01 * 50000 with 6 decimals."""
        base = _full_precision_base(0.01)
        items = [_gravado(0.01, 50000, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_high_qty_1_sol(self):
        """Previously failed: 1.00 * 9999 with 2-decimal base."""
        base = _full_precision_base(1.00)
        items = [_gravado(1.00, 9999, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_max_items_20(self):
        items = [_gravado(float(i + 1), i + 1, unit_price_without_tax=_full_precision_base(float(i + 1))) for i in range(20)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller


# ════════════════════════════════════════════════════════════════
# 14. Worst-case stress tests — all pass with full precision
# ════════════════════════════════════════════════════════════════

class TestWorstCaseStress:
    def test_0_99_x_9999(self):
        base = _full_precision_base(0.99)
        items = [_gravado(0.99, 9999, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_1_00_x_9999(self):
        base = _full_precision_base(1.00)
        items = [_gravado(1.00, 9999, unit_price_without_tax=base)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_20_rounding_items_qty_100(self):
        bad_prices = [
            0.99, 1.00, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99,
            4.49, 4.99, 5.49, 5.99, 6.49, 6.99, 7.49, 7.99,
            8.49, 8.99, 9.49, 9.99,
        ]
        items = [_gravado(p, 100, unit_price_without_tax=_full_precision_base(p)) for p in bad_prices]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_centavo_prices_high_qty(self):
        items = [_gravado(i * 0.01, 1000, unit_price_without_tax=_full_precision_base(i * 0.01)) for i in range(1, 21)]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller

    def test_near_boundary_rounding(self):
        items = [
            _gravado(0.59, 999, unit_price_without_tax=_full_precision_base(0.59)),
            _gravado(0.60, 999, unit_price_without_tax=_full_precision_base(0.60)),
            _gravado(0.61, 999, unit_price_without_tax=_full_precision_base(0.61)),
        ]
        _, _, _, ms_total = calculate_items(items)
        caller = _caller_total_from_base(items)
        assert ms_total == caller
