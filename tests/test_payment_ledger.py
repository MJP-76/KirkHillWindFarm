"""Tests for the board payment ledger: validation, figures, storage, sensor, services.

The ledger is the only money path on the card that reports what the board
actually declared, so the tests below pin three things that must not drift:

* an empty ledger is *unknown*, never GBP 0.00 -- no declaration is not a
  declaration of nothing;
* an undeclared current period is an *estimate*, labelled as one, and kept out
  of the declared total;
* nothing monetary is written to ``entry.options`` (config v11 purges earnings
  inputs), so the ledger persists through a Store.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.kirkhill_wind.const import DOMAIN, SCOPE_OWNER, SCOPE_SITE
from custom_components.kirkhill_wind.payment_ledger import (
    BASIS_DECLARED,
    BASIS_NO_ENTRIES,
    BASIS_WITHHELD,
    PaymentLedger,
    async_setup_ledger,
    async_unload_ledger,
    current_figure,
    current_year_gbp,
    derived_invested_gbp,
    effective_invested,
    get_ledger,
    latest_board_record,
    latest_record,
    ledger_store,
    ledger_total_gbp,
    lifetime_estimate,
    normalise_record,
    projection_gbp,
    record_value_gbp,
    roi_pct,
    share_value_per_watt,
    source_totals_gbp,
    split_totals_gbp,
    year_totals_gbp,
)
from custom_components.kirkhill_wind.sensor import PaymentLedgerSensor
from custom_components.kirkhill_wind.services import (
    SERVICE_ADD_PAYMENT_RECORD,
    SERVICE_REMOVE_PAYMENT_RECORD,
    SERVICE_SCHEMA_ADD_PAYMENT,
    SERVICE_SCHEMA_SET_INVESTED,
    SERVICE_SCHEMA_SET_PROJECTION,
    SERVICE_SET_INVESTED_AMOUNT,
    SERVICE_SET_PROJECTION,
    SERVICE_UPDATE_PAYMENT_RECORD,
    async_setup_services,
)

# A period that ended before "now" -- the board has not declared the time since.
PAST_START = "2025-02-01"
PAST_END = "2026-06-30"
# A period long enough to contain any test run's "today".
OPEN_START = "2000-01-01"
OPEN_END = "2099-12-31"


class FakeStore:
    """Same interface as HA's Store, without writing a .storage file."""

    def __init__(self, data=None):
        self.data = data
        self.saves = 0

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data
        self.saves += 1


def _record(**overrides):
    record = {
        "period_start": PAST_START,
        "period_end": PAST_END,
        "rate_p_per_w": 20.0,
        "capacity_watts": 2000.0,
    }
    record.update(overrides)
    return record


@pytest.fixture
def fake_store():
    """Patch the ledger's Store with an in-memory double, per test."""
    store = FakeStore()
    with patch(
        "custom_components.kirkhill_wind.payment_ledger.ledger_store",
        return_value=store,
    ):
        yield store


class TestNormaliseRecord:
    """Every field passes through one validator, whichever door it came in."""

    def test_iso_strings_are_stored_as_iso_dates(self):
        stored = normalise_record(_record())
        assert stored["period_start"] == "2025-02-01"
        assert stored["period_end"] == "2026-06-30"

    def test_date_objects_and_datetimes_are_accepted(self):
        # cv.date hands the service date objects, and a hand-edited storage
        # file could hold either form.
        stored = normalise_record(
            _record(
                period_start=date(2025, 2, 1),
                period_end=date(2026, 6, 30),
                announced_on="2026-07-15T00:00:00",
            )
        )
        assert stored["period_start"] == "2025-02-01"
        assert stored["announced_on"] == "2026-07-15"

    def test_id_is_generated_when_absent_and_kept_when_present(self):
        assert len(normalise_record(_record())["id"]) == 32
        assert normalise_record(_record(id="abc123"))["id"] == "abc123"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"period_start": None},
            {"period_start": "not-a-date"},
            {"period_end": "2026-13-40"},
            {"period_end": "2025-01-01"},  # before the start
            {"rate_p_per_w": 0},  # "nothing declared" is no record at all
            {"rate_p_per_w": 1000.1},  # beyond the typo guard
            {"rate_p_per_w": "twenty"},
            {"capacity_watts": -1},
            {"capacity_watts": None},
        ],
    )
    def test_invalid_records_are_rejected(self, overrides):
        with pytest.raises(ValueError):
            normalise_record(_record(**overrides))

    def test_note_is_truncated_not_dropped(self):
        stored = normalise_record(_record(note="x" * 400))
        assert len(stored["note"]) == 200

    def test_periods_snap_to_whole_months(self):
        # The board declares months, not days: Feb 2025 -> Jun 2026 is the
        # 1st to the last day whichever days were picked in the form.
        stored = normalise_record(_record(period_start="2025-02-15", period_end="2026-06-10"))
        assert stored["period_start"] == "2025-02-01"
        assert stored["period_end"] == "2026-06-30"

    def test_month_only_shorthand_is_accepted(self):
        # The card's form deals in months and may send "2025-02" directly.
        stored = normalise_record(_record(period_start="2025-02", period_end="2026-06"))
        assert stored["period_start"] == "2025-02-01"
        assert stored["period_end"] == "2026-06-30"

    def test_end_month_snap_handles_leap_february(self):
        stored = normalise_record(_record(period_start="2024-01", period_end="2024-02-10"))
        assert stored["period_end"] == "2024-02-29"

    def test_end_before_start_is_still_rejected(self):
        # The ordering check runs before snapping, so whole months cannot
        # quietly rescue a period that runs backwards.
        with pytest.raises(ValueError):
            normalise_record(_record(period_start="2025-03", period_end="2025-02"))


