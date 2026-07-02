from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KirkHillApi

_LOGGER = logging.getLogger(__name__)


class KirkHillCoordinator(DataUpdateCoordinator):
    """Kirk Hill Wind Farm coordinator."""

    def __init__(self, hass, entry):
        """Initialise coordinator."""
        self.hass = hass
        self.entry = entry

        self.api = KirkHillApi(
            base_url="https://dashboard.kirkhillcoop.org",
            api_key=entry.data["api_key"],
        )

        super().__init__(
            hass,
            logger=_LOGGER,
            name="kirkhillwindfarm",
            update_interval=timedelta(seconds=60),
        )

    @property
    def session(self):
        """Return shared aiohttp session."""
        return async_get_clientsession(self.hass)

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            session = self.session

            owner = await self._fetch_scope(session, "owner")
            site = await self._fetch_scope(session, "site")

            _LOGGER.debug("Owner data fetched successfully")
            _LOGGER.debug("Site data fetched successfully")

            data = {
                "owner": owner,
                "site": site,
            }
            
            _LOGGER.info("Coordinator data updated successfully")
            return data

        except Exception as err:
            _LOGGER.exception("Kirk Hill update failed")
            raise UpdateFailed(str(err)) from err

    async def _fetch_scope(self, session, scope: str):
        """Fetch all API endpoints for a scope."""
        try:
            summary = await self.api.summary(session, scope)
            generation = await self.api.generation(session, scope)
            wind = await self.api.wind(session, scope)
            turbines = await self.api.turbines(session, scope)
            
            _LOGGER.debug(f"[{scope}] summary fetched")
            _LOGGER.debug(f"[{scope}] generation fetched")
            _LOGGER.debug(f"[{scope}] wind fetched")
            _LOGGER.debug(f"[{scope}] turbines fetched")
            
            return {
                "summary": summary,
                "generation": generation,
                "wind": wind,
                "turbines": turbines,
            }
        except Exception as err:
            _LOGGER.error(f"Failed to fetch {scope} scope: {err}")
            raise
