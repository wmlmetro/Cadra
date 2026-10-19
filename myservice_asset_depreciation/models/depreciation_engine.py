"""
Depreciation engine — pure functions, no Odoo imports.
═══════════════════════════════════════════════════════════════════════════════
Kept free of the ORM deliberately so the arithmetic can be unit-tested under
plain pytest without spinning up a database. Everything here is deterministic:
the same inputs always produce the same board, which is what makes point-in-time
queries ("what was this worth on 2024-12-31?") a free side effect rather than a
separate feature.

Conventions decided here (the PRD does not settle either — see the plan):
  • Whole-month proration. Period 1 ends at the end of the month FOLLOWING
    start_date. No day-count apportionment.
  • The final period absorbs the rounding remainder, so a schedule always sums
    to exactly (cost - salvage). Without this a 3-year schedule on an odd cost
    drifts by a few kobo and the register never quite reconciles.
"""
from calendar import monthrange
from collections import namedtuple
from datetime import date

# ── Methods (must match the published API enum — PRD §8.6) ───────────────────
METHOD_NONE = 'none'
METHOD_STRAIGHT_LINE = 'straight_line'
METHOD_DECLINING_BALANCE = 'declining_balance'
METHOD_ERP_MANAGED = 'erp_managed'

# ── Calculation conventions (tenant-configurable) ────────────────────────────
#
# Both of these are genuine accounting-policy choices that differ between
# standards and between tenants, which is why they are settings rather than
# opinions baked into the engine.

#: How the first period is charged.
PRORATION_WHOLE_MONTH = 'whole_month'   # a full month's charge from month 1
PRORATION_DAILY = 'daily'               # first period scaled by days held

PRORATION_SELECTION = [
    (PRORATION_WHOLE_MONTH, 'Whole month'),
    (PRORATION_DAILY, 'Pro-rata by days'),
]

#: Methods Cadra actually calculates. 'none' has nothing to compute and
#: 'erp_managed' is owned by the tenant's ERP (NRS spec §6.2).
COMPUTED_METHODS = (METHOD_STRAIGHT_LINE, METHOD_DECLINING_BALANCE)

METHOD_SELECTION = [
    (METHOD_NONE, 'Not depreciated'),
    (METHOD_STRAIGHT_LINE, 'Straight line'),
    (METHOD_DECLINING_BALANCE, 'Declining balance'),
    (METHOD_ERP_MANAGED, 'ERP-managed'),
]

# ── Lifecycle states ─────────────────────────────────────────────────────────
STATE_NOT_APPLICABLE = 'not_applicable'
STATE_NOT_STARTED = 'not_started'
STATE_DEPRECIATING = 'depreciating'
STATE_FULLY_DEPRECIATED = 'fully_depreciated'
STATE_DISPOSED = 'disposed'
STATE_ERP_MANAGED = 'erp_managed'

STATE_SELECTION = [
    (STATE_NOT_APPLICABLE, 'Not depreciated'),
    (STATE_NOT_STARTED, 'Not started'),
    (STATE_DEPRECIATING, 'Depreciating'),
    (STATE_FULLY_DEPRECIATED, 'Fully depreciated'),
    (STATE_DISPOSED, 'Disposed'),
    (STATE_ERP_MANAGED, 'ERP-managed'),
]

# ── Start-date provenance ────────────────────────────────────────────────────
# The NRS import CSVs carry acquisition_cost on every row but no date column at
# all, so ~11.9k assets fall through to create_date. Recording which source won
# is what stops an inferred date being mistaken for a real capitalisation date.
SOURCE_ACQUISITION = 'acquisition'
SOURCE_PURCHASE = 'purchase'
SOURCE_CREATED = 'created'
SOURCE_MANUAL = 'manual'

SOURCE_SELECTION = [
    (SOURCE_ACQUISITION, 'Acquisition date'),
    (SOURCE_PURCHASE, 'Purchase date'),
    (SOURCE_CREATED, 'Record created (inferred)'),
    (SOURCE_MANUAL, 'Set manually'),
]

#: Sources that are genuine business dates. Anything else is a guess and should
#: surface in the backfill queue.
RELIABLE_SOURCES = (SOURCE_ACQUISITION, SOURCE_PURCHASE, SOURCE_MANUAL)


