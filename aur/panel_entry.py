# Generates a .desktop file based on the current python version. Used for AUR installation
import sys

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman
Categories = System;
Comment = Manage your Flatpak / Snap applications
Exec = /usr/bin/fpakman --tray=0
Icon = /usr/lib/python{version}/site-packages/fpakman/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

with open('fpakman.desktop', 'w+') as f:
    f.write(desktop_file.format(version=py_version))
