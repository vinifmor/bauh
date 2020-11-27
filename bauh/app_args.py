import argparse
from argparse import Namespace

from bauh import __app_name__, __version__


def read() -> Namespace:
    parser = argparse.ArgumentParser(prog=__app_name__, description="GUI for Linux software management")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('--logs', action="store_true", help='It activates {} logs.'.format(__app_name__))
    parser.add_argument('--offline', action="store_true", help='It assumes the internet connection is off')

    exclusive_args = parser.add_mutually_exclusive_group()
    exclusive_args.add_argument('--tray', action="store_true", help='If {} should be attached to the system tray.'.format(__app_name__))
    exclusive_args.add_argument('--settings', action="store_true", help="Display only the settings panel")
    exclusive_args.add_argument('--reset', action="store_true", help='Remove all configuration and cache files')

    parser.add_argument_group(exclusive_args)

    return parser.parse_args()
