import os
import shutil
import subprocess
import sys
import traceback
from typing import List, Tuple

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtGui import QIcon
from colorama import Fore

from bauh import __app_name__
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.constants import CACHE_PATH, CONFIG_PATH
from bauh.commons.system import run_cmd
from bauh.view.util import resource


def notify_user(msg: str, icon_path: str = None):
    icon_id = icon_path

    if not icon_id:
        icon_id = get_default_icon()[0]

    os.system("notify-send -a {} {} '{}'".format(__app_name__, "-i {}".format(icon_id) if icon_id else '', msg))


def get_default_icon(system: bool = True) -> Tuple[str, QIcon]:
    if system:
        system_icon = QIcon.fromTheme(__app_name__)
        if not system_icon.isNull():
            return system_icon.name(), system_icon

    path = resource.get_path('img/logo.svg')
    return path, QIcon(path)


def restart_app():
    """
    :param show_panel: if the panel should be displayed after the app restart
    :return:
    """
    restart_cmd = [sys.executable, *sys.argv]
    subprocess.Popen(restart_cmd)
    QCoreApplication.exit()


def get_distro():
    if os.path.exists('/etc/arch-release'):
        return 'arch'

    if os.path.exists('/proc/version'):
        if 'ubuntu' in run_cmd('cat /proc/version').lower():
            return 'ubuntu'

    return 'unknown'


def clean_app_files(managers: List[SoftwareManager], logs: bool = True):

    if logs:
        print('[bauh] Cleaning configuration and cache files')

    for path in (CACHE_PATH, CONFIG_PATH):
        if logs:
            print('[bauh] Deleting directory {}'.format(path))

        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                if logs:
                    print('{}[bauh] Directory {} deleted{}'.format(Fore.YELLOW, path, Fore.RESET))
            except:
                if logs:
                    print('{}[bauh] An exception has happened when deleting {}{}'.format(Fore.RED, path, Fore.RESET))
                    traceback.print_exc()

    if managers:
        for m in managers:
            m.clear_data()

    if logs:
        print('[bauh] Cleaning finished')
