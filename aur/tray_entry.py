# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman (tray)
Categories = System;
Comment = Manage your Flatpak / Snap applications
Exec = {path}
Icon = {lib_path}/python{version}/site-packages/fpakman/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

fpakman_cmd = os.getenv('FPAKMAN_PATH', '/usr/bin/fpakman') + ' --tray=1'

with open('fpakman_tray.desktop', 'w+') as f:
    f.write(desktop_file.format(lib_path=os.getenv('FPAKMAN_LIB_PATH', '/usr/lib'),
                                version=py_version,
                                path=fpakman_cmd))


with open('fpakman-tray', 'w') as f:
    f.write(fpakman_cmd)
