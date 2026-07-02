from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class KirkHillCoordinator(DataUpdateCoordinator):
    """Central data coordinator for Kirk Hill Wind Farm."""

    def __init__(self, hass, api, update_interval: int):
        super().__init__(
            hass,
            _LOGGER,
            name="Kirk Hill Wind Farm",
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api

    async def _async_update_data(self):
        try:
            owner = await self.api.get_current(scope="owner")
            site = await self.api.get_current(scope="site")

            return {
                "owner": owner,
                "site": site,
            }

        except Exception as err:
            raise UpdateFailed(f"API update failed: {err}") from err
