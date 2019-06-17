# used for AUR installation
import os
import shutil
import subprocess
from pathlib import Path

share_path = str(Path.home()) + '/.local/share'
local_resources_path = share_path + '/fpakman'

if os.path.exists(local_resources_path):
    shutil.rmtree(local_resources_path)

os.mkdir(local_resources_path)

desktop_file = """
[Desktop Entry]
Type = Application
Name = fpakman
Categories=System;
Comment = Manage your Flatpak applications
Exec = /usr/bin/fpakman
Icon = {resource_path}/resources/img/flathub_45.svg
""".format(resource_path=local_resources_path)

apps_path = '{}/.local/share/applications'.format(str(Path.home()))

if not os.path.exists(apps_path):
    os.mkdir(apps_path)

file_path = apps_path + '/fpakman.desktop'

with open(file_path, 'w+') as f:
    f.write(desktop_file)

subprocess.run('desktop-file-install {}'.format(file_path), shell=True)
