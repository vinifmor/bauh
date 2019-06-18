import re
from typing import List

from fpakman.core import system


def app_str_to_json(line: str, version: str) -> dict:

    app_array = line.split('\t')

    if version >= '1.3.0':
        app = {'name': app_array[0],
               'id': app_array[1],
               'version': app_array[2],
               'branch': app_array[3]}
    elif '1.0' <= version < '1.1':
        app = {'ref': app_array[0], 'options': app_array[1]}

        ref_data = app['ref'].split('/')
        app['id'] = ref_data[0]
        app['arch'] = ref_data[1]
        app['branch'] = ref_data[2]
        app['name'] = ref_data[0].split('.')[-1]
        app['version'] = None
    elif '1.2' <= version < '1.3':
        app = {'name': app_array[1].strip().split('.')[-1],
               'id': app_array[1],
               'version': app_array[2],
               'branch': app_array[3],
               'arch': app_array[4],
               'origin': app_array[5]}
    else:
        raise Exception('Unsupported version')

    info = re.findall('\w+:\s.+', get_app_info(app['id']))
    fields_to_get = ['origin', 'arch', 'ref']

    for field in info:
        field_val = field.split(':')
        field_name = field_val[0].lower()

        if field_name in fields_to_get:
            app[field_name] = field_val[1].strip()

        if field_name == 'ref':
            app['runtime'] = app['ref'].startswith('runtime/')

    return app


def get_version():
    res = system.run_cmd('flatpak --version')
    return res.split(' ')[1].strip() if res else None


def get_app_info(app_id: str):
    return system.run_cmd('flatpak info ' + app_id)


def list_installed() -> List[dict]:
    apps_str = system.run_cmd('flatpak list')

    if apps_str:
        version = get_version()
        app_lines = apps_str.split('\n')
        return [app_str_to_json(line, version) for line in app_lines if line]

    return []


def update(app_ref: str) -> bool:
    return bool(system.run_cmd('flatpak update -y ' + app_ref))


def update_and_stream(app_ref: str):
    """
    Updates the app reference and streams Flatpak output,
    :param app_ref:
    :return:
    """
    return system.stream_cmd(['flatpak', 'update', '-y', app_ref])


def list_updates_as_str():
    return system.run_cmd('flatpak update', ignore_return_code=True)