Period = namedtuple('Period', 'sequence period_end charge accumulated book_value')


# ── Date helpers ─────────────────────────────────────────────────────────────

def end_of_month(d):
    """Last calendar day of d's month."""
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def add_months(d, n):
    """Month-end n months after d. Always lands on a month end, so schedules
    never drift on 29/30/31-day boundaries."""
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, monthrange(year, month)[1])


def resolve_start_date(acquisition_date=None, purchase_date=None, created_date=None):
    """Fallback chain for the depreciation start date.

    Returns (start_date, source). See SOURCE_* — the source is what makes an
    inferred date auditable rather than silently wrong.
    """
    if acquisition_date:
        return acquisition_date, SOURCE_ACQUISITION
    if purchase_date:
        return purchase_date, SOURCE_PURCHASE
    if created_date:
        return created_date, SOURCE_CREATED
    return None, False


# ── Charge generators ────────────────────────────────────────────────────────

def _straight_line_charges(depreciable, life_months):
    """Equal monthly charge, with the last period absorbing the rounding drift."""
    per = round(depreciable / life_months, 2)
    charges = [per] * life_months
    drift = round(depreciable - per * life_months, 2)
    charges[-1] = round(charges[-1] + drift, 2)
    return charges


def _declining_balance_charges(cost, salvage, life_months, annual_rate_pct,
                               switch_to_straight_line=True):
    """Fixed percentage of the opening book value each month, floored at salvage.

    Declining balance never mathematically reaches salvage, so something has to
    close the gap by end of life. Two ways to do it:

    switch_to_straight_line=True (the default, and what MACRS does)
        Each period charge the GREATER of the declining amount and straight-line
        over the remaining life. Once straight-line wins it keeps winning, so
        the charge glides down and then flattens. No cliff.

    switch_to_straight_line=False
        Pure declining balance, with the final period writing off whatever is
        left down to salvage. Mathematically exact but the last charge can dwarf
        every other one — on a 36-month life at 20%/yr with 10% salvage the
        final month is ~3x the preceding one, which no accountant would book.

    Note the first mode makes a rate/life mismatch visible rather than hiding
    it: if the rate is too low for the life, straight-line wins from period one
    and the schedule is simply straight-line. That is the correct answer to an
    inconsistent policy, not a bug.
    """
    monthly_rate = float(annual_rate_pct) / 100.0 / 12.0
    charges = []
    book = cost
    for i in range(life_months):
        remaining = round(book - salvage, 2)
        if remaining <= 0:
            break
        charge = round(book * monthly_rate, 2)
        if switch_to_straight_line:
            periods_left = life_months - i
            straight = round(remaining / periods_left, 2) if periods_left else remaining
            charge = max(charge, straight)
        if charge >= remaining or i == life_months - 1:
            charge = remaining
        charges.append(charge)
        book = round(book - charge, 2)
    return charges


def _apply_daily_proration(charges, start_date):
    """Scale the first period by the fraction of that month actually held.

    The shortfall is pushed onto the end so the schedule still sums to exactly
    (cost - salvage) — the whole board simply runs one period longer when the
    asset was acquired mid-month.
    """
    if not charges or not start_date:
        return charges
    first_end = add_months(start_date, 1)
    days_in_month = first_end.day
    days_held = days_in_month - start_date.day
    if days_held >= days_in_month or days_held <= 0:
        return charges

    charges = list(charges)
    full = charges[0]
    prorated = round(full * days_held / days_in_month, 2)
    carry = round(full - prorated, 2)
    charges[0] = prorated
    if carry > 0:
        # The deferred slice becomes a final stub period.
        charges.append(carry)
    return charges


# ── Public API ───────────────────────────────────────────────────────────────

