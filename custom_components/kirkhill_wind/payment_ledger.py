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

* **An estimate is a labelled derivation, never a declaration.** While today
  falls outside every declared period the figure for the current one comes from
  the last declared rate and is labelled ``estimated_from_last_declared_rate``.
  It is shown, never added to the declared total: the board has not said it.
  The moment the board declares, that period becomes an entry.

Nothing here reaches for generation data. Money derives from capacity and the
declared rate only -- the same reason ``MemberSavingsValueSensor`` ignores the
calendar.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# attribute values, so the card and the sensors agree on the wording
BASIS_NO_ENTRIES = "no_entries"
BASIS_DECLARED = "declared"
BASIS_ESTIMATED = "estimated_from_last_declared_rate"

# A p/W rate is a small number of pence; anything past this is a typo, and a
# silent one would show a plausible-looking figure the board never declared.
MAX_RATE_P_PER_W = 1000.0
MAX_NOTE_LENGTH = 200


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
    has spoken about it. ``estimated_from_last_declared_rate`` when today is
    past every declared period, so the pending one is priced at the last rate
    the board announced and clearly marked as derived. ``no_entries`` when the
    ledger is empty: there is no last rate to derive from.
    """
    latest = latest_record(records)
    if latest is None:
        return None, BASIS_NO_ENTRIES
    value = record_value_gbp(latest)
    if today is None:
        today = dt_util.now().date()
    if latest["period_start"] <= today.isoformat() <= latest["period_end"]:
        return value, BASIS_DECLARED
    return value, BASIS_ESTIMATED


class PaymentLedger:
    """One config entry's payment declarations, persisted to a Store.

    Mutations always write through before notifying, so a listener that reads
    ``records`` is reading the saved state, never a half-applied edit.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._records: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []

    @property
    def entry_id(self) -> str:
        return self._entry_id

    @property
    def records(self) -> list[dict[str, Any]]:
        """Return copies of the entries, earliest period first."""
        return [dict(record) for record in self._records]

    async def async_load(self) -> None:
        """Load the stored ledger. An unreadable entry is dropped, not fatal."""
        data = await ledger_store(self._hass, self._entry_id).async_load()
        raw = data.get("records") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            self._records = []
            return
        loaded: list[dict[str, Any]] = []
        for candidate in raw:
            try:
                loaded.append(normalise_record(candidate))
            except ValueError as err:
                _LOGGER.warning("Dropping unreadable payment record: %s", err)
        self._records = _sorted(loaded)

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
        await ledger_store(self._hass, self._entry_id).async_save(
            {"records": self._records}
        )
        self._notify()

    async def async_add(self, record: dict[str, Any]) -> dict[str, Any]:
        """Validate, store and announce a new declaration."""
        stored = normalise_record(record)
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


async def async_setup_ledger(hass: HomeAssistant, entry) -> PaymentLedger:
    """Create and load the ledger for one config entry, before platforms set up."""
    ledger = PaymentLedger(hass, entry.entry_id)
    await ledger.async_load()
    _ledgers(hass)[entry.entry_id] = ledger
    return ledger


def get_ledger(hass: HomeAssistant, entry_id: str) -> PaymentLedger | None:
    """Return the loaded ledger for an entry, or None when it is not set up."""
    return _ledgers(hass).get(entry_id)


def async_unload_ledger(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the ledger for an unloading entry."""
    _ledgers(hass).pop(entry_id, None)
