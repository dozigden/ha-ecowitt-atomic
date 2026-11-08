"""Registration types from HTTP API v1.0.6, section 7 (not display order)."""

from collections import defaultdict
import re

# Include channel and reserved entries when deciding whether a designation is
# singular. Registration presence never changes catalogue cardinality.
REGISTRATION_CATALOGUE = {
    0: "wh65",
    1: "wh68",
    2: "wh80",
    3: "wh40",
    4: "wh25",
    5: "wh26",
    **dict.fromkeys(range(6, 14), "wh31"),
    **dict.fromkeys(range(14, 22), "wh51"),
    **dict.fromkeys(range(22, 26), "wh41"),
    26: "wh57",
    **dict.fromkeys(range(27, 31), "wh55"),
    **dict.fromkeys(range(31, 39), "wh34"),
    39: "wh45",
    **dict.fromkeys(range(40, 48), "wh35"),
    48: "wh90",
    49: "wh85",
    **dict.fromkeys(range(50, 58), "wh48"),
    **dict.fromkeys(range(58, 66), "wh51"),
    **dict.fromkeys(range(66, 70), "wh54"),
    70: "wn20",
    71: "wn38",
}


def _singleton_types() -> dict[str, int]:
    """Index only designations occupying one catalogue entry."""
    slots: dict[str, list[int]] = defaultdict(list)
    for slot, designation in REGISTRATION_CATALOGUE.items():
        slots[designation].append(slot)
    return {name: values[0] for name, values in slots.items() if len(values) == 1}


SINGLETON_TYPES = _singleton_types()


def singleton_property(field: str) -> tuple[int, str] | None:
    """Split a WS/WH-prefixed property with a unique catalogue designation."""
    match = re.fullmatch(r"w[sh]([0-9]+)([^0-9].*)", field, re.IGNORECASE)
    if match is None:
        return None
    slot = SINGLETON_TYPES.get(f"wh{match[1]}")
    return (slot, match[2].lower()) if slot is not None else None
