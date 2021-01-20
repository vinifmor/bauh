import logging
import os
from pathlib import Path

from packaging.version import parse as parse_version

from bauh import __app_name__, __version__
from bauh.api.constants import CACHE_PATH
from bauh.api.http import HttpClient
from bauh.commons.html import bold, link
from bauh.view.util.translation import I18n


def check_for_update(logger: logging.Logger, http_client: HttpClient, i18n: I18n, tray: bool = False) -> str:
    """
    :param logger:
    :param http_client:
    :param i18n:
    :param file_prefix: notification file prefix
    :return: bauh update warning string or 'None' if no update is available
    """
    logger.info("Checking for updates")

    try:
        releases = http_client.get_json('https://api.github.com/repos/vinifmor/bauh/releases')

        if releases:
            latest = None

            for r in releases:
                if not r['draft']:
                    latest = r
                    break

            if latest and latest.get('tag_name'):
                notifications_dir = '{}/updates'.format(CACHE_PATH)
                release_file = '{}/{}{}'.format(notifications_dir, '' if not tray else 'tray_', latest['tag_name'])
                if os.path.exists(release_file):
                    logger.info("Release {} already notified".format(latest['tag_name']))
                elif parse_version(latest['tag_name']) > parse_version(__version__):
                    try:
                        Path(notifications_dir).mkdir(parents=True, exist_ok=True)
                        with open(release_file, 'w+') as f:
                            f.write('')
                    except:
                        logger.error("An error occurred while trying to create the update notification file: {}".format(release_file))

                    if tray:
                        return i18n['tray.warning.update_available'].format(__app_name__, latest['tag_name'])
                    else:
                        return i18n['warning.update_available'].format(bold(__app_name__), bold(latest['tag_name']), link(latest.get('html_url', '?')))
                else:
                    logger.info("No updates available")
            else:
                logger.warning("No official release found")
        else:
            logger.warning("No releases returned from the GitHub API")
    except:
        logger.error("An error occurred while trying to retrieve the current releases")
