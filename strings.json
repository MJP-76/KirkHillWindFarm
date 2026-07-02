from homeassistant.helpers.update_coordinator import CoordinatorEntity


class KirkHillEntity(CoordinatorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def available(self):
        return (
            self.coordinator
            and self.coordinator.data is not None
        )
