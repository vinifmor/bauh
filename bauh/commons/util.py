import logging
from abc import ABC
from datetime import datetime
from logging import Logger
from typing import Optional


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


def size_to_byte(size: float, unit: str) -> int:
    lower_unit = unit.lower()

    if lower_unit[0] == 'b':
        final_size = size
    elif lower_unit[0] == 'k':
        final_size = size * 1024
    elif lower_unit[0] == 'm':
        final_size = size * (1024 ** 2)
    elif lower_unit[0] == 'g':
        final_size = size * (1024 ** 3)
    elif lower_unit[0] == 't':
        final_size = size * (1024 ** 4)
    else:
        final_size = size * (1024 ** 5)

    return round(final_size)


def datetime_as_milis(date: datetime = datetime.utcnow()) -> int:
    return int(round(date.timestamp() * 1000))


def map_timestamp_file(file_path: str) -> str:
    path_split = file_path.split('/')
    return '/'.join(path_split[0:-1]) + '/' + path_split[-1].split('.')[0] + '.ts'
