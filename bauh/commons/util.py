import logging
from abc import ABC
from datetime import datetime
from logging import Logger
from typing import Optional, Union


class NullLoggerFactory(ABC):

    __instance: Optional[Logger] = None

    @classmethod
    def logger(cls) -> Logger:
        if cls.__instance is None:
            cls.__instance = logging.getLogger('__null__')
            cls.__instance.addHandler(logging.NullHandler())

        return cls.__instance


def deep_update(source: dict, overrides: dict):
    for key, value in overrides.items():
        if isinstance(value, dict):
            returned = deep_update(source.get(key, {}), value)
            source[key] = returned
        else:
            source[key] = overrides[key]
    return source


def size_to_byte(size: Union[float, int, str], unit: str, logger: Optional[Logger] = None) -> Optional[float]:
    lower_unit = unit.strip().lower()

    if isinstance(size, str):
        try:
            final_size = float(size.strip().replace(',', '.').replace(' ', ''))
        except ValueError:
            if logger:
                logger.error(f"Could not parse string size {size} to bytes")
            return
    else:
        final_size = float(size)

    if unit == 'b':
        return final_size / 8

    if unit == 'B':
        return final_size

    base = 1024 if lower_unit.endswith('ib') else 1000

    if lower_unit[0] == 'k':
        return final_size * base
    elif lower_unit[0] == 'm':
        return final_size * (base ** 2)
    elif lower_unit[0] == 'g':
        return final_size * (base ** 3)
    elif lower_unit[0] == 't':
        return final_size * (base ** 4)
    else:
        return final_size * (base ** 5)


def datetime_as_milis(date: datetime = datetime.utcnow()) -> int:
    return int(round(date.timestamp() * 1000))


def map_timestamp_file(file_path: str) -> str:
    path_split = file_path.split('/')
    return '/'.join(path_split[0:-1]) + '/' + path_split[-1].split('.')[0] + '.ts'
