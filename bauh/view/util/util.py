import os
import subprocess
import sys

from PyQt5.QtCore import QCoreApplication

from bauh import __app_name__
from bauh.commons.system import run_cmd
from bauh.view.util import resource


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


def get_distro():
    if os.path.exists('/etc/arch-release'):
        return 'arch'

    if os.path.exists('/proc/version'):
        if 'ubuntu' in run_cmd('cat /proc/version').lower():
            return 'ubuntu'

    return 'unknown'
