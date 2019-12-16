import logging

import requests

from bauh.api.http import HttpClient


def is_available(client: HttpClient, logger: logging.Logger) -> bool:
    try:
        client.exists('https://google.com')
        return True
    except requests.exceptions.ConnectionError:
        if logger:
            logger.warning('Internet connection seems to be off')
        return False

