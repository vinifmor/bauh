import subprocess
from typing import List


def _package_str_to_json(line: str, version: str) -> dict:

    app_array = line.split('\t')

    if version >= '1.4.0':
        app = {'name': app_array[0], 'id': app_array[1], 'version': app_array[2], 'branch': app_array[3], 'runtime': 'runtime' in app_array[4]}
        # TODO not working yet

    elif '1.0' <= version < '1.1':
        app = {'ref': app_array[0], 'options': app_array[1]}

        ref_data = app['ref'].split('/')
        app['id'] = ref_data[0]
        app['arch'] = ref_data[1]
        app['branch'] = ref_data[2]
        app['name'] = ref_data[0].split('.')[-1]
        app['runtime'] = 'runtime' in app['options']
    else:
        raise Exception('Unsupported version')

    return app


def _run_cmd(cmd: str) -> str:
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return res.stdout.decode() if res.returncode == 0 else None


def get_version():
    res = _run_cmd('flatpak --version')
    return res.split(' ')[1].strip() if res else None


def list_installed() -> List[str]:
    apps_str = _run_cmd('flatpak list')

    if apps_str:
        version = get_version()
        app_lines = apps_str.split('\n')
        return [_package_str_to_json(line, version) for line in app_lines if line]

    return None


def check_update(ref: dict) -> bool:
    res = _run_cmd('flatpak update ' + ref)
    return 'Updating in system' in res


def update(ref: str):
    return bool(_run_cmd('flatpak update -y ' + ref))
