import logging
from logging import INFO

FORMAT = '%(asctime)s %(levelname)s [%(module_path)s:%(lineno)s - %(funcName)s()] - %(message)s'


class FilePathFilter(logging.Filter):

    def filter(self, record):
        record.module_path = record.pathname.split('site-packages/')[1] if 'site-packages' in record.pathname else str(record.pathname)
        return True


def new_logger(name: str, enabled: bool) -> logging.Logger:
    instance = logging.Logger(name, level=INFO)
    instance.addFilter(FilePathFilter())
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(FORMAT))
    instance.addHandler(stream_handler)
    instance.disabled = not enabled

    return instance
