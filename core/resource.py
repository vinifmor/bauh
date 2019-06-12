import os


def get_path(resource_path):
    cur_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return cur_dir + '/resources/' + resource_path
