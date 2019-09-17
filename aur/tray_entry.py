# Generates a .desktop file based on the current python version. Used for AUR installation
import locale
import os
import sys

system_locale = locale.getdefaultlocale()[0].split('_')[0]

if system_locale == 'pt':
    comment = "Gerencie seus aplicativos Flatpak / Snap / AUR "
    tray = 'bandeja'
elif system_locale == 'es':
    comment = "Administre sus aplicaciones Flatpak / Snap / AUR"
    tray = 'bandeja'
else:
    comment = "Manage your Flatpak / Snap / AUR applications"
    tray = 'tray'

desktop_file = """
[Desktop Entry]
Type = Application
Name = bauh ( {tray} )
Categories = System;
Comment = {comment}
Exec = {path}
Icon = {lib_path}/python{version}/site-packages/bauh/resources/img/logo.svg
"""

py_version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

app_cmd = os.getenv('BAUH_PATH', '/usr/bin/bauh') + ' --tray=1'

with open('bauh_tray.desktop', 'w+') as f:
    f.write(desktop_file.format(lib_path=os.getenv('BAUH_LIB_PATH', '/usr/lib'),
                                version=py_version,
                                path=app_cmd,
                                comment=comment,
                                tray=tray))


with open('bauh-tray', 'w') as f:
    f.write(app_cmd)
