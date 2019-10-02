# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys

desktop_file = """
[Desktop Entry]
Type=Application
Name=bauh
Categories=System;
Comment=Manage your Flatpak / Snap / AUR applications
Comment[pt]=Gerencie seus aplicativos Flatpak / Snap / AUR
Comment[es]=Administre sus aplicaciones Flatpak / Snap / AUR
Exec = {path}
Icon = {lib_path}/python{version}/site-packages/bauh/view/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

app_cmd = os.getenv('BAUH_PATH', '/usr/bin/bauh')

with open('bauh.desktop', 'w+') as f:
    f.write(desktop_file.format(lib_path=os.getenv('BAUH_LIB_PATH', '/usr/lib'),
                                version=py_version,
                                path=app_cmd))
