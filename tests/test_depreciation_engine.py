"""
Unit tests for the depreciation engine.

Unlike the rest of tests/, these need NO running Odoo and no API token — the
engine is deliberately free of ORM imports. Run with:

    pytest tests/test_depreciation_engine.py -v

The module is loaded by path rather than imported as a package, because the
addon's __init__.py pulls in odoo.
"""
import importlib.util
import pathlib
from datetime import date

import pytest

_ENGINE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "myservice_asset_depreciation" / "models" / "depreciation_engine.py"
)
_spec = importlib.util.spec_from_file_location("depreciation_engine", _ENGINE_PATH)
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)


SL = eng.METHOD_STRAIGHT_LINE
DB = eng.METHOD_DECLINING_BALANCE


# ── Date helpers ─────────────────────────────────────────────────────────────

def test_add_months_always_lands_on_month_end():
    assert eng.add_months(date(2024, 1, 15), 1) == date(2024, 2, 29)  # leap year
    assert eng.add_months(date(2024, 1, 31), 3) == date(2024, 4, 30)
    assert eng.add_months(date(2024, 11, 5), 2) == date(2025, 1, 31)  # year roll


def test_add_months_handles_february_in_a_non_leap_year():
    assert eng.add_months(date(2025, 1, 10), 1) == date(2025, 2, 28)


def test_resolve_start_date_prefers_acquisition_then_purchase_then_created():
    acq, pur, cre = date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)
    assert eng.resolve_start_date(acq, pur, cre) == (acq, eng.SOURCE_ACQUISITION)
    assert eng.resolve_start_date(None, pur, cre) == (pur, eng.SOURCE_PURCHASE)
    assert eng.resolve_start_date(None, None, cre) == (cre, eng.SOURCE_CREATED)
    assert eng.resolve_start_date(None, None, None) == (None, False)


# ── Straight line ────────────────────────────────────────────────────────────

def test_straight_line_produces_one_period_per_month_of_life():
    s = eng.build_schedule(cost=1200.0, start_date=date(2024, 1, 31),
                           life_months=12, method=SL)
    assert len(s) == 12
    assert all(p.charge == 100.0 for p in s)
    assert s[-1].book_value == 0.0


def test_first_period_ends_the_month_after_the_start_date():
    s = eng.build_schedule(cost=1200.0, start_date=date(2024, 1, 15),
                           life_months=12, method=SL)
    assert s[0].period_end == date(2024, 2, 29)
    assert s[-1].period_end == date(2025, 1, 31)


def test_straight_line_respects_salvage():
    s = eng.build_schedule(cost=1000.0, start_date=date(2024, 1, 31),
                           life_months=10, method=SL, salvage=200.0)
    assert sum(p.charge for p in s) == pytest.approx(800.0)
    assert s[-1].book_value == pytest.approx(200.0)


@pytest.mark.parametrize("cost,life", [
    (1000.0, 3),      # 333.33 x 3 = 999.99 — one kobo short
    (10000.0, 7),     # 1428.57 x 7 = 9999.99
    (12345.67, 60),
    (99999.99, 37),
    (1.0, 12),        # rounds to 0.08 per period
])
def test_schedule_sums_exactly_to_the_depreciable_amount(cost, life):
    """The rounding-remainder case. If the last period doesn't absorb the drift
    the register never reconciles."""
    s = eng.build_schedule(cost=cost, start_date=date(2024, 1, 31),
                           life_months=life, method=SL)
    assert round(sum(p.charge for p in s), 2) == round(cost, 2)
    assert s[-1].book_value == 0.0
    assert s[-1].accumulated == round(cost, 2)


def test_accumulated_is_monotonic_and_book_value_never_goes_negative():
    s = eng.build_schedule(cost=7777.77, start_date=date(2024, 1, 31),
                           life_months=41, method=SL, salvage=500.0)
    accs = [p.accumulated for p in s]
    assert accs == sorted(accs)
    assert all(p.book_value >= 500.0 - 0.005 for p in s)


# ── Declining balance ────────────────────────────────────────────────────────

def test_declining_balance_charge_shrinks_each_period():
    s = eng.build_schedule(cost=100000.0, start_date=date(2024, 1, 31),
                           life_months=60, method=DB, annual_rate_pct=15.0)
    charges = [p.charge for p in s]
    # Strictly decreasing until the final write-down period.
    assert all(a >= b for a, b in zip(charges, charges[1:-1]))
    assert charges[0] == pytest.approx(100000.0 * 0.15 / 12, abs=0.01)


def test_declining_balance_floors_at_salvage_and_sums_exactly():
    s = eng.build_schedule(cost=50000.0, start_date=date(2024, 1, 31),
                           life_months=60, method=DB, annual_rate_pct=25.0,
                           salvage=5000.0)
    assert round(sum(p.charge for p in s), 2) == pytest.approx(45000.0)
    assert s[-1].book_value == pytest.approx(5000.0)
    assert all(p.book_value >= 5000.0 - 0.005 for p in s)


def test_declining_balance_terminates_early_when_it_hits_salvage():
    """A high rate against a high salvage floor should stop well short of life."""
    s = eng.build_schedule(cost=10000.0, start_date=date(2024, 1, 31),
                           life_months=120, method=DB, annual_rate_pct=90.0,
                           salvage=9000.0)
    assert len(s) < 120
    assert s[-1].book_value == pytest.approx(9000.0)


def test_declining_balance_without_a_rate_yields_no_schedule():
    assert eng.build_schedule(cost=1000.0, start_date=date(2024, 1, 31),
                             life_months=12, method=DB) == []


