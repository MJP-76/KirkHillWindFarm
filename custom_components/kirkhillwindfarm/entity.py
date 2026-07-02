"""Base entity for Kirk Hill Wind Farm integration."""

from homeassistant.helpers.entity import Entity
from .const import DOMAIN


class KirkHillEntity(Entity):
    """Base entity for Kirk Hill Wind Farm."""

    @property
    def attribution(self):
        return "Kirk Hill Cooperative Wind Farm"
