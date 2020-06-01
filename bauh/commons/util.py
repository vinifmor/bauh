import collections


def deep_update(source: dict, overrides: dict):
    for key, value in overrides.items():
        if isinstance(value, dict):
            returned = deep_update(source.get(key, {}), value)
            source[key] = returned
        else:
            source[key] = overrides[key]
    return source


def size_to_byte(size: float, unit: str) -> int:
    lower_unit = unit.lower()

    if lower_unit[0] == 'b':
        final_size = size
    elif lower_unit[0] == 'k':
        final_size = size * 1000
    elif lower_unit[0] == 'm':
        final_size = size * 1000000
    elif lower_unit[0] == 't':
        final_size = size * 1000000000000
    else:
        final_size = size * 1000000000000000

    return int(final_size)