class TestFigures:
    """Watts x declared rate per period, summed -- never a time integral."""

    def test_one_declaration(self):
        # 2,000 W at 20 p/W is GBP 400 whatever the period spans.
        assert record_value_gbp(normalise_record(_record())) == 400.0

    def test_total_of_several_declarations(self):
        records = [
            normalise_record(_record()),
            normalise_record(_record(period_start="2026-07-01", period_end="2026-12-31")),
        ]
        assert ledger_total_gbp(records) == 800.0

    def test_empty_total_is_unknown_not_zero(self):
        assert ledger_total_gbp([]) is None

    def test_latest_record_is_the_one_ending_last(self):
        records = [
            normalise_record(_record(period_start="2025-02-01", period_end="2025-07-31")),
            normalise_record(_record(period_start="2025-08-01", period_end="2026-01-31")),
        ]
        assert latest_record(records)["period_end"] == "2026-01-31"
        assert latest_record([]) is None

    def test_current_period_inside_a_declared_window_is_declared(self):
        value, basis = current_figure([normalise_record(_record(period_start=OPEN_START, period_end=OPEN_END))])
        assert basis == BASIS_DECLARED
        assert value == 400.0

    def test_time_past_the_last_declaration_withholds_the_figure(self):
        # Today is past every declared period: the declaration that would
        # bring the rate and the capital/interest split has not happened, so
        # nothing may be derived -- the period exists, the number does not
        # (decision, 2026-10-21).
        value, basis = current_figure([normalise_record(_record())])
        assert basis == BASIS_WITHHELD
        assert value is None

    def test_withheld_basis_string_matches_the_documented_one(self):
        # The value is part of the documented attribute surface (sensors.md
        # and dashboard.md enumerate it), so renaming it has to be a
        # deliberate, visible change rather than a silent refactor.
        assert BASIS_WITHHELD == "awaiting_next_declaration"

    def test_no_records_at_all(self):
        assert current_figure([]) == (None, BASIS_NO_ENTRIES)


