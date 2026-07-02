def _get_scopes_for_entity_setup(data: dict) -> list[str]:
    """Return scopes to expose as entities.

    Owner and site are separate logical scopes and should both be exposed,
    even if their payloads are currently identical.
    """
    scopes = []

    if isinstance(data.get("owner"), dict):
        scopes.append("owner")

    if isinstance(data.get("site"), dict):
        scopes.append("site")

    return scopes
