import argparse
from argparse import Namespace

from bauh import __app_name__, __version__


def read() -> Namespace:
    parser = argparse.ArgumentParser(prog='{}-cli'.format(__app_name__), description="CLI for Linux software management")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))

    sub_parsers = parser.add_subparsers(dest='command', help='commands')
    updates_parser = sub_parsers.add_parser('updates', help='List available software updates')
    updates_parser.add_argument('-f', '--format', help='Command output format. Default: %(default)s', choices=['text', 'json'], default='text')

    return parser.parse_args()
