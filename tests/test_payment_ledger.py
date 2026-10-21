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
    BASIS_ESTIMATED,
    BASIS_NO_ENTRIES,
    PaymentLedger,
    async_setup_ledger,
    async_unload_ledger,
    current_figure,
    current_year_gbp,
    get_ledger,
    latest_board_record,
    latest_record,
    ledger_store,
    ledger_total_gbp,
    normalise_record,
    record_value_gbp,
    roi_pct,
    source_totals_gbp,
    year_totals_gbp,
)
from custom_components.kirkhill_wind.sensor import PaymentLedgerSensor
from custom_components.kirkhill_wind.services import (
    SERVICE_ADD_PAYMENT_RECORD,
    SERVICE_REMOVE_PAYMENT_RECORD,
    SERVICE_SCHEMA_ADD_PAYMENT,
    SERVICE_SCHEMA_SET_INVESTED,
    SERVICE_SET_INVESTED_AMOUNT,
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

    def test_time_past_the_last_declaration_is_an_estimate(self):
        value, basis = current_figure([normalise_record(_record())])
        assert basis == BASIS_ESTIMATED
        # Derived from the last declared rate -- the same 400, marked as pending.
        assert value == 400.0

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

    def test_past_period_is_reported_as_an_estimate(self):
        sensor = _sensor()
        attrs = sensor.extra_state_attributes
        # Today is past PAST_END, so the figure is pending, not declared -- and
        # it stays out of the total either way.
        assert attrs["current_basis"] == BASIS_ESTIMATED
        assert attrs["current_gbp"] == 400.0
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
