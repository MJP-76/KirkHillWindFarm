"""Services for the Kirk Hill Wind Farm integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SCOPE_OWNER
from .payment_ledger import MAX_NOTE_LENGTH, MAX_RATE_P_PER_W, SOURCES, get_ledger

SERVICE_RELOAD_INTEGRATION = "reload_integration"
SERVICE_RESET_DASHBOARD = "reset_dashboard"
# The ledger's write path. The card's Amount pill opens a pop-out of dated
# line items, and this is how an edit there becomes stored state -- the card
# never writes storage itself, and never touches entry.options (config v11
# purges earnings inputs; see payment_ledger).
SERVICE_ADD_PAYMENT_RECORD = "add_payment_record"
SERVICE_UPDATE_PAYMENT_RECORD = "update_payment_record"
SERVICE_REMOVE_PAYMENT_RECORD = "remove_payment_record"
# The ROI card's capital input. Kept as its own service rather than a field on
# a record: the invested amount describes the member's holding, not one period.
SERVICE_SET_INVESTED_AMOUNT = "set_invested_amount"
ATTR_ENTRY_ID = "entry_id"
ATTR_RECORD_ID = "record_id"
ATTR_PERIOD_START = "period_start"
ATTR_PERIOD_END = "period_end"
ATTR_RATE_P_PER_W = "rate_p_per_w"
ATTR_CAPACITY_WATTS = "capacity_watts"
ATTR_ANNOUNCED_ON = "announced_on"
ATTR_NOTE = "note"
ATTR_SOURCE = "source"
ATTR_INVESTED_GBP = "invested_gbp"
ATTR_CAPITAL_GBP = "capital_gbp"
ATTR_INTEREST_GBP = "interest_gbp"
SERVICE_SCHEMA_RELOAD = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
SERVICE_SCHEMA_RESET = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})

# Dates arrive from the card as "YYYY-MM-DD" strings; cv.date normalises them
# to date objects, which normalise_record accepts alongside strings.
_PERIOD_FIELDS = {
    vol.Optional(ATTR_PERIOD_START): cv.date,
    vol.Optional(ATTR_PERIOD_END): cv.date,
    vol.Optional(ATTR_RATE_P_PER_W): vol.All(
        vol.Coerce(float),
        # min_included=False: a rate of 0 is "nothing declared", which the
        # ledger expresses by having no record at all. A zero-rate record would
        # assert a payment the board never made.
        vol.Range(min=0, max=MAX_RATE_P_PER_W, min_included=False),
    ),
    vol.Optional(ATTR_CAPACITY_WATTS): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_ANNOUNCED_ON): cv.date,
    vol.Optional(ATTR_NOTE): vol.All(str, vol.Length(max=MAX_NOTE_LENGTH)),
    # Optional, and "board" when absent, so a call written before the tick
    # existed keeps announcing instead of silently becoming a self estimate.
    vol.Optional(ATTR_SOURCE): vol.In(SOURCES),
    # The capital/interest halves of a period's payment, entered by hand from
    # an Ethex statement or a board announcement. Either may be omitted; when
    # both arrive they are checked against the period's figure in
    # normalise_record and the save is rejected if they disagree.
    vol.Optional(ATTR_CAPITAL_GBP): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_INTEREST_GBP): vol.All(vol.Coerce(float), vol.Range(min=0)),
}

SERVICE_SCHEMA_ADD_PAYMENT = vol.Schema(
    {
        vol.Required(ATTR_PERIOD_START): cv.date,
        vol.Required(ATTR_PERIOD_END): cv.date,
        vol.Required(ATTR_RATE_P_PER_W): _PERIOD_FIELDS[ATTR_RATE_P_PER_W],
        vol.Optional(ATTR_CAPACITY_WATTS): _PERIOD_FIELDS[ATTR_CAPACITY_WATTS],
        vol.Optional(ATTR_ANNOUNCED_ON): cv.date,
        vol.Optional(ATTR_NOTE): _PERIOD_FIELDS[ATTR_NOTE],
        vol.Optional(ATTR_SOURCE): _PERIOD_FIELDS[ATTR_SOURCE],
        vol.Optional(ATTR_CAPITAL_GBP): _PERIOD_FIELDS[ATTR_CAPITAL_GBP],
        vol.Optional(ATTR_INTEREST_GBP): _PERIOD_FIELDS[ATTR_INTEREST_GBP],
        vol.Optional(ATTR_ENTRY_ID): str,
    }
)
SERVICE_SCHEMA_UPDATE_PAYMENT = vol.Schema(
    {
        vol.Required(ATTR_RECORD_ID): str,
        **_PERIOD_FIELDS,
        vol.Optional(ATTR_ENTRY_ID): str,
    }
)
SERVICE_SCHEMA_REMOVE_PAYMENT = vol.Schema(
    {vol.Required(ATTR_RECORD_ID): str, vol.Optional(ATTR_ENTRY_ID): str}
)
SERVICE_SCHEMA_SET_INVESTED = vol.Schema(
    {
        # JSON null clears it back to "not told": an unknown investment is a
        # different statement from having invested nothing.
        vol.Required(ATTR_INVESTED_GBP): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0))
        ),
        vol.Optional(ATTR_ENTRY_ID): str,
    }
)
# hass.data is a global namespace shared with every other integration, so the
# flag must be domain-scoped (same convention as _FRONTEND_REGISTERED in
# __init__.py). The bare "services_registered" key collided with
# flight_price_tracker, which made whichever integration loaded second skip
# registering its services entirely -- with no log line.
SERVICES_REGISTERED = f"{DOMAIN}_services_registered"


def _get_target_entry(hass: HomeAssistant, entry_id: str | None = None):
    """Return the target config entry, or raise if not found."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise HomeAssistantError(
                f"No {DOMAIN} config entry found for entry_id '{entry_id}'"
            )
        return target
    if not entries:
        raise HomeAssistantError(f"No {DOMAIN} config entry is available")
    return entries[0]


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services."""
    if hass.data.get(SERVICES_REGISTERED):
        return

    async def _async_reload_integration_service(call) -> None:
        target = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        await hass.config_entries.async_reload(target.entry_id)

    async def _async_reset_dashboard_service(call) -> None:
        from .dashboard import async_reset_dashboard  # noqa: PLC0415

        target = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        await async_reset_dashboard(hass, target)

    def _target_and_ledger(call):
        """Return (target entry, its ledger), or explain why it is not there."""
        target = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        ledger = get_ledger(hass, target.entry_id)
        if ledger is None:
            raise HomeAssistantError(
                f"The payment ledger for config entry '{target.entry_id}' is not loaded"
            )
        return target, ledger

    def _owned_watts(target) -> float:
        """Current owner capacity, used when a new record does not name one.

        Defaults to the API's capacity rather than a hard-coded number: the
        figure a record carries is what makes the historical total correct, so
        it must start from what is known now and never from a guess.
        """
        coordinator = getattr(target, "runtime_data", None)
        data = getattr(coordinator, "data", None)
        summary = (
            data.get(SCOPE_OWNER, {}).get("summary", {})
            if isinstance(data, dict)
            else {}
        )
        watts = summary.get("capacity_watts") if isinstance(summary, dict) else None
        if isinstance(watts, bool) or not isinstance(watts, (int, float)) or watts <= 0:
            raise HomeAssistantError(
                "capacity_watts is required: the API is not reporting owner capacity right now"
            )
        return float(watts)

    async def _async_add_payment_record(call) -> None:
        data = {k: v for k, v in call.data.items() if k != ATTR_ENTRY_ID}
        target, ledger = _target_and_ledger(call)
        data.setdefault(ATTR_CAPACITY_WATTS, _owned_watts(target))
        try:
            await ledger.async_add(data)
        except ValueError as err:
            raise HomeAssistantError(f"Payment record rejected: {err}") from err

    async def _async_update_payment_record(call) -> None:
        changes = {
            k: v
            for k, v in call.data.items()
            if k not in (ATTR_ENTRY_ID, ATTR_RECORD_ID)
        }
        if not changes:
            raise HomeAssistantError(
                "Nothing to update: supply at least one changed field"
            )
        _, ledger = _target_and_ledger(call)
        try:
            await ledger.async_update(call.data[ATTR_RECORD_ID], changes)
        except KeyError as err:
            raise HomeAssistantError(str(err)) from err
        except ValueError as err:
            raise HomeAssistantError(f"Payment record rejected: {err}") from err

    async def _async_remove_payment_record(call) -> None:
        _, ledger = _target_and_ledger(call)
        if not await ledger.async_remove(call.data[ATTR_RECORD_ID]):
            raise HomeAssistantError(
                f"No payment record with id '{call.data[ATTR_RECORD_ID]}'"
            )

    async def _async_set_invested_amount(call) -> None:
        _, ledger = _target_and_ledger(call)
        try:
            await ledger.async_set_invested(call.data[ATTR_INVESTED_GBP])
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD_INTEGRATION,
        _async_reload_integration_service,
        schema=SERVICE_SCHEMA_RELOAD,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_DASHBOARD,
        _async_reset_dashboard_service,
        schema=SERVICE_SCHEMA_RESET,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PAYMENT_RECORD,
        _async_add_payment_record,
        schema=SERVICE_SCHEMA_ADD_PAYMENT,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_PAYMENT_RECORD,
        _async_update_payment_record,
        schema=SERVICE_SCHEMA_UPDATE_PAYMENT,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PAYMENT_RECORD,
        _async_remove_payment_record,
        schema=SERVICE_SCHEMA_REMOVE_PAYMENT,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INVESTED_AMOUNT,
        _async_set_invested_amount,
        schema=SERVICE_SCHEMA_SET_INVESTED,
    )
    hass.data[SERVICES_REGISTERED] = True


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload domain services."""
    if not hass.data.get(SERVICES_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_RELOAD_INTEGRATION)
    hass.services.async_remove(DOMAIN, SERVICE_RESET_DASHBOARD)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_PAYMENT_RECORD)
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE_PAYMENT_RECORD)
    hass.services.async_remove(DOMAIN, SERVICE_REMOVE_PAYMENT_RECORD)
    hass.services.async_remove(DOMAIN, SERVICE_SET_INVESTED_AMOUNT)
    hass.data[SERVICES_REGISTERED] = False
