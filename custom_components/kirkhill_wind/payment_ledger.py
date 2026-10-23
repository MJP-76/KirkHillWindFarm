"""Board payment declarations: a Store-backed ledger of dated p/W records.

The board pays members for the watts they own, at a p/W rate it announces for
a period. Four facts shape this module:

* **The period matters, the calendar does not — and a period is measured in
  whole months.** The rate is not an accrual -- 2,000 W at 20 p/W is GBP 400
  whether the period is a fortnight or a year -- but the period is what says
  *which* declaration applies. The board declares for months and the exact
  payment dates are not settled to a day, so every stored period runs from the
  1st to the last day of its months, the card's form offers months only, and a
  new line is offered the month after the latest one ends. The twice-a-year
  rhythm the AGM implies is still a convention the user enters, never a rule
  the code imposes, and a period stays editable after the fact.

* **All time is a sum of declarations, not a time integral** (decisions.md,
  2026-10-09, the third open question for the board): ``capacity_watts ×
  rate_p_per_w ÷ 100`` per entry, summed. Before any entry exists the total is
  *unknown*, never GBP 0.00 -- no declaration is not a declaration of nothing.

* **Storage cannot be ``entry.options``.** Config entry v11 purges the earnings
  inputs whatever they hold, so any monetary value stored there dies on the
  next upgrade (decisions.md, 2026-10-12). The ledger lives in HA's ``Store``,
  the way ``oauth.py`` keeps its registration, and outlives migrations.

* **No figure for a period the board has not declared.** While today falls
  outside every declared period the current figure is **withheld, not
  derived**: ``current_basis=awaiting_next_declaration`` with ``current_gbp``
  None. A declaration brings the rate *and* the capital/interest split
  together, and a number of unknown composition cannot be estimated honestly
  -- a derived figure would be neither what the board pays nor safely
  ignorable (decision, 2026-10-21). The moment the board declares the period,
  it becomes an entry.

Nothing here reaches for generation data. Money derives from capacity and the
declared rate only -- the same reason ``MemberSavingsValueSensor`` ignores the
calendar.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import BOARD_FIGURES_MANUAL, DOMAIN, SCOPE_OWNER
from .settings import board_figures_source

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Where a declaration came from. "board" is what the board announced; "self" is
# the member's own estimate for a period the board has not declared yet. They
# are stored alike but never presented alike: a self figure must never read as
# something published, which is why the pill's rate follows board records only.
SOURCE_BOARD = "board"
SOURCE_SELF = "self"
SOURCES = (SOURCE_BOARD, SOURCE_SELF)

# attribute values, so the card and the sensors agree on the wording
BASIS_NO_ENTRIES = "no_entries"
BASIS_DECLARED = "declared"
# An undeclared period produces no figure at all: capital/interest split unknown.
BASIS_WITHHELD = "awaiting_next_declaration"

# A p/W rate is a small number of pence; anything past this is a typo, and a
# silent one would show a plausible-looking figure the board never declared.
MAX_RATE_P_PER_W = 1000.0
MAX_NOTE_LENGTH = 200

# Board announcements shipped with the integration and upserted into the ledger
# on setup. Edited in a pull request, so git records who entered which figure
# and when — and the install picks it up on reload, with no code deploy.
BOARD_ANNOUNCEMENTS_FILE = Path(__file__).parent / "board_announcements.yaml"


def _read_announcements_file() -> str | None:
    """Read the shipped announcements file, for an executor job.

    ``Path.read_text`` is a blocking open, and Home Assistant flags it when
    that happens on the event loop — v4.18.0 did exactly that and logged a
    warning on every setup. File I/O belongs in an executor; parsing the text
    that comes back is cheap enough to stay in the loop.
    """
    if not BOARD_ANNOUNCEMENTS_FILE.is_file():
        return None
    try:
        return BOARD_ANNOUNCEMENTS_FILE.read_text(encoding="utf-8")
    except OSError as err:
        _LOGGER.warning("Cannot read board announcements: %s", err)
        return None


def ledger_store(hass: HomeAssistant, entry_id: str) -> Store:
    """Return the Store holding one config entry's payment ledger."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}_payment_ledger_{entry_id}")


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def month_start(value: date) -> date:
    """Return the first day of the month ``value`` falls in."""
    return value.replace(day=1)


