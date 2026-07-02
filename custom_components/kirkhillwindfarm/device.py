"""Device helpers for Kirk Hill Wind Farm integration."""


def get_device_info(entry, scope):
    """Return device info for the scope."""
    scope_label = "Owner" if scope == "owner" else "Site"
    
    return {
        "identifiers": {("kirkhillwindfarm", f"{entry.entry_id}_{scope}")},
        "name": f"Kirk Hill Wind Farm {scope_label}",
        "manufacturer": "Kirk Hill Cooperative",
        "model": "Wind Farm",
    }
