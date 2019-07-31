# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys
from pathlib import Path

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman{desc}
Categories = System;
Comment = Manage your Flatpak / Snap applications
Exec = /usr/bin/fpakman{param}
Icon = /usr/lib/python{version}/site-packages/fpakman/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

with open('fpakman.desktop', 'w+') as f:
    f.write(desktop_file.format(desc='', version=py_version, param=' --tray 0'))

with open('fpakman_tray.desktop', 'w+') as f:
    f.write(desktop_file.format(desc=' ( tray )', version=py_version, param=''))


# cleaning the old fpakman.desktop entry model -> the following lines will be removed for the next releases
desktop_file_path = '{}/.local/share/applications/fpakman.desktop'.format(str(Path.home()))

if os.path.exists(desktop_file_path):
    os.remove(desktop_file_path)
