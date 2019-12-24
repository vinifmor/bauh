import argparse
import logging
import os
from argparse import Namespace

from bauh import __app_name__, __version__


def read() -> Namespace:
    parser = argparse.ArgumentParser(prog=__app_name__, description="GUI for Linux package management")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('--tray', action="store", default=os.getenv('BAUH_TRAY', 0), choices=[0, 1], type=int,
                        help='If the tray icon and update-check daemon should be created. Default: %(default)s')
    parser.add_argument('--logs', action="store", default=int(os.getenv('BAUH_LOGS', 0)), choices=[0, 1], type=int, help='If the application logs should be displayed. Default: %(default)s')
    parser.add_argument('--show-panel', action="store_true", help='Shows the management panel after the app icon is attached to the tray.')
    parser.add_argument('--reset', action="store_true", help='Removes all configuration and cache files')
    return parser.parse_args()
    
    
def validate(args: Namespace, logger: logging.Logger):

    if args.logs == 1:
        logger.info("Logs are enabled")

    return args
