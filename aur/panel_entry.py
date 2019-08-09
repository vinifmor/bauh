# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman
Categories = System;
Comment = Manage your Flatpak / Snap applications
Exec = {path}
Icon = {lib_path}/python{version}/site-packages/fpakman/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

fpakman_cmd = os.getenv('FPAKMAN_PATH', '/usr/bin/fpakman')

with open('fpakman_desktop.desktop', 'w+') as f:
    f.write(desktop_file.format(lib_path=os.getenv('FPAKMAN_LIB_PATH', '/usr/lib'),
                                version=py_version,
                                path=fpakman_cmd))


with open('fpakman', 'w') as f:
    f.write(fpakman_cmd)
