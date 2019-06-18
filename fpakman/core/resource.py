import os

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_path(resource_path):
    return app_dir + '/resources/' + resource_path
