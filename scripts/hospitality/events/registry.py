"""Hand-curated event registry (YAML) loaded into frozen `Event` models.

An event whose start date is not verified carries `start: null` (and a `verify:` note in the
YAML). Such events are excluded from ranking unless the caller asks for them: a wrong date sends
a rep to an empty room.
"""

from pathlib import Path

import yaml

from scripts.hospitality.models import Event


def load_events(path: Path, *, include_unverified: bool = False) -> list[Event]:
    """Read the registry; by default only events with a verified start date."""
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    entries = raw.get("events") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected a top-level 'events' list")  # noqa: TRY004
    events = [Event.model_validate(entry) for entry in entries]
    return [e for e in events if include_unverified or e.start is not None]
