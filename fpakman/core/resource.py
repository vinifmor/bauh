import os
from pathlib import Path

local_resource_path = '{}/.local/share/fpakman/resources'.format(str(Path.home()))
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_path(resource_path):

    if os.path.exists(local_resource_path):
        return local_resource_path + '/' + resource_path
    else:
        return app_dir + '/resources/' + resource_path
