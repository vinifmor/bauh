# Generates a .desktop file based on the current python version. Used for AUR installation
import os
import sys
import locale

system_locale = locale.getdefaultlocale()[0].split('_')[0]

if system_locale == 'pt':
    comment = "Gerencie seus aplicativos Flatpak / Snap / AUR "
elif system_locale == 'es':
    comment = "Administre sus aplicaciones Flatpak / Snap / AUR"
else:
    comment = "Manage your Flatpak / Snap / AUR applications"

desktop_file = """
[Desktop Entry]
Type = Application
Name = bauh
Categories = System;
Comment = {comment}
Exec = {path}
Icon = {lib_path}/python{version}/site-packages/bauh/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

app_cmd = os.getenv('BAUH_PATH', '/usr/bin/bauh')

with open('bauh.desktop', 'w+') as f:
    f.write(desktop_file.format(lib_path=os.getenv('BAUH_LIB_PATH', '/usr/lib'),
                                version=py_version,
                                path=app_cmd,
                                comment=comment))