def month_end(value: date) -> date:
    """Return the last day of the month ``value`` falls in (handles February)."""
    if value.month == 12:
        return date(value.year, 12, 31)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def _sorted(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order entries by the period they cover, earliest first."""
    return sorted(records, key=lambda r: (r["period_start"], r["period_end"]))


def normalise_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a clean, stored-shape copy of one record, or raise ValueError.

    Every field is validated here and nowhere else, so the service schema, the
    card's save path and a hand-edited storage file all land on the same rules.
    """
    if not isinstance(record, dict):
        raise ValueError("a payment record must be an object")

    period_start = _parse_date(record.get("period_start"))
    if period_start is None:
        raise ValueError("period_start is required and must be YYYY-MM or YYYY-MM-DD")
    period_end = _parse_date(record.get("period_end"))
    if period_end is None:
        raise ValueError("period_end is required and must be YYYY-MM or YYYY-MM-DD")
    if period_end < period_start:
        raise ValueError("period_end must not be before period_start")

    # Periods are month-granular: the board declares for months and the exact
    # payment dates are not settled to a day, so a stored period always runs
    # from the 1st to the last day of its months -- "Feb 2025 to Jun 2026"
    # means those whole months and nothing in between. Snapping happens after
    # the ordering check, so an end before its start stays an error instead of
    # quietly widening into a valid month.
    period_start = month_start(period_start)
    period_end = month_end(period_end)

    rate = _as_float(record.get("rate_p_per_w"))
    if rate is None or not 0 < rate <= MAX_RATE_P_PER_W:
        raise ValueError(
            f"rate_p_per_w must be greater than 0 and at most {MAX_RATE_P_PER_W}"
        )

    capacity = _as_float(record.get("capacity_watts"))
    if capacity is None or capacity < 0:
        raise ValueError("capacity_watts must be 0 or greater")

    announced_on = _parse_date(record.get("announced_on"))

    note = record.get("note")
    if note is not None:
        note = str(note).strip()[:MAX_NOTE_LENGTH] or None

    source = record.get("source")
    if source is None:
        # Records written before the tick existed were entered from a board
        # announcement, so absence means board rather than an unknown.
        source = SOURCE_BOARD
    if source not in SOURCES:
        raise ValueError(f"source must be one of {' or '.join(SOURCES)}")

    # A payment splits into capital and interest. Both are optional: while the
    # split is unknown the pair stays None. If only one is given the other is
    # the remainder of the period's figure, so a stored pair is always complete
    # and always sums correctly. Both given and not summing to the penny is a
    # rejected entry, not a silent fix -- these figures come from an Ethex
    # statement or a board announcement and must agree with the period they sit
    # in (and with a later edit to that period's rate or watts).
    value = round(capacity * rate / 100, 2)
    capital = _as_float(record.get("capital_gbp"))
    interest = _as_float(record.get("interest_gbp"))
    if capital is not None and capital < 0:
        raise ValueError("capital_gbp must be 0 or greater")
    if interest is not None and interest < 0:
        raise ValueError("interest_gbp must be 0 or greater")
    if capital is not None and interest is not None:
        if abs(round(capital + interest, 2) - value) > 0.01:
            raise ValueError(
                f"capital + interest ({capital + interest:.2f}) must equal the period's"
                f" figure ({value:.2f})"
            )
    elif capital is not None:
        interest = round(value - capital, 2)
    elif interest is not None:
        capital = round(value - interest, 2)

    record_id = record.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        record_id = uuid.uuid4().hex

    return {
        "id": record_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "rate_p_per_w": round(rate, 4),
        "capacity_watts": capacity,
        "announced_on": announced_on.isoformat() if announced_on else None,
        "note": note,
        "source": source,
        "capital_gbp": capital,
        "interest_gbp": interest,
    }


def _parse_date(value: Any) -> date | None:
    """Parse a date from ``YYYY-MM-DD``, ``YYYY-MM``, a ``date`` or a ``datetime``.

    None if unparseable. The month-only form is how a period reads in the UI:
    it resolves to the 1st, and ``month_end`` puts an end month on its last day.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
        if len(text) == 7 and text[4] == "-":
            try:
                return date.fromisoformat(f"{text}-01")
            except ValueError:
                return None
        return None
    return None


def record_value_gbp(record: dict[str, Any]) -> float:
    """Return one declaration's figure: watts owned at that period's p/W rate."""
    return round(record["capacity_watts"] * record["rate_p_per_w"] / 100, 2)


def ledger_total_gbp(records: list[dict[str, Any]]) -> float | None:
    """Return Σ of every declaration, or None when nothing has been declared.

    None -- not 0.0 -- is the empty answer: the card draws "—" and the sensor
    reads unknown, because the board has declared nothing yet.
    """
    if not records:
        return None
    return round(sum(record_value_gbp(r) for r in records), 2)


def latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the declaration whose period ends last, or None when empty."""
    if not records:
        return None
    return max(records, key=lambda r: (r["period_end"], r["period_start"]))


def current_figure(
    records: list[dict[str, Any]], today: date | None = None
) -> tuple[float | None, str]:
    """Return (figure, basis) for the period that is current now.

    ``declared`` when today falls inside the latest declared period -- the board
    has spoken about it. ``awaiting_next_declaration`` when today is past every
    declared period: the figure is **withheld rather than derived**, because
    the period covering today carries no rate and no published capital/interest
    split -- a payment splits into two halves, and a number of unknown
    composition is a guess rather than an estimate. ``no_entries`` when the
    ledger is empty: nothing has ever been declared.
    """
    latest = latest_record(records)
    if latest is None:
        return None, BASIS_NO_ENTRIES
    if today is None:
        today = dt_util.now().date()
    if latest["period_start"] <= today.isoformat() <= latest["period_end"]:
        return record_value_gbp(latest), BASIS_DECLARED
    return None, BASIS_WITHHELD


def source_totals_gbp(records: list[dict[str, Any]]) -> dict[str, float | None]:
    """Return ``{"board": Σ, "self": Σ}``, each None when that source is absent.

    The buckets do not replace the total: ``total_gbp`` stays the sum of
    everything declared or estimated, and these say how much of it the board
    actually announced versus how much is the member's own estimate.
    """
    board = [r for r in records if r.get("source") == SOURCE_BOARD]
    own = [r for r in records if r.get("source") == SOURCE_SELF]
    return {SOURCE_BOARD: ledger_total_gbp(board), SOURCE_SELF: ledger_total_gbp(own)}


def split_totals_gbp(records: list[dict[str, Any]]) -> dict[str, float | None]:
    """Return ``{"capital": Σ, "interest": Σ}`` across records carrying a split.

    None, not 0, when no record carries that half: a split nobody has entered
    is an absence of information, not a payment of nothing. Both halves of a
    record always sum to its figure -- ``normalise_record`` enforces it -- so
    these two numbers cannot disagree with ``total_gbp`` for the records they
    cover. Splits are entered by hand from an Ethex statement or a board
    announcement; nothing here derives one.
    """
    capitals = [r["capital_gbp"] for r in records if r.get("capital_gbp") is not None]
    interests = [
        r["interest_gbp"] for r in records if r.get("interest_gbp") is not None
    ]
    return {
        "capital": round(sum(capitals), 2) if capitals else None,
        "interest": round(sum(interests), 2) if interests else None,
    }


def latest_board_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest board declaration, or None.

    This -- and only this -- is what the card's `Published …` pill reports: a
    self-estimated rate has not been published by anyone.
    """
    return latest_record([r for r in records if r.get("source") == SOURCE_BOARD])


def year_totals_gbp(records: list[dict[str, Any]]) -> dict[str, float]:
    """Σ of declarations keyed by the calendar year each one **ends** in.

    A declaration is attributed whole, never split: Feb 2025 → Jun 2026 counts
    as 2026, because dividing it across the years it touches would be exactly
    the accrual the no-accrual decision rules out. Years with no declaration
    are absent from the map, so the card draws "—" rather than 0.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        buckets.setdefault(record["period_end"][:4], []).append(record)
    return {year: ledger_total_gbp(group) for year, group in sorted(buckets.items())}


def current_year_gbp(
    records: list[dict[str, Any]], today: date | None = None
) -> float | None:
    """Σ of declarations ending in today's calendar year, or None when there are none."""
    if today is None:
        today = dt_util.now().date()
    return year_totals_gbp(records).get(str(today.year))


def roi_pct(value_gbp: float | None, invested_gbp: float | None) -> float | None:
    """Return ``value ÷ invested × 100``, or None when no return can be computed.

    None -- not 0 -- is the empty answer: with no invested amount recorded there
    is no return to quote, and "0.00%" would claim the money earned nothing
    rather than admitting we were never told what was put in. Plain percentage
    of capital per period, deliberately unannualised: the board pays per period
    regardless of how long it runs, so a per-year figure would be a rate of our
    own invention.
    """
    if value_gbp is None or invested_gbp is None or invested_gbp <= 0:
        return None
    return round(value_gbp / invested_gbp * 100, 2)


def projection_gbp(
    annual_rate_p_per_w: float | None,
    capacity_watts: float | None,
    lifespan_years: float | None,
) -> tuple[float | None, float | None]:
    """Return (annual_gbp, lifespan_gbp) for the member's capacity.

    A projection, never a figure: the annual rate is whatever the member chose
    to assume -- normally the board's own published annual equivalent, whose
    Feb 2025 → Jun 2026 announcement equated 21 p/W over 17 months to 15 p/W
    over 12 -- and the total assumes that rate holds for the whole lifespan.
    None when any input is missing, because a projection with a hole in it is
    worse than no projection. It feeds no total and fills no period; callers
    must label it as what it is.
    """
    if annual_rate_p_per_w is None or capacity_watts is None or lifespan_years is None:
        return None, None
    if annual_rate_p_per_w <= 0 or capacity_watts <= 0 or lifespan_years <= 0:
        return None, None
    annual = round(capacity_watts * annual_rate_p_per_w / 100, 2)
    return annual, round(annual * lifespan_years, 2)


def share_value_per_watt(
    invested_gbp: float | None, capacity_watts: float | None
) -> float | None:
    """Return the member's share value in GBP per watt, derived.

    ``invested ÷ watts`` -- what one watt of the stake cost them -- recomputed
    from whatever the two inputs currently are, so it is a quotation of the
    ledger rather than a figure of its own: it changes the moment either input
    changes, and it writes nothing back. None while either input is missing or
    not positive, because a share value with a hole in it is a fiction.
    """
    if invested_gbp is None or capacity_watts is None:
        return None
    if invested_gbp <= 0 or capacity_watts <= 0:
        return None
    return round(invested_gbp / capacity_watts, 4)


def derived_invested_gbp(
    share_price_p_per_w: float | None, capacity_watts: float | None
) -> float | None:
    """Return the unconfirmed capital: share price × watts ÷ 100.

    Amber until the member enters their own figure or ticks that it matches:
    an auto-fill is a suggestion, never their statement, so nothing here
    writes ``invested_gbp``. None while either input is missing or not
    positive — a derived capital with a hole in it is a fiction.
    """
    if share_price_p_per_w is None or capacity_watts is None:
        return None
    if share_price_p_per_w <= 0 or capacity_watts <= 0:
        return None
    return round(share_price_p_per_w * capacity_watts / 100, 2)


def effective_invested(
    invested_gbp: float | None, derived_gbp: float | None
) -> tuple[float | None, str | None]:
    """Return ``(amount, source)`` for ROI: the member's own figure wins.

    ``("user", ...)`` when they entered it — green. ``("derived", ...)`` when
    only the price-times-watts auto-fill exists — amber, and every ROI quoting
    it is provisional until confirmed. ``(None, None)`` when neither exists:
    there is no return to quote, never zero.
    """
    if invested_gbp is not None:
        return invested_gbp, "user"
    if derived_gbp is not None:
        return derived_gbp, "derived"
    return None, None


def lifetime_estimate(
    records: list[dict[str, Any]],
    annual_rate_p_per_w: float | None,
    capacity_watts: float | None,
    lifespan_years: float | None,
    invested_gbp: float | None,
    today: date | None = None,
) -> dict[str, float | None] | None:
    """Return the labelled lifetime estimate, or None when an input is missing.

    **Known plus time-left, never an accrual.** The known half is what the
    board actually declared (``board_total_gbp`` -- self estimates stay out of
    it, they are guesses about periods that may never be announced), and the
    unknown half is the years the lifespan has left times the member's annual
    projection: ``(lifespan − elapsed since the first board period) ×
    watts × rate ÷ 100``. Elapsed runs fractionally (days ÷ 365.25) from the
    earliest board declaration -- with no periods there is no anchor, so
    elapsed is zero and the whole lifespan is estimate.

    The annual rate is whatever ``set_projection`` last stored -- normally the
    board's own published annual equivalent, whose Feb 2025 → Jun 2026
    announcement equated 21 p/W over 17 months to 15 p/W over 12 -- never a
    constant in this code, because the board can requote.

    **It counts for nothing.** This figure feeds no total, fills no period and
    replaces no actual: callers must label it as an estimate. A projection
    with a hole in it is worse than no projection, so any missing input means
    None; an elapsed lifespan simply leaves remainder zero.
    """
    if annual_rate_p_per_w is None or capacity_watts is None or lifespan_years is None:
        return None
    if annual_rate_p_per_w <= 0 or capacity_watts <= 0 or lifespan_years <= 0:
        return None
    known = source_totals_gbp(records)[SOURCE_BOARD]
    anchor = next(
        (r["period_start"] for r in records if r.get("source") == SOURCE_BOARD),
        None,
    )
    if today is None:
        today = dt_util.now().date()
    elapsed = 0.0
    if anchor is not None:
        elapsed = max((today - date.fromisoformat(anchor)).days / 365.25, 0.0)
    remaining = max(lifespan_years - elapsed, 0.0)
    annual = round(capacity_watts * annual_rate_p_per_w / 100, 2)
    remainder = round(annual * remaining, 2)
    lifetime = round((known if known is not None else 0.0) + remainder, 2)
    return {
        "known_gbp": known,
        "remainder_gbp": remainder,
        "lifetime_gbp": lifetime,
        "elapsed_years": round(elapsed, 2),
        "remaining_years": round(remaining, 2),
        "roi_pct": roi_pct(lifetime, invested_gbp),
    }


class PaymentLedger:
    """One config entry's payment declarations, persisted to a Store.

    Mutations always write through before notifying, so a listener that reads
    ``records`` is reading the saved state, never a half-applied edit.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._records: list[dict[str, Any]] = []
        self._invested_gbp: float | None = None
        self._share_price_p_per_w: float | None = None
        self._annual_rate_p_per_w: float | None = None
        self._lifespan_years: float | None = None
        self._listeners: list[Callable[[], None]] = []

    @property
    def entry_id(self) -> str:
        return self._entry_id

    @property
    def invested_gbp(self) -> float | None:
        """What the member put in — one number for the whole ledger, None if untold."""
        return self._invested_gbp

    @property
    def share_price_p_per_w(self) -> float | None:
        """Pence per watt paid — the input the amber derived capital uses."""
        return self._share_price_p_per_w

    @property
    def annual_rate_p_per_w(self) -> float | None:
        """p/W per year the member assumes — normally the board's published equivalent."""
        return self._annual_rate_p_per_w

    @property
    def lifespan_years(self) -> float | None:
        """Years the projection runs over, None if untold."""
        return self._lifespan_years

    @property
    def records(self) -> list[dict[str, Any]]:
        """Return copies of the entries, earliest period first."""
        return [dict(record) for record in self._records]

    async def async_load(self) -> None:
        """Load the stored ledger. An unreadable entry is dropped, not fatal."""
        try:
            data = await ledger_store(self._hass, self._entry_id).async_load()
        except (ValueError, OSError) as err:
            # HA's Store raises on a truncated or corrupt file instead of
            # returning None -- the docstring's promise stands: an unreadable
            # entry is dropped, never fatal. The integration starts; the
            # error names the loss loudly so it cannot pass unnoticed.
            _LOGGER.error(
                "Stored payment ledger is unreadable (%s) -- starting empty;"
                " declarations must be re-entered or re-applied from the file",
                err,
            )
            data = None
        is_dict = isinstance(data, dict)
        raw = data.get("records") if is_dict else None
        if isinstance(raw, list):
            loaded: list[dict[str, Any]] = []
            for candidate in raw:
                try:
                    loaded.append(normalise_record(candidate))
                except ValueError as err:
                    _LOGGER.warning("Dropping unreadable payment record: %s", err)
            self._records = _sorted(loaded)
        else:
            self._records = []
        # Read even when the records are absent: an invested amount with no
        # declarations yet is a legitimate thing to have stored.
        invested = _as_float(data.get("invested_gbp")) if is_dict else None
        self._invested_gbp = (
            invested if invested is not None and invested >= 0 else None
        )
        # The share price is a per-watt input (p/W): the amber derived capital
        # is this times the member's watts -- nothing else derives capital,
        # and nothing writes invested_gbp from it.
        price = _as_float(data.get("share_price_p_per_w")) if is_dict else None
        self._share_price_p_per_w = price if price is not None and price > 0 else None
        rate = _as_float(data.get("annual_rate_p_per_w")) if is_dict else None
        self._annual_rate_p_per_w = rate if rate is not None and rate > 0 else None
        years = _as_float(data.get("lifespan_years")) if is_dict else None
        self._lifespan_years = years if years is not None and years > 0 else None

    async def async_apply_board_announcements(
        self, default_capacity: float | None = None
    ) -> int:
        """Upsert the shipped ``board_announcements.yaml`` into the ledger.

        The file owns the periods it names: the same period in means the same
        record out — rate, dates, announced_on and note updated, while the
        watts and any capital/interest split the user entered against that
        period are preserved. Periods the file does not name — everything
        added in the card — are never touched. A new period with no capacity
        available is skipped rather than guessed: a rate without watts cannot
        produce a figure.

        Returns how many records were created or changed.
        """
        text = await self._hass.async_add_executor_job(_read_announcements_file)
        if text is None:
            return 0
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as err:
            _LOGGER.warning("Cannot parse board announcements: %s", err)
            return 0
        entries = data.get("records") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            _LOGGER.warning(
                "%s: expected a 'records' list", BOARD_ANNOUNCEMENTS_FILE.name
            )
            return 0

        index_by_period = {
            (r["period_start"], r["period_end"]): i for i, r in enumerate(self._records)
        }
        applied = 0
        for position, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                _LOGGER.warning(
                    "%s: entry %s is not a mapping",
                    BOARD_ANNOUNCEMENTS_FILE.name,
                    position,
                )
                continue
            period_start = _parse_date(entry.get("period_start"))
            period_end = _parse_date(entry.get("period_end"))
            if period_start is None or period_end is None:
                _LOGGER.warning(
                    "%s: entry %s has no usable period",
                    BOARD_ANNOUNCEMENTS_FILE.name,
                    position,
                )
                continue
            # Match on the snapped period, which is how records are stored.
            key = (
                month_start(period_start).isoformat(),
                month_end(period_end).isoformat(),
            )
            index = index_by_period.get(key)
            existing = self._records[index] if index is not None else None
            capacity = existing.get("capacity_watts") if existing else default_capacity
            if capacity is None:
                _LOGGER.warning(
                    "%s: skipping %s — no owner capacity for a new record",
                    BOARD_ANNOUNCEMENTS_FILE.name,
                    key,
                )
                continue

            candidate = {
                **(existing or {}),
                "id": f"board-{key[0]}-{key[1]}"
                if existing is None
                else existing["id"],
                "period_start": key[0],
                "period_end": key[1],
                "capacity_watts": capacity,
                "rate_p_per_w": entry.get("rate_p_per_w"),
                "announced_on": entry.get("announced_on"),
                "note": entry.get("note"),
                "source": SOURCE_BOARD,
            }
            # A split the file names wins for that period -- and owns BOTH
            # halves: the half it omits goes back to normalise_record to be
            # worked out from this period's figure, never inherited from an
            # entered split. A file silent on splits keeps an entered one
            # (only a rate or watts change clears that -- handled below). Key
            # presence, not truthiness: capital_gbp: 0 is a figure, and an
            # interest-only payment is exactly that. Validation, the penny
            # sum and completing the other half all ride normalise_record, so
            # the file gets the service's rules for free.
            named_split = {
                k: entry[k] for k in ("capital_gbp", "interest_gbp") if k in entry
            }
            if named_split:
                named_split.setdefault("capital_gbp", None)
                named_split.setdefault("interest_gbp", None)
            candidate.update(named_split)
            try:
                stored = normalise_record(candidate)
            except ValueError:
                # A re-announced rate can invalidate an entered capital/
                # interest split. The board's figure wins, but the split must
                # not be silently wrong: drop it, and say so.
                candidate.pop("capital_gbp", None)
                candidate.pop("interest_gbp", None)
                try:
                    stored = normalise_record(candidate)
                except ValueError as err:
                    _LOGGER.warning(
                        "%s: entry %s rejected: %s",
                        BOARD_ANNOUNCEMENTS_FILE.name,
                        position,
                        err,
                    )
                    continue
                _LOGGER.warning(
                    "%s: entry %s no longer sums with its capital/interest"
                    " split (the rate or watts moved, or the file's own"
                    " halves do not add up) -- the split was cleared",
                    BOARD_ANNOUNCEMENTS_FILE.name,
                    position,
                )

            if existing is not None:
                if stored == existing:
                    continue
                self._records[index] = stored
            else:
                self._records.append(stored)
                index_by_period[key] = len(self._records) - 1
            applied += 1

        if applied:
            self._records = _sorted(self._records)
            await self._async_commit()
        return applied

    async def async_set_invested(self, amount: float | None) -> None:
        """Record what the member invested; None clears it back to untold."""
        if amount is not None:
            value = _as_float(amount)
            if value is None or value < 0:
                raise ValueError("invested_gbp must be 0 or greater")
            amount = round(value, 2)
        self._invested_gbp = amount
        await self._async_commit()

    async def async_set_share_price(self, price_p_per_w: float | None) -> None:
        """Record the share price in p/W; None clears the auto-fill basis.

        Storing the price never writes ``invested_gbp``: the derived capital is
        computed from this and the member's watts at read time, shown amber
        until they enter their own figure or tick that it matches — their
        statement stays theirs alone.
        """
        if price_p_per_w is not None:
            value = _as_float(price_p_per_w)
            if value is None or value <= 0:
                raise ValueError("share_price_p_per_w must be greater than 0")
            price_p_per_w = round(value, 4)
        self._share_price_p_per_w = price_p_per_w
        await self._async_commit()

    async def async_set_projection(
        self, annual_rate_p_per_w: float | None, lifespan_years: float | None
    ) -> None:
        """Record the projection inputs; either may be None to clear it.

        The annual rate is the member's assumption, normally the board's own
        published annual equivalent. Storing it changes no total: a projection
        is a labelled line, never a figure the ledger counts.
        """
        if annual_rate_p_per_w is not None:
            rate = _as_float(annual_rate_p_per_w)
            if rate is None or rate <= 0:
                raise ValueError("annual_rate_p_per_w must be greater than 0")
            annual_rate_p_per_w = round(rate, 4)
        if lifespan_years is not None:
            years = _as_float(lifespan_years)
            if years is None or years <= 0 or years > 200:
                raise ValueError("lifespan_years must be between 1 and 200")
            lifespan_years = years
        self._annual_rate_p_per_w = annual_rate_p_per_w
        self._lifespan_years = lifespan_years
        await self._async_commit()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after every saved change. Returns an unsubscribe."""
        self._listeners.append(listener)

        @callback
        def _unsub() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsub

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def _async_commit(self) -> None:
        # Everything the ledger holds persists together -- the records, the
        # capital they are measured against, and the projection inputs -- so a
        # figure can never be computed from one half of a save.
        await ledger_store(self._hass, self._entry_id).async_save(
            {
                "records": self._records,
                "invested_gbp": self._invested_gbp,
                "share_price_p_per_w": self._share_price_p_per_w,
                "annual_rate_p_per_w": self._annual_rate_p_per_w,
                "lifespan_years": self._lifespan_years,
            }
        )
        self._notify()

    def _assert_period_free(
        self,
        period_start: str,
        period_end: str,
        exclude_id: str | None = None,
    ) -> None:
        """Refuse a period already declared, or overlapping one.

        The board declares whole, non-overlapping periods, so a collision is
        always an entry error — and a silent double add would double-count
        money in every total the ledger reports. Matching is on the snapped
        month window; adjacent periods (…Jun 2026 / Jul 2026…) never collide.
        ``exclude_id`` lets an edit keep its own window.
        """
        for existing in self._records:
            if existing["id"] == exclude_id:
                continue
            if (
                existing["period_start"],
                existing["period_end"],
            ) == (period_start, period_end):
                raise ValueError(
                    f"period {period_start} to {period_end} is already declared"
                    f" (record {existing['id']}) -- edit that record instead"
                )
            if (
                period_start <= existing["period_end"]
                and period_end >= existing["period_start"]
            ):
                raise ValueError(
                    f"period {period_start} to {period_end} overlaps the"
                    f" declared period {existing['period_start']} to"
                    f" {existing['period_end']} (record {existing['id']})"
                )

    async def async_add(self, record: dict[str, Any]) -> dict[str, Any]:
        """Validate, store and announce a new declaration."""
        stored = normalise_record(record)
        self._assert_period_free(stored["period_start"], stored["period_end"])
        if any(existing["id"] == stored["id"] for existing in self._records):
            stored["id"] = uuid.uuid4().hex
        self._records = _sorted([*self._records, stored])
        await self._async_commit()
        return dict(stored)

    async def async_update(
        self, record_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge ``changes`` into one record and re-save.

        Payment dates are not settled, so a period is expected to be edited
        after the fact: the merged record is re-validated in full, which is what
        keeps a "fix the end date" edit from leaving a broken figure behind.
        """
        index = next(
            (i for i, r in enumerate(self._records) if r["id"] == record_id), -1
        )
        if index < 0:
            raise KeyError(f"No payment record with id '{record_id}'")
        merged = {**self._records[index], **changes, "id": record_id}
        stored = normalise_record(merged)
        # Moving a window onto (or across) another record's period is an
        # entry error too; keeping its own window is not a collision.
        self._assert_period_free(
            stored["period_start"], stored["period_end"], exclude_id=record_id
        )
        self._records = _sorted(
            [r for i, r in enumerate(self._records) if i != index] + [stored]
        )
        await self._async_commit()
        return dict(stored)

    async def async_remove(self, record_id: str) -> bool:
        """Delete one record. Returns False when it was not there."""
        remaining = [r for r in self._records if r["id"] != record_id]
        if len(remaining) == len(self._records):
            return False
        self._records = remaining
        await self._async_commit()
        return True


# --- config-entry lifecycle -------------------------------------------------


def _ledgers(hass: HomeAssistant) -> dict[str, PaymentLedger]:
    # Domain-scoped key, same reasoning as services.SERVICES_REGISTERED:
    # hass.data is a namespace shared with every other integration.
    return hass.data.setdefault(DOMAIN, {})


def _owner_capacity(entry) -> float | None:
    """Current owner capacity from the coordinator; None when the API has none.

    The board announces a rate, not the member's watts, so a new board record
    needs the API's capacity to be worth anything -- and gets skipped if the
    API has none rather than being given a guess.
    """
    data = getattr(getattr(entry, "runtime_data", None), "data", None)
    if not isinstance(data, dict):
        return None
    scope = data.get(SCOPE_OWNER)
    summary = scope.get("summary") if isinstance(scope, dict) else None
    value = (
        _as_float(summary.get("capacity_watts")) if isinstance(summary, dict) else None
    )
    return value if value is not None and value > 0 else None


async def async_setup_ledger(hass: HomeAssistant, entry) -> PaymentLedger:
    """Create and load the ledger for one config entry, before platforms set up."""
    ledger = PaymentLedger(hass, entry.entry_id)
    await ledger.async_load()
    _ledgers(hass)[entry.entry_id] = ledger
    # Board announcements ship inside the integration and are applied after the
    # stored state loads, so an edit to that file lands on setup or a reload --
    # no code deploy, and never at the expense of records added in the card.
    # "manual" switches the file off entirely and leaves the card the only
    # writer; anything else (including the "repo" default) applies it.
    if board_figures_source(entry) != BOARD_FIGURES_MANUAL:
        await ledger.async_apply_board_announcements(
            default_capacity=_owner_capacity(entry)
        )
    return ledger


def get_ledger(hass: HomeAssistant, entry_id: str) -> PaymentLedger | None:
    """Return the loaded ledger for an entry, or None when it is not set up."""
    return _ledgers(hass).get(entry_id)


def async_unload_ledger(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the ledger for an unloading entry."""
    _ledgers(hass).pop(entry_id, None)
