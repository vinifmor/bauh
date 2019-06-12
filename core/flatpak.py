import re
import subprocess
from typing import List


def _package_str_to_json(line: str, version: str) -> dict:

    app_array = line.split('\t')

    if version >= '1.4.0':
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
    else:
        raise Exception('Unsupported version')

    info = re.findall('\w+:\s.+', get_info(app['id']))
    fields_to_get = ['origin', 'arch', 'ref']

    for field in info:
        field_val = field.split(':')
        field_name = field_val[0].lower()

        if field_name in fields_to_get:
            app[field_name] = field_val[1].strip()

        if field_name == 'ref':
            app['runtime'] = app['ref'].startswith('runtime/')

    return app


def _run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False) -> str:
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return res.stdout.decode() if ignore_return_code or res.returncode == expected_code else None


def get_version():
    res = _run_cmd('flatpak --version')
    return res.split(' ')[1].strip() if res else None


def get_info(app_id: str):
    return _run_cmd('flatpak info ' + app_id)


def list_installed() -> List[str]:
    apps_str = _run_cmd('flatpak list')

    if apps_str:
        version = get_version()
        app_lines = apps_str.split('\n')
        return [_package_str_to_json(line, version) for line in app_lines if line]

    return None


def check_update(pak_id: dict) -> bool:
    res = _run_cmd('flatpak update ' + pak_id)
    return 'Updating in system' in res


def update(ref: str):
    return bool(_run_cmd('flatpak update -y ' + ref))


def list_updates():
    return _run_cmd('flatpak update', ignore_return_code=True)
