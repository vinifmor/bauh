import glob
import locale
import os
import subprocess
import sys
from typing import Tuple

from PyQt5.QtCore import QCoreApplication

from bauh import __app_name__
from bauh.view.util import resource


def get_locale_keys(key: str = None, locale_dir: str = resource.get_path('locale')) -> Tuple[str, dict]:

    locale_path = None

    if key is None:
        current_locale = locale.getdefaultlocale()
    else:
        current_locale = [key.strip().lower()]

    if current_locale:
        current_locale = current_locale[0]

        for locale_file in glob.glob(locale_dir + '/*'):
            name = locale_file.split('/')[-1]

            if current_locale == name or current_locale.startswith(name + '_'):
                locale_path = locale_file
                break

    if not locale_path:
        locale_path = resource.get_path('locale/en')

    with open(locale_path, 'r') as f:
        locale_keys = f.readlines()

    locale_obj = {}
    for line in locale_keys:
        if line:
            keyval = line.strip().split('=')
            locale_obj[keyval[0].strip()] = keyval[1].strip()

    return locale_path.split('/')[-1], locale_obj


def notify_user(msg: str, icon_path: str = resource.get_path('img/logo.svg')):
    os.system("notify-send -a {} {} '{}'".format(__app_name__, "-i {}".format(icon_path) if icon_path else '', msg))


def restart_app(show_panel: bool):
    """
    :param show_panel: if the panel should be displayed after the app restart
    :return:
    """
    restart_cmd = [sys.executable, *sys.argv]

    if show_panel:
        restart_cmd.append('--show-panel')

    subprocess.Popen(restart_cmd)
    QCoreApplication.exit()

