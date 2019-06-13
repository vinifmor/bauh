import os


def get_path(resource_path):
    app_dir = get_app_dir()
    return app_dir + '/resources/' + resource_path


def get_app_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