def build_schedule(*, cost, start_date, life_months, method, salvage=0.0,
                   annual_rate_pct=None, disposal_date=None,
                   switch_to_straight_line=True,
                   proration=PRORATION_WHOLE_MONTH):
    """Full period-by-period board.

    Returns a list of Period tuples, or [] when the inputs can't produce one
    (no cost, no start date, uncomputed method, salvage >= cost, zero life).
    Returning [] rather than raising keeps callers simple: a missing policy is
    an ordinary state in this register, not an error.
    """
    if method not in COMPUTED_METHODS or not start_date:
        return []

    cost = round(float(cost or 0.0), 2)
    salvage = round(float(salvage or 0.0), 2)
    life_months = int(life_months or 0)

    if cost <= 0 or life_months <= 0 or salvage >= cost:
        return []
    if method == METHOD_DECLINING_BALANCE and not annual_rate_pct:
        return []

    if method == METHOD_STRAIGHT_LINE:
        charges = _straight_line_charges(round(cost - salvage, 2), life_months)
    else:
        charges = _declining_balance_charges(
            cost, salvage, life_months, annual_rate_pct,
            switch_to_straight_line=switch_to_straight_line)

    if proration == PRORATION_DAILY:
        charges = _apply_daily_proration(charges, start_date)

    periods = []
    accumulated = 0.0
    for i, charge in enumerate(charges, start=1):
        period_end = add_months(start_date, i)
        # Disposal truncates the board — an asset stops depreciating the day it
        # leaves the register.
        if disposal_date and period_end > disposal_date:
            break
        accumulated = round(accumulated + charge, 2)
        periods.append(Period(
            sequence=i,
            period_end=period_end,
            charge=charge,
            accumulated=accumulated,
            book_value=round(cost - accumulated, 2),
        ))
    return periods


def value_at(as_of, *, cost, start_date, life_months, method, salvage=0.0,
             annual_rate_pct=None, disposal_date=None,
             switch_to_straight_line=True,
             proration=PRORATION_WHOLE_MONTH):
    """Summary at a point in time: (accumulated, book_value, state).

    Built on top of build_schedule rather than deriving independently, so the
    summary can never disagree with the board a user is looking at.
    """
    cost = round(float(cost or 0.0), 2)

    if method == METHOD_ERP_MANAGED:
        # The ERP owns these figures; the caller keeps whatever was fed in.
        return None, None, STATE_ERP_MANAGED
    if method not in COMPUTED_METHODS:
        return 0.0, cost, STATE_NOT_APPLICABLE

    schedule = build_schedule(
        cost=cost, start_date=start_date, life_months=life_months,
        method=method, salvage=salvage, annual_rate_pct=annual_rate_pct,
        disposal_date=disposal_date,
        switch_to_straight_line=switch_to_straight_line, proration=proration,
    )
    return _value_from(schedule, as_of, cost, disposal_date)


def _value_from(schedule, as_of, cost, disposal_date):
    """`value_at`'s answer read off a schedule already built."""
    if not schedule:
        return 0.0, cost, STATE_NOT_STARTED

    elapsed = [p for p in schedule if p.period_end <= as_of]
    if not elapsed:
        return 0.0, cost, STATE_NOT_STARTED

    last = elapsed[-1]
    if disposal_date and as_of >= disposal_date:
        state = STATE_DISPOSED
    elif len(elapsed) == len(schedule):
        state = STATE_FULLY_DEPRECIATED
    else:
        state = STATE_DEPRECIATING
    return last.accumulated, last.book_value, state


def schedule_end_date(**kwargs):
    """Month-end of the final period, or None if there is no schedule."""
    schedule = build_schedule(**kwargs)
    return schedule[-1].period_end if schedule else None


def summary_at(as_of, **kwargs):
    """`value_at(as_of, **kwargs) + (schedule_end_date(**kwargs),)`, from ONE
    schedule rather than two.

    Handoff 63b. Restating a class after a category policy save called both
    for every asset, so every schedule was built twice: 76,168 builds and
    about 7 s of a 22 s save on `test19`'s class of 19,042. Same arguments,
    same answers — `build_schedule` rounds the cost itself, so the schedule
    `value_at` builds is the one `schedule_end_date` builds
    (`test_depreciation_engine` pins the two forms equal).
    """
    method = kwargs.get('method')
    if method == METHOD_ERP_MANAGED or method not in COMPUTED_METHODS:
        # No schedule to share: both answers come from the early returns.
        return value_at(as_of, **kwargs) + (schedule_end_date(**kwargs),)
    schedule = build_schedule(**kwargs)
    cost = round(float(kwargs.get('cost') or 0.0), 2)
    return (_value_from(schedule, as_of, cost, kwargs.get('disposal_date'))
            + (schedule[-1].period_end if schedule else None,))
