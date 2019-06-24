# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys
from pathlib import Path

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman
Categories = System;
Comment = Manage your Flatpak applications
Exec = /usr/bin/fpakman
Icon = /usr/lib/python{version}/site-packages/fpakman/resources/img/flathub_45.svg
""".format(version="{}.{}".format(sys.version_info.major, sys.version_info.minor))

with open('fpakman.desktop', 'w+') as f:
    f.write(desktop_file)


# cleaning the old fpakman.desktop entry model -> the following lines will be removed for the next releases
desktop_file_path = '{}/.local/share/applications/fpakman.desktop'.format(str(Path.home()))

if os.path.exists(desktop_file_path):
    os.remove(desktop_file_path)