class TestLedgerPersistence:
    """Mutations write through to the Store before anybody is notified."""

    @pytest.mark.asyncio
    async def test_add_persists_and_sorts_by_period(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_add(_record(period_start="2025-08-01", period_end="2026-01-31"))
        await ledger.async_add(_record(period_start="2025-02-01", period_end="2025-07-31"))

        assert [r["period_start"] for r in ledger.records] == ["2025-02-01", "2025-08-01"]
        assert fake_store.saves == 2
        assert len(fake_store.data["records"]) == 2

    @pytest.mark.asyncio
    async def test_load_restores_saved_records(self, hass):
        store = FakeStore({"records": [normalise_record(_record())]})
        with patch(
            "custom_components.kirkhill_wind.payment_ledger.ledger_store",
            return_value=store,
        ):
            ledger = PaymentLedger(hass, "test-entry")
            await ledger.async_load()
        assert [r["period_start"] for r in ledger.records] == [PAST_START]

    @pytest.mark.asyncio
    async def test_load_drops_an_unreadable_record_rather_than_failing(self, hass):
        store = FakeStore({"records": [normalise_record(_record()), {"period_start": "garbage"}]})
        with patch(
            "custom_components.kirkhill_wind.payment_ledger.ledger_store",
            return_value=store,
        ):
            ledger = PaymentLedger(hass, "test-entry")
            await ledger.async_load()
        assert len(ledger.records) == 1

    @pytest.mark.asyncio
    async def test_update_merges_and_revalidates(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        added = await ledger.async_add(_record())

        # Payment dates are not final, so editing a period is the normal case.
        updated = await ledger.async_update(added["id"], {"period_end": "2026-07-31", "rate_p_per_w": 22.5})
        assert updated["period_end"] == "2026-07-31"
        assert updated["rate_p_per_w"] == 22.5
        assert updated["capacity_watts"] == 2000.0

        # ...and a bad edit is rejected rather than stored half-valid.
        with pytest.raises(ValueError):
            await ledger.async_update(added["id"], {"rate_p_per_w": 0})

    @pytest.mark.asyncio
    async def test_update_unknown_id_raises(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        with pytest.raises(KeyError):
            await ledger.async_update("nope", {"rate_p_per_w": 10.0})

    @pytest.mark.asyncio
    async def test_remove_reports_whether_it_found_the_record(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        added = await ledger.async_add(_record())
        assert await ledger.async_remove(added["id"]) is True
        assert await ledger.async_remove(added["id"]) is False
        assert ledger.records == []

    @pytest.mark.asyncio
    async def test_listeners_fire_once_per_saved_change_and_can_unsubscribe(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        seen = []
        unsub = ledger.async_add_listener(lambda: seen.append(1))
        second = []
        ledger.async_add_listener(lambda: second.append(1))

        await ledger.async_add(_record())
        assert seen == [1] and second == [1]

        unsub()
        await ledger.async_add(_record(period_start="2026-07-01", period_end="2026-12-31"))
        assert seen == [1] and second == [1, 1]

    def test_storage_key_carries_the_entry_id(self, hass):
        # One Store per config entry: a second entry must never read the first
        # entry's declarations.
        assert ledger_store(hass, "entry-a").key == f"{DOMAIN}_payment_ledger_entry-a"
        assert ledger_store(hass, "entry-b").key != ledger_store(hass, "entry-a").key

    @pytest.mark.asyncio
    async def test_ledgers_are_held_per_entry_and_dropped_on_unload(self, hass, fake_store):
        entry = MagicMock()
        entry.entry_id = "entry-1"
        await async_setup_ledger(hass, entry)
        assert isinstance(get_ledger(hass, "entry-1"), PaymentLedger)
        assert get_ledger(hass, "entry-2") is None

        async_unload_ledger(hass, "entry-1")
        assert get_ledger(hass, "entry-1") is None


def _sensor(coordinator=None, **kwargs):
    """Build a sensor over a loaded ledger, as async_setup_entry does."""
    if coordinator is None:
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2000.0}},
            SCOPE_SITE: {"summary": {}},
        }
    entry = MagicMock()
    entry.entry_id = "test-entry"
    return PaymentLedgerSensor(coordinator, entry, kwargs.get("ledger") or _loaded_ledger())


def _loaded_ledger():
    ledger = PaymentLedger(MagicMock(), "test-entry")
    ledger._records = [normalise_record(_record())]
    return ledger


class TestPaymentLedgerSensor:
    """The sensor the card reads for All time £, Member savings and the pill."""

    def test_empty_ledger_reads_unknown_not_zero(self):
        sensor = _sensor(ledger=PaymentLedger(MagicMock(), "test-entry"))
        assert sensor.native_value is None
        attrs = sensor.extra_state_attributes
        assert attrs["record_count"] == 0
        assert attrs["total_gbp"] is None
        assert attrs["current_basis"] == BASIS_NO_ENTRIES

    def test_declared_total_and_records_are_exposed(self):
        sensor = _sensor()
        assert sensor.native_value == 400.0

        attrs = sensor.extra_state_attributes
        assert attrs["total_gbp"] == 400.0
        assert attrs["latest_rate_p_per_w"] == 20.0
        assert attrs["latest_period_start"] == PAST_START
        assert attrs["records"][0]["value_gbp"] == 400.0
        assert attrs["scope"] == SCOPE_OWNER

    def test_past_period_withholds_the_figure_but_not_the_records(self):
        sensor = _sensor()
        attrs = sensor.extra_state_attributes
        # Today is past PAST_END: the period exists and its £ stays in the
        # total, but no *current* figure may be derived until the board's
        # capital/interest split is published (decision, 2026-10-21).
        assert attrs["current_basis"] == BASIS_WITHHELD
        assert attrs["current_gbp"] is None
        # The source still reports, so the card can tell a self entry apart.
        assert attrs["current_source"] == "board"
        assert attrs["total_gbp"] == 400.0

    def test_available_even_when_the_coordinator_fails(self):
        # Declarations live on disk; a failed API poll must not blank them.
        coordinator = MagicMock()
        coordinator.last_update_success = False
        coordinator.data = {}
        assert _sensor(coordinator=coordinator).available is True

    def test_current_period_inside_the_window_reads_declared(self):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(_record(period_start=OPEN_START, period_end=OPEN_END))]
        sensor = _sensor(ledger=ledger)
        assert sensor.extra_state_attributes["current_basis"] == BASIS_DECLARED


class TestPaymentRecordServices:
    """The card's write path: kirkhill_wind.*_payment_record."""

    @staticmethod
    def _handler(hass, service):
        for call in hass.services.async_register.call_args_list:
            if call.args[:2] == (DOMAIN, service):
                return call.args[2]
        raise AssertionError(f"{service} was not registered")

    @staticmethod
    def _entry(*, capacity=2000.0):
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = MagicMock()
        entry.runtime_data.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": capacity}},
            SCOPE_SITE: {"summary": {}},
        }
        return entry

    async def _setup(self, hass, store):
        hass.config_entries.async_entries.return_value = [self._entry()]
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        hass.data.setdefault(DOMAIN, {})["test-entry"] = ledger
        await async_setup_services(hass)
        return ledger

    @pytest.mark.asyncio
    async def test_add_defaults_capacity_to_what_the_api_reports(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        handler = self._handler(hass, SERVICE_ADD_PAYMENT_RECORD)

        await handler(
            SimpleNamespace(
                data={
                    "period_start": PAST_START,
                    "period_end": PAST_END,
                    "rate_p_per_w": 20,
                }
            )
        )

        record = ledger.records[0]
        assert record["capacity_watts"] == 2000.0
        assert record_value_gbp(record) == 400.0

    @pytest.mark.asyncio
    async def test_add_with_explicit_historical_capacity(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        handler = self._handler(hass, SERVICE_ADD_PAYMENT_RECORD)

        await handler(
            SimpleNamespace(
                data={
                    "period_start": PAST_START,
                    "period_end": PAST_END,
                    "rate_p_per_w": 18.5,
                    "capacity_watts": 1500,
                    "note": "AGM",
                    "source": "self",
                }
            )
        )

        assert ledger.records[0]["capacity_watts"] == 1500.0
        assert ledger.records[0]["note"] == "AGM"
        # The tick travels through the schema and the validator unchanged.
        assert ledger.records[0]["source"] == "self"

    @pytest.mark.asyncio
    async def test_add_without_capacity_and_without_api_reading_is_refused(self, hass, fake_store):
        # Guessing watts would silently misprice every historical period.
        hass.config_entries.async_entries.return_value = [self._entry(capacity=None)]
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        hass.data.setdefault(DOMAIN, {})["test-entry"] = ledger
        await async_setup_services(hass)
        handler = self._handler(hass, SERVICE_ADD_PAYMENT_RECORD)

        entry = hass.config_entries.async_entries.return_value[0]
        entry.runtime_data.data[SCOPE_OWNER]["summary"] = {}

        with pytest.raises(HomeAssistantError):
            await handler(
                SimpleNamespace(
                    data={
                        "period_start": PAST_START,
                        "period_end": PAST_END,
                        "rate_p_per_w": 20,
                    }
                )
            )
        assert ledger.records == []

    @pytest.mark.asyncio
    async def test_update_and_remove_round_trip(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        add = self._handler(hass, SERVICE_ADD_PAYMENT_RECORD)
        update = self._handler(hass, SERVICE_UPDATE_PAYMENT_RECORD)
        remove = self._handler(hass, SERVICE_REMOVE_PAYMENT_RECORD)

        await add(
            SimpleNamespace(
                data={
                    "period_start": PAST_START,
                    "period_end": PAST_END,
                    "rate_p_per_w": 20,
                }
            )
        )
        record_id = ledger.records[0]["id"]

        await update(SimpleNamespace(data={"record_id": record_id, "period_end": "2026-07-31"}))
        assert ledger.records[0]["period_end"] == "2026-07-31"

        await remove(SimpleNamespace(data={"record_id": record_id}))
        assert ledger.records == []

    @pytest.mark.asyncio
    async def test_service_errors_are_reported_not_swallowed(self, hass, fake_store):
        await self._setup(hass, fake_store)
        update = self._handler(hass, SERVICE_UPDATE_PAYMENT_RECORD)
        remove = self._handler(hass, SERVICE_REMOVE_PAYMENT_RECORD)

        with pytest.raises(HomeAssistantError):
            await update(SimpleNamespace(data={"record_id": "missing", "rate_p_per_w": 5}))
        with pytest.raises(HomeAssistantError):
            await remove(SimpleNamespace(data={"record_id": "missing"}))

    def test_a_zero_rate_never_reaches_the_ledger(self):
        # The service schema rejects it before any handler runs; assert the
        # schema itself so a future handler change cannot re-admit a rate of 0.
        with pytest.raises(vol.Invalid):
            SERVICE_SCHEMA_ADD_PAYMENT(
                {
                    "period_start": PAST_START,
                    "period_end": PAST_END,
                    "rate_p_per_w": 0,
                }
            )

    @pytest.mark.asyncio
    async def test_set_invested_amount_round_trip(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        handler = self._handler(hass, SERVICE_SET_INVESTED_AMOUNT)

        await handler(SimpleNamespace(data={"invested_gbp": 5000}))
        assert ledger.invested_gbp == 5000.0

        # JSON null clears it: unknown capital, not zero capital.
        await handler(SimpleNamespace(data={"invested_gbp": None}))
        assert ledger.invested_gbp is None

    def test_invested_schema_accepts_null_and_rejects_negative(self):
        assert SERVICE_SCHEMA_SET_INVESTED({"invested_gbp": None})["invested_gbp"] is None
        assert SERVICE_SCHEMA_SET_INVESTED({"invested_gbp": "1250.5"})["invested_gbp"] == 1250.5
        with pytest.raises(vol.Invalid):
            SERVICE_SCHEMA_SET_INVESTED({"invested_gbp": -1})

    @pytest.mark.asyncio
    async def test_split_enters_through_the_service(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        add = self._handler(hass, SERVICE_ADD_PAYMENT_RECORD)
        data = {
            "period_start": PAST_START,
            "period_end": PAST_END,
            "rate_p_per_w": 20,
            "capacity_watts": 2000,
            "capital_gbp": 300,
            "interest_gbp": 100,
        }
        await add(SimpleNamespace(data=data))
        assert ledger.records[0]["capital_gbp"] == 300.0
        assert ledger.records[0]["interest_gbp"] == 100.0

        # A pair that does not sum to the period's figure is refused, not fixed.
        with pytest.raises(HomeAssistantError):
            await add(SimpleNamespace(data={**data, "interest_gbp": 100.5}))
        assert len(ledger.records) == 1

    @pytest.mark.asyncio
    async def test_projection_sets_and_clears_through_the_service(self, hass, fake_store):
        ledger = await self._setup(hass, fake_store)
        handler = self._handler(hass, SERVICE_SET_PROJECTION)

        # The board's own annual equivalent for Feb 2025 -> Jun 2026: 15 p/W.
        await handler(SimpleNamespace(data={"annual_rate_p_per_w": 15, "lifespan_years": 25}))
        assert ledger.annual_rate_p_per_w == 15.0
        assert ledger.lifespan_years == 25.0

        await handler(SimpleNamespace(data={"annual_rate_p_per_w": None, "lifespan_years": None}))
        assert ledger.annual_rate_p_per_w is None
        assert ledger.lifespan_years is None

        with pytest.raises(vol.Invalid):
            SERVICE_SCHEMA_SET_PROJECTION({"annual_rate_p_per_w": 0, "lifespan_years": 25})


class TestSource:
    """board = announced by the board; self = the member's own estimate."""

    def test_missing_source_is_board(self):
        # Records written before the tick existed came from board announcements,
        # so absence must not silently turn them into unlabelled estimates.
        assert normalise_record(_record())["source"] == "board"

    @pytest.mark.parametrize("source", ["board", "self"])
    def test_explicit_source_is_kept(self, source):
        assert normalise_record(_record(source=source))["source"] == source

    def test_unknown_source_is_rejected(self):
        with pytest.raises(ValueError):
            normalise_record(_record(source="committee"))

    def test_totals_split_without_changing_the_total(self):
        records = [
            normalise_record(_record()),
            normalise_record(_record(period_start="2026-07", period_end="2026-12", source="self")),
        ]
        totals = source_totals_gbp(records)
        assert totals["board"] == 400.0
        assert totals["self"] == 400.0
        # The state stays the sum of everything; the split is extra detail.
        assert ledger_total_gbp(records) == 800.0

    def test_absent_source_reads_none_not_zero(self):
        assert source_totals_gbp([normalise_record(_record())])["self"] is None
        assert source_totals_gbp([]) == {"board": None, "self": None}

    def test_pill_rate_follows_board_records_only(self):
        records = [
            normalise_record(_record()),  # board: 20 p/W, ends Jun 2026
            normalise_record(
                _record(
                    period_start="2026-07",
                    period_end="2026-12",
                    rate_p_per_w=33.5,
                    source="self",
                )
            ),
        ]
        # The self line is the later one, but nobody has published it.
        assert latest_board_record(records)["rate_p_per_w"] == 20.0
        assert latest_board_record([normalise_record(_record(source="self"))]) is None


class TestYearAttribution:
    """A declaration is counted whole in the year it ends in, never split."""

    def test_spanning_declaration_counts_once_in_its_end_year(self):
        records = [normalise_record(_record())]  # Feb 2025 -> Jun 2026
        assert year_totals_gbp(records) == {"2026": 400.0}
        assert current_year_gbp(records, today=date(2026, 10, 21)) == 400.0
        # It does not also claim 2025 -- that would double count.
        assert current_year_gbp(records, today=date(2025, 10, 21)) is None

    def test_years_with_no_declaration_are_absent(self):
        records = [normalise_record(_record(period_start="2024-01", period_end="2024-12"))]
        assert year_totals_gbp(records) == {"2024": 400.0}
        assert current_year_gbp(records, today=date(2026, 10, 21)) is None

    def test_declarations_in_one_year_add_up(self):
        records = [
            normalise_record(_record()),
            normalise_record(_record(period_start="2026-07", period_end="2026-12")),
        ]
        assert year_totals_gbp(records) == {"2026": 800.0}


class TestSourceAttributesOnTheSensor:
    """Board/self split, published rate and the year map as the card reads them."""

    @staticmethod
    def _sensor_with(records):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(r) for r in records]
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test-entry"
        return PaymentLedgerSensor(coordinator, entry, ledger)

    def test_split_published_rate_and_year_map(self):
        sensor = self._sensor_with(
            [
                _record(),  # board, ends Jun 2026
                _record(
                    period_start="2026-07",
                    period_end="2026-12",
                    rate_p_per_w=33.5,
                    source="self",
                ),
            ]
        )
        attrs = sensor.extra_state_attributes

        # board: 2,000 W x 20 p/W = 400.00 · self: 2,000 W x 33.5 p/W = 670.00
        assert attrs["total_gbp"] == 1070.0
        assert attrs["board_total_gbp"] == 400.0
        assert attrs["self_total_gbp"] == 670.0
        # Latest overall is the self line; the published one is not.
        assert attrs["latest_rate_p_per_w"] == 33.5
        assert attrs["latest_board_rate_p_per_w"] == 20.0
        # Today sits inside Jul-Dec 2026, whose record is self-estimated --
        # that is what makes Member savings draw with "~".
        assert attrs["current_source"] == "self"
        assert attrs["current_basis"] == BASIS_DECLARED
        assert attrs["current_year_gbp"] == 1070.0
        assert attrs["year_totals_gbp"] == {"2026": 1070.0}


class TestRoiAndInvested:
    """Return is value ÷ capital, and capital persists beside the records."""

    def test_roi_is_value_over_capital(self):
        assert roi_pct(537.49, 5000.0) == 10.75
        assert roi_pct(0.0, 5000.0) == 0.0

    @pytest.mark.parametrize(
        ("value", "invested"),
        [
            (537.49, None),  # never told what was invested
            (None, 5000.0),  # nothing declared yet
            (537.49, 0.0),  # zero capital has no rate of return
        ],
    )
    def test_missing_input_reads_none_not_zero(self, value, invested):
        assert roi_pct(value, invested) is None

    @pytest.mark.asyncio
    async def test_capital_persists_with_the_records(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_add(_record())
        await ledger.async_set_invested(5000)

        assert ledger.invested_gbp == 5000.0
        assert fake_store.data["invested_gbp"] == 5000.0
        assert len(fake_store.data["records"]) == 1

        reloaded = PaymentLedger(hass, "test-entry")
        await reloaded.async_load()
        assert reloaded.invested_gbp == 5000.0
        assert len(reloaded.records) == 1

    @pytest.mark.asyncio
    async def test_clearing_capital_reads_unknown(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_set_invested(5000)
        await ledger.async_set_invested(None)
        assert ledger.invested_gbp is None
        assert fake_store.data["invested_gbp"] is None

    @pytest.mark.asyncio
    async def test_negative_capital_is_refused(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        with pytest.raises(ValueError):
            await ledger.async_set_invested(-1)
        assert ledger.invested_gbp is None

    @pytest.mark.asyncio
    async def test_capital_without_records_is_kept(self, hass):
        store = FakeStore({"records": [], "invested_gbp": 1500.0})
        with patch(
            "custom_components.kirkhill_wind.payment_ledger.ledger_store",
            return_value=store,
        ):
            ledger = PaymentLedger(hass, "test-entry")
            await ledger.async_load()
        assert ledger.records == []
        assert ledger.invested_gbp == 1500.0

    @staticmethod
    def _sensor(ledger: PaymentLedger) -> PaymentLedgerSensor:
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test-entry"
        return PaymentLedgerSensor(coordinator, entry, ledger)

    def test_sensor_reports_capital_and_roi(self):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(_record())]  # GBP 400.00
        ledger._invested_gbp = 5000.0

        attrs = self._sensor(ledger).extra_state_attributes
        assert attrs["invested_gbp"] == 5000.0
        assert attrs["total_roi_pct"] == 8.0
        assert attrs["records"][0]["roi_pct"] == 8.0

    def test_roi_is_unknown_until_capital_is_known(self):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(_record())]

        attrs = self._sensor(ledger).extra_state_attributes
        assert attrs["invested_gbp"] is None
        assert attrs["total_roi_pct"] is None
        assert attrs["records"][0]["roi_pct"] is None


class TestCapitalInterestSplit:
    """A payment splits into capital and interest, entered by hand.

    The split comes from an Ethex statement or a board announcement; the ledger
    stores it, never derives it from anything else, and both halves always sum
    to the period's figure.
    """

    def test_both_halves_summing_to_the_figure_are_kept(self):
        stored = normalise_record(_record(capital_gbp=300.0, interest_gbp=100.0))
        assert stored["capital_gbp"] == 300.0
        assert stored["interest_gbp"] == 100.0

    def test_a_penny_out_is_rejected(self):
        # The period is worth £400.00, so the halves must agree to the penny.
        with pytest.raises(ValueError):
            normalise_record(_record(capital_gbp=300.0, interest_gbp=100.5))

    def test_one_half_completes_the_other(self):
        capital_only = normalise_record(_record(capital_gbp=350.0))
        assert capital_only["capital_gbp"] == 350.0
        assert capital_only["interest_gbp"] == 50.0

        interest_only = normalise_record(_record(interest_gbp=25.0))
        assert interest_only["interest_gbp"] == 25.0
        assert interest_only["capital_gbp"] == 375.0

    def test_no_split_stays_unknown(self):
        stored = normalise_record(_record())
        assert stored["capital_gbp"] is None
        assert stored["interest_gbp"] is None

    def test_negative_half_is_rejected(self):
        with pytest.raises(ValueError):
            normalise_record(_record(capital_gbp=-1))

    def test_totals_are_none_until_a_split_exists(self):
        assert split_totals_gbp([]) == {"capital": None, "interest": None}
        assert split_totals_gbp([normalise_record(_record())]) == {
            "capital": None,
            "interest": None,
        }
        records = [normalise_record(_record(capital_gbp=300.0, interest_gbp=100.0))]
        assert split_totals_gbp(records) == {"capital": 300.0, "interest": 100.0}

    @staticmethod
    def _sensor(records):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(r) for r in records]
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test-entry"
        return PaymentLedgerSensor(coordinator, entry, ledger)

    def test_sensor_reports_the_split_and_keeps_the_total(self):
        attrs = self._sensor([_record(capital_gbp=300.0, interest_gbp=100.0)]).extra_state_attributes
        assert attrs["capital_total_gbp"] == 300.0
        assert attrs["interest_total_gbp"] == 100.0
        assert attrs["records"][0]["capital_gbp"] == 300.0
        assert attrs["records"][0]["interest_gbp"] == 100.0
        # The split is a breakdown of the total, never a second figure.
        assert attrs["total_gbp"] == 400.0

    def test_sensor_split_totals_stay_none_for_unsplit_records(self):
        attrs = self._sensor([_record()]).extra_state_attributes
        assert attrs["capital_total_gbp"] is None
        assert attrs["interest_total_gbp"] is None


class TestProjection:
    """A projection over the farm's lifespan: an assumed annual rate, labelled.

    The rate is the member's assumption -- normally the board's own published
    annual equivalent (21 p/W over 17 months ≈ 15 p/W over a year). It feeds no
    total and fills no period.
    """

    def test_annual_and_lifespan_from_rate_and_watts(self):
        # 2,559.465 W at 15 p/W is £383.92 a year; over 25 years £9,598.00.
        annual, lifespan = projection_gbp(15.0, 2559.465, 25)
        assert annual == 383.92
        assert lifespan == 9598.0

    @pytest.mark.parametrize(
        ("rate", "watts", "years"),
        [
            (None, 2000.0, 25),
            (15.0, None, 25),
            (15.0, 2000.0, None),
            (0, 2000.0, 25),
            (15.0, 0, 25),
            (15.0, 2000.0, 0),
        ],
    )
    def test_any_missing_input_reads_none(self, rate, watts, years):
        # A projection with a hole in it is worse than no projection.
        assert projection_gbp(rate, watts, years) == (None, None)

    @pytest.mark.asyncio
    async def test_projection_is_stored_and_cleared(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_add(_record())
        await ledger.async_set_projection(15.0, 25)

        assert ledger.annual_rate_p_per_w == 15.0
        assert ledger.lifespan_years == 25.0
        assert fake_store.data["annual_rate_p_per_w"] == 15.0
        assert fake_store.data["lifespan_years"] == 25.0

        reloaded = PaymentLedger(hass, "test-entry")
        await reloaded.async_load()
        assert reloaded.annual_rate_p_per_w == 15.0

        await ledger.async_set_projection(None, None)
        assert ledger.annual_rate_p_per_w is None
        assert ledger.lifespan_years is None
        assert fake_store.data["annual_rate_p_per_w"] is None

    @pytest.mark.asyncio
    async def test_bad_projection_inputs_are_refused(self, hass, fake_store):
        ledger = PaymentLedger(hass, "test-entry")
        with pytest.raises(ValueError):
            await ledger.async_set_projection(0, 25)
        with pytest.raises(ValueError):
            await ledger.async_set_projection(15.0, 0)
        with pytest.raises(ValueError):
            await ledger.async_set_projection(15.0, 500)
        assert ledger.annual_rate_p_per_w is None

    @staticmethod
    def _sensor(records, ledger_kwargs=None):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._records = [normalise_record(r) for r in records]
        if ledger_kwargs:
            ledger._annual_rate_p_per_w = ledger_kwargs.get("rate")
            ledger._lifespan_years = ledger_kwargs.get("years")
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test-entry"
        return PaymentLedgerSensor(coordinator, entry, ledger)

    def test_sensor_projects_from_the_latest_capacity(self):
        attrs = self._sensor([_record(capacity_watts=2000.0)], {"rate": 15.0, "years": 25}).extra_state_attributes
        assert attrs["annual_rate_p_per_w"] == 15.0
        assert attrs["lifespan_years"] == 25.0
        assert attrs["annual_gbp"] == 300.0
        assert attrs["lifespan_gbp"] == 7500.0

    def test_sensor_projection_is_none_until_assumed(self):
        attrs = self._sensor([_record()]).extra_state_attributes
        assert attrs["annual_gbp"] is None
        assert attrs["lifespan_gbp"] is None
        assert attrs["annual_rate_p_per_w"] is None
        # ...and it never leaks into the totals.
        assert attrs["total_gbp"] == 400.0


class TestBoardAnnouncements:
    """The shipped board_announcements.yaml upserts into the ledger on setup."""

    @pytest.fixture
    def announcements(self, tmp_path):
        path = tmp_path / "board_announcements.yaml"
        with patch(
            "custom_components.kirkhill_wind.payment_ledger.BOARD_ANNOUNCEMENTS_FILE",
            path,
        ):
            yield path

    @staticmethod
    def _write(path, text):
        path.write_text(text, encoding="utf-8")

    @pytest.mark.asyncio
    async def test_creates_a_board_record(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
    announced_on: 2025-07-15
    note: "GBP 1.6m member payment approved"
""",
        )
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        applied = await ledger.async_apply_board_announcements(default_capacity=2559.465)

        assert applied == 1
        record = ledger.records[0]
        assert record["source"] == "board"
        assert record["rate_p_per_w"] == 21.0
        assert record["announced_on"] == "2025-07-15"
        assert record["capacity_watts"] == 2559.465
        assert record["id"].startswith("board-")  # stable and derived from the period
        assert fake_store.saves >= 1

    @pytest.mark.asyncio
    async def test_user_records_are_untouched(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2026-07-01
    period_end: 2026-12-31
    rate_p_per_w: 15
""",
        )
        ledger = PaymentLedger(hass, "test-entry")
        # A period added in the card, with its own watts and split.
        await ledger.async_add(
            _record(
                period_start="2025-02-01",
                period_end="2026-06-30",
                capacity_watts=3000.0,
                capital_gbp=100.0,
            )
        )
        applied = await ledger.async_apply_board_announcements(default_capacity=2559.465)

        assert applied == 1
        user = ledger.records[0]
        # Untouched: not renamed, not re-rated, split and watts intact.
        assert user["period_start"] == "2025-02-01"
        assert user["rate_p_per_w"] == 20.0
        assert user["capacity_watts"] == 3000.0
        assert user["capital_gbp"] == 100.0
        assert user["interest_gbp"] == 500.0  # 3,000 W at 20 p/W = 600.00
        assert not user["id"].startswith("board-")
        assert ledger.records[1]["id"].startswith("board-")

    @pytest.mark.asyncio
    async def test_same_period_updates_in_place(self, hass, fake_store, announcements):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_add(_record())  # rate 20, capacity 2000, no split
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
    announced_on: 2025-07-15
""",
        )
        applied = await ledger.async_apply_board_announcements(default_capacity=9999.0)

        assert applied == 1
        assert len(ledger.records) == 1
        record = ledger.records[0]
        assert record["rate_p_per_w"] == 21.0
        assert record["announced_on"] == "2025-07-15"
        assert record["capacity_watts"] == 2000.0  # the existing watts, not the default

    @pytest.mark.asyncio
    async def test_rate_change_clears_an_incompatible_split(self, hass, fake_store, announcements):
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_add(
            _record(capacity_watts=2000.0, capital_gbp=100.0, interest_gbp=300.0)
        )  # split sums to the old 400.00
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
""",
        )
        applied = await ledger.async_apply_board_announcements(default_capacity=2559.465)

        assert applied == 1
        record = ledger.records[0]
        assert record["rate_p_per_w"] == 21.0
        # The board's figure wins, and the split that no longer sums to it is
        # dropped rather than left silently wrong.
        assert record["capital_gbp"] is None
        assert record["interest_gbp"] is None

    @pytest.mark.asyncio
    async def test_empty_list_is_a_noop(self, hass, fake_store, announcements):
        self._write(announcements, "records: []\n")
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        applied = await ledger.async_apply_board_announcements(default_capacity=2559.465)

        assert applied == 0
        assert ledger.records == []
        assert fake_store.saves == 0  # nothing written when nothing changed

    @pytest.mark.asyncio
    async def test_new_period_without_capacity_is_skipped(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2026-07-01
    period_end: 2026-12-31
    rate_p_per_w: 15
""",
        )
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        applied = await ledger.async_apply_board_announcements(default_capacity=None)

        # A rate without watts cannot produce a figure, so it is not guessed.
        assert applied == 0
        assert ledger.records == []

    @pytest.mark.asyncio
    async def test_malformed_entries_are_skipped_others_applied(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - rate_p_per_w: 15
  - notamapping
  - period_start: 2026-07-01
    period_end: 2026-12-31
    rate_p_per_w: 15
""",
        )
        ledger = PaymentLedger(hass, "test-entry")
        await ledger.async_load()
        applied = await ledger.async_apply_board_announcements(default_capacity=2559.465)

        assert applied == 1
        assert len(ledger.records) == 1

    @pytest.mark.asyncio
    async def test_setup_applies_the_shipped_file(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
""",
        )
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.options = {}  # no overrides: the "repo" default applies the file
        entry.runtime_data = MagicMock()
        entry.runtime_data.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2559.465}},
            SCOPE_SITE: {"summary": {}},
        }

        ledger = await async_setup_ledger(hass, entry)

        assert len(ledger.records) == 1
        assert ledger.records[0]["capacity_watts"] == 2559.465

    @pytest.mark.asyncio
    async def test_manual_mode_ignores_the_file(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
""",
        )
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.options = {"board_figures_source": "manual"}
        entry.runtime_data = MagicMock()
        entry.runtime_data.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2559.465}},
            SCOPE_SITE: {"summary": {}},
        }

        ledger = await async_setup_ledger(hass, entry)

        # The card becomes the only writer: the file is not read at all.
        assert ledger.records == []

    @pytest.mark.asyncio
    async def test_repo_mode_is_the_default(self, hass, fake_store, announcements):
        self._write(
            announcements,
            """
records:
  - period_start: 2025-02-01
    period_end: 2026-06-30
    rate_p_per_w: 21
""",
        )
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.options = {}  # default: repo
        entry.runtime_data = MagicMock()
        entry.runtime_data.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2559.465}},
            SCOPE_SITE: {"summary": {}},
        }

        ledger = await async_setup_ledger(hass, entry)

        assert len(ledger.records) == 1
        assert ledger.records[0]["source"] == "board"