# ── Degenerate inputs ────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    dict(cost=0.0, life_months=12),            # no cost
    dict(cost=None, life_months=12),           # unset cost
    dict(cost=1000.0, life_months=0),          # no useful life
    dict(cost=1000.0, life_months=None),       # unset useful life
    dict(cost=-500.0, life_months=12),         # negative cost
])
def test_degenerate_inputs_return_an_empty_schedule_rather_than_raising(kwargs):
    assert eng.build_schedule(start_date=date(2024, 1, 31), method=SL, **kwargs) == []


def test_missing_start_date_returns_an_empty_schedule():
    assert eng.build_schedule(cost=1000.0, start_date=None,
                             life_months=12, method=SL) == []


def test_salvage_at_or_above_cost_returns_an_empty_schedule():
    for salvage in (1000.0, 1500.0):
        assert eng.build_schedule(cost=1000.0, start_date=date(2024, 1, 31),
                                 life_months=12, method=SL, salvage=salvage) == []


@pytest.mark.parametrize("method", [eng.METHOD_NONE, eng.METHOD_ERP_MANAGED])
def test_uncomputed_methods_produce_no_schedule(method):
    assert eng.build_schedule(cost=1000.0, start_date=date(2024, 1, 31),
                             life_months=12, method=method) == []


# ── Disposal ─────────────────────────────────────────────────────────────────

def test_disposal_truncates_the_schedule():
    full = eng.build_schedule(cost=1200.0, start_date=date(2024, 1, 31),
                              life_months=12, method=SL)
    cut = eng.build_schedule(cost=1200.0, start_date=date(2024, 1, 31),
                             life_months=12, method=SL,
                             disposal_date=date(2024, 6, 30))
    assert len(full) == 12
    assert len(cut) == 5
    assert cut[-1].period_end <= date(2024, 6, 30)


def test_disposal_before_the_first_period_yields_nothing():
    assert eng.build_schedule(cost=1200.0, start_date=date(2024, 1, 31),
                             life_months=12, method=SL,
                             disposal_date=date(2024, 1, 31)) == []


# ── value_at ─────────────────────────────────────────────────────────────────

def test_value_at_agrees_with_the_board_at_every_period_boundary():
    """The summary must never disagree with the schedule a user is looking at."""
    policy = dict(cost=54321.99, start_date=date(2021, 3, 10), life_months=48,
                  method=SL, salvage=1234.56)
    schedule = eng.build_schedule(**policy)
    for period in schedule:
        acc, book, _state = eng.value_at(period.period_end, **policy)
        assert acc == pytest.approx(period.accumulated)
        assert book == pytest.approx(period.book_value)


def test_value_at_agrees_with_the_board_for_declining_balance_too():
    policy = dict(cost=250000.0, start_date=date(2022, 7, 1), life_months=60,
                  method=DB, annual_rate_pct=20.0, salvage=10000.0)
    for period in eng.build_schedule(**policy):
        acc, book, _ = eng.value_at(period.period_end, **policy)
        assert acc == pytest.approx(period.accumulated)
        assert book == pytest.approx(period.book_value)


def test_value_at_before_the_first_period_is_not_started():
    acc, book, state = eng.value_at(
        date(2024, 1, 31), cost=1200.0, start_date=date(2024, 1, 15),
        life_months=12, method=SL)
    assert (acc, book, state) == (0.0, 1200.0, eng.STATE_NOT_STARTED)


def test_value_at_mid_life_is_depreciating():
    _acc, _book, state = eng.value_at(
        date(2024, 7, 31), cost=1200.0, start_date=date(2024, 1, 31),
        life_months=12, method=SL)
    assert state == eng.STATE_DEPRECIATING


def test_value_at_past_end_of_life_is_fully_depreciated():
    acc, book, state = eng.value_at(
        date(2030, 1, 1), cost=1200.0, start_date=date(2024, 1, 31),
        life_months=12, method=SL)
    assert state == eng.STATE_FULLY_DEPRECIATED
    assert (acc, book) == (1200.0, 0.0)


def test_value_at_after_disposal_reports_disposed():
    _acc, _book, state = eng.value_at(
        date(2024, 9, 30), cost=1200.0, start_date=date(2024, 1, 31),
        life_months=12, method=SL, disposal_date=date(2024, 6, 30))
    assert state == eng.STATE_DISPOSED


def test_value_at_for_method_none_holds_book_value_at_cost():
    acc, book, state = eng.value_at(
        date(2030, 1, 1), cost=999.0, start_date=date(2020, 1, 1),
        life_months=12, method=eng.METHOD_NONE)
    assert (acc, book, state) == (0.0, 999.0, eng.STATE_NOT_APPLICABLE)


def test_value_at_for_erp_managed_declines_to_compute():
    """NRS spec §6.2 — Cadra reads but does not compute. Returning None is the
    signal to the caller to leave the externally-fed figures alone."""
    acc, book, state = eng.value_at(
        date(2030, 1, 1), cost=999.0, start_date=date(2020, 1, 1),
        life_months=12, method=eng.METHOD_ERP_MANAGED)
    assert (acc, book, state) == (None, None, eng.STATE_ERP_MANAGED)


def test_schedule_end_date_is_the_final_period():
    end = eng.schedule_end_date(cost=1200.0, start_date=date(2024, 1, 31),
                                life_months=12, method=SL)
    assert end == date(2025, 1, 31)
    assert eng.schedule_end_date(cost=0.0, start_date=date(2024, 1, 31),
                                 life_months=12, method=SL) is None