class TestLifetimeEstimateAndShareValue:
    """Known actuals plus time-left, and the derived per-watt share quotation."""

    def test_share_value_is_invested_divided_by_watts(self):
        # GBP 4,427.87 over 2,559.465 W is GBP 1.73 per watt, to four places.
        assert share_value_per_watt(4427.87, 2559.465) == 1.73

    def test_share_value_needs_two_positive_inputs(self):
        assert share_value_per_watt(None, 2559.465) is None
        assert share_value_per_watt(4427.87, None) is None
        assert share_value_per_watt(0, 2559.465) is None
        assert share_value_per_watt(4427.87, 0) is None

    def test_lifetime_is_known_actuals_plus_the_years_left(self):
        records = [normalise_record(_record(rate_p_per_w=21, capacity_watts=2559.465))]
        today = date(2026, 10, 22)
        result = lifetime_estimate(records, 15, 2559.465, 25, 4427.87, today=today)

        assert result is not None
        assert result["known_gbp"] == 537.49  # the board's actual figure
        elapsed = (today - date(2025, 2, 1)).days / 365.25
        assert result["elapsed_years"] == round(elapsed, 2)
        assert 23.27 <= result["remaining_years"] <= 23.29
        # 15 p/W on 2,559.465 W is GBP 383.92/year, for the years left.
        expected_remainder = round(383.92 * (25 - elapsed), 2)
        assert result["remainder_gbp"] == expected_remainder
        assert result["lifetime_gbp"] == round(537.49 + expected_remainder, 2)
        assert result["roi_pct"] == round(result["lifetime_gbp"] / 4427.87 * 100, 2)

    def test_the_rate_comes_from_the_input_not_a_constant(self):
        # The board may requote its annual equivalent: the same records under a
        # different stored rate must produce a different remainder.
        records = [normalise_record(_record())]
        at_fifteen = lifetime_estimate(records, 15, 2000.0, 25, None, today=date(2026, 10, 22))
        at_seventeen = lifetime_estimate(records, 17, 2000.0, 25, None, today=date(2026, 10, 22))
        assert at_fifteen["remainder_gbp"] != at_seventeen["remainder_gbp"]

    def test_missing_projection_inputs_withhold_the_whole_estimate(self):
        records = [normalise_record(_record())]
        assert lifetime_estimate(records, None, 2000.0, 25, None) is None
        assert lifetime_estimate(records, 15, None, 25, None) is None
        assert lifetime_estimate(records, 15, 2000.0, None, None) is None
        assert lifetime_estimate(records, 0, 2000.0, 25, None) is None

    def test_no_board_periods_means_a_pure_full_lifespan_estimate(self):
        result = lifetime_estimate([], 15, 2000.0, 25, None, today=date(2026, 10, 22))
        assert result["known_gbp"] is None
        assert result["elapsed_years"] == 0.0  # nothing declared, no anchor
        assert result["lifetime_gbp"] == 7500.0  # 300/year x 25, none known yet
        assert result["roi_pct"] is None

    def test_self_estimates_never_count_as_known(self):
        records = [normalise_record(_record(source="self"))]
        result = lifetime_estimate(records, 15, 2000.0, 25, None, today=date(2026, 10, 22))
        assert result["known_gbp"] is None
        # ...and a self record does not anchor the elapsed clock either.
        assert result["elapsed_years"] == 0.0

    def test_a_finished_lifespan_leaves_only_the_known(self):
        records = [normalise_record(_record(period_start="1990-01-01", period_end="1990-12-31"))]
        result = lifetime_estimate(records, 15, 2000.0, 25, 1000.0, today=date(2026, 10, 22))
        assert result["remaining_years"] == 0.0
        assert result["remainder_gbp"] == 0.0
        assert result["lifetime_gbp"] == 400.0  # only the declared actuals
        assert result["roi_pct"] == 40.0

    def test_sensor_exposes_share_and_lifetime_attrs(self):
        ledger = _loaded_ledger()
        ledger._annual_rate_p_per_w = 15.0
        ledger._lifespan_years = 25.0
        ledger._invested_gbp = 4427.87
        attrs = _sensor(ledger=ledger).extra_state_attributes

        assert attrs["share_value_gbp_per_w"] == 2.2139  # 4427.87 / 2000 W
        assert attrs["lifetime_estimate_gbp"] is not None
        assert attrs["lifetime_roi_pct"] is not None
        assert attrs["lifetime_remaining_years"] is not None
        # The declared total is untouched by any of it.
        assert attrs["total_gbp"] == 400.0

    def test_sensor_reads_the_estimate_as_unknown_when_inputs_are_missing(self):
        attrs = _sensor(ledger=_loaded_ledger()).extra_state_attributes
        assert attrs["share_value_gbp_per_w"] is None
        assert attrs["lifetime_estimate_gbp"] is None
        assert attrs["lifetime_roi_pct"] is None
        assert attrs["lifetime_remaining_years"] is None


class TestDerivedInvestment:
    """Share price × watts: the amber capital, its provenance, its ROI."""

    def test_derived_capital_is_price_times_watts(self):
        # 173.0 p/W on 2,559.465 W is the member's historic GBP 4,427.87.
        assert derived_invested_gbp(173.0, 2559.465) == 4427.87

    def test_derived_capital_needs_two_positive_inputs(self):
        assert derived_invested_gbp(None, 2559.465) is None
        assert derived_invested_gbp(173.0, None) is None
        assert derived_invested_gbp(0, 2559.465) is None
        assert derived_invested_gbp(173.0, 0) is None

    def test_the_members_own_figure_always_wins(self):
        assert effective_invested(5000.0, 4427.87) == (5000.0, "user")
        assert effective_invested(None, 4427.87) == (4427.87, "derived")
        assert effective_invested(None, None) == (None, None)
        # Investing nothing is a statement too: 0.0 is theirs, not the
        # auto-fill's, and never collapses into "unknown".
        assert effective_invested(0.0, 4427.87) == (0.0, "user")

    @pytest.mark.asyncio
    async def test_share_price_round_trips_through_the_store(self, hass, fake_store):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        await ledger.async_set_share_price(173.0)
        assert ledger.share_price_p_per_w == 173.0

        reloaded = PaymentLedger(MagicMock(), "test-entry")
        await reloaded.async_load()
        assert reloaded.share_price_p_per_w == 173.0

    @pytest.mark.asyncio
    async def test_share_price_validates_and_clears(self, hass, fake_store):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        with pytest.raises(ValueError):
            await ledger.async_set_share_price(0)
        with pytest.raises(ValueError):
            await ledger.async_set_share_price(-1)

        await ledger.async_set_share_price(173.0)
        await ledger.async_set_share_price(None)
        assert ledger.share_price_p_per_w is None

    @pytest.mark.asyncio
    async def test_a_price_never_writes_invested(self, hass, fake_store):
        # The whole invariant: the auto-fill computes, their entry stores.
        ledger = PaymentLedger(MagicMock(), "test-entry")
        await ledger.async_set_share_price(173.0)
        assert ledger.invested_gbp is None

    def test_sensor_derives_from_api_capacity_even_without_records(self):
        ledger = PaymentLedger(MagicMock(), "test-entry")
        ledger._share_price_p_per_w = 173.0
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2559.465}},
            SCOPE_SITE: {"summary": {}},
        }
        attrs = _sensor(coordinator=coordinator, ledger=ledger).extra_state_attributes

        assert attrs["capacity_watts"] == 2559.465
        assert attrs["invested_derived_gbp"] == 4427.87
        assert attrs["invested_source"] == "derived"
        assert attrs["invested_gbp"] is None
        assert attrs["total_gbp"] is None  # an empty ledger stays unknown

    def test_api_capacity_beats_the_records(self):
        ledger = _loaded_ledger()  # the record carries 2,000 W
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {
            SCOPE_OWNER: {"summary": {"capacity_watts": 2500.0}},
            SCOPE_SITE: {"summary": {}},
        }
        attrs = _sensor(coordinator=coordinator, ledger=ledger).extra_state_attributes
        assert attrs["capacity_watts"] == 2500.0

    def test_record_capacity_stands_in_without_the_api(self):
        ledger = _loaded_ledger()
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {SCOPE_OWNER: {}, SCOPE_SITE: {}}
        attrs = _sensor(coordinator=coordinator, ledger=ledger).extra_state_attributes
        assert attrs["capacity_watts"] == 2000.0

    def test_roi_quotes_derived_capital_and_the_source_says_so(self):
        ledger = _loaded_ledger()  # GBP 400 declared
        ledger._share_price_p_per_w = 173.0  # x2,000 W = GBP 3,460 derived
        attrs = _sensor(ledger=ledger).extra_state_attributes

        assert attrs["invested_gbp"] is None
        assert attrs["invested_derived_gbp"] == 3460.0
        assert attrs["invested_source"] == "derived"
        # Provisional, but present: ROI now, flagged by the source.
        assert attrs["total_roi_pct"] == round(400 / 3460 * 100, 2)
        assert attrs["records"][0]["roi_pct"] == round(400 / 3460 * 100, 2)

    def test_a_user_entry_switches_the_source_and_wins_the_roi(self):
        ledger = _loaded_ledger()
        ledger._share_price_p_per_w = 173.0
        ledger._invested_gbp = 5000.0
        attrs = _sensor(ledger=ledger).extra_state_attributes

        assert attrs["invested_source"] == "user"
        assert attrs["invested_derived_gbp"] == 3460.0  # still shown, amber-free
        assert attrs["total_roi_pct"] == 8.0  # 400 / 5000 -- theirs, not the
        # auto-fill's 11.56
