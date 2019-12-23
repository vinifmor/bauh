import logging
import re
import subprocess
from io import StringIO
from typing import List, Tuple

from bauh.commons.system import new_root_subprocess, run_cmd, new_subprocess, SimpleProcess
from bauh.gems.snap.model import SnapApplication

BASE_CMD = 'snap'
RE_SNAPD_STATUS = re.compile('\s+')
SNAPD_RUNNING_STATUS = {'listening', 'running'}


def is_installed():
    res = run_cmd('which snap', print_error=False)
    return res and not res.strip().startswith('which ')


def is_snapd_running() -> bool:
    services = new_subprocess(['systemctl', 'list-units'])

    service, service_running = False, False
    socket, socket_running = False, False
    for o in new_subprocess(['grep', '-Eo', 'snapd.+'], stdin=services.stdout).stdout:
        if o:
            line = o.decode().strip()

            if line:
                line_split = RE_SNAPD_STATUS.split(line)
                running = line_split[3] in SNAPD_RUNNING_STATUS

                if line_split[0] == 'snapd.service':
                    service = True
                    service_running = running
                elif line_split[0] == 'snapd.socket':
                    socket = True
                    socket_running = running

    return socket and socket_running and (not service or service_running)


def app_str_to_json(app: str) -> dict:
    app_data = [word for word in app.split(' ') if word]
    app_json = {
        'name': app_data[0],
        'version': app_data[1],
        'rev': app_data[2],
        'tracking': app_data[3],
        'publisher': app_data[4] if len(app_data) >= 5 else None,
        'notes': app_data[5] if len(app_data) >= 6 else None
    }

    return app_json


def get_info(app_name: str, attrs: tuple = None):
    full_info_lines = run_cmd('{} info {}'.format(BASE_CMD, app_name))

    data = {}

    if full_info_lines:
        re_attrs = r'\w+' if not attrs else '|'.join(attrs)
        info_map = re.findall(r'({}):\s+(.+)'.format(re_attrs), full_info_lines)

        for info in info_map:
            val = info[1].strip()

            if info[0] == 'installed':
                val_split = [s for s in val.split(' ') if s]
                data['version'] = val_split[0]

                if len(val_split) > 2:
                    data['size'] = val_split[2]
            else:
                data[info[0]] = val

        if not attrs or 'description' in attrs:
            desc = re.findall(r'\|\n+((\s+.+\n+)+)', full_info_lines)
            data['description'] = ''.join([w.strip() for w in desc[0][0].strip().split('\n')]).replace('.', '.\n') if desc else None

        if not attrs or 'commands' in attrs:
            commands = re.findall(r'commands:\s*\n*((\s+-\s.+\s*\n)+)', full_info_lines)
            data['commands'] = commands[0][0].strip().replace('- ', '').split('\n') if commands else None

    return data


def read_installed(ubuntu_distro: bool) -> List[dict]:
    res = run_cmd('{} list'.format(BASE_CMD), print_error=False)

    apps = []

    if res and len(res) > 0:
        lines = res.split('\n')

        if not lines[0].startswith('error'):
            for idx, app_str in enumerate(lines):
                if idx > 0 and app_str:
                    apps.append(app_str_to_json(app_str))

            info_path = _get_app_info_path(ubuntu_distro)

            info_out = new_subprocess(['cat', *[info_path.format(a['name']) for a in apps]]).stdout

            idx = -1
            for o in new_subprocess(['grep', '-E', '(summary|apps)', '--colour=never'], stdin=info_out).stdout:
                if o:
                    line = o.decode()

                    if line.startswith('summary:'):
                        idx += 1
                        apps[idx]['summary'] = line.split(':')[1].strip()
                    else:
                        apps[idx]['apps_field'] = True

    return apps


def _get_app_info_path(ubuntu_distro: bool) -> str:
    if ubuntu_distro:
        return '/snap/{}/current/meta/snap.yaml'
    else:
        return '/var/lib/snapd/snap/{}/current/meta/snap.yaml'


def has_apps_field(name: str, ubuntu_distro: bool) -> bool:
    info_path = _get_app_info_path(ubuntu_distro)

    info_out = new_subprocess(['cat', info_path.format(name)]).stdout

    res = False
    for o in new_subprocess(['grep', '-E', 'apps', '--colour=never'], stdin=info_out).stdout:
        if o:
            line = o.decode()

            if line.startswith('apps:'):
                res = True

    return res


def search(word: str, exact_name: bool = False) -> List[dict]:
    apps = []

    res = run_cmd('{} find "{}"'.format(BASE_CMD, word), print_error=False)

    if res:
        res = res.split('\n')

        if not res[0].startswith('No matching'):
            for idx, app_str in enumerate(res):
                if idx > 0 and app_str:
                    app_data = [word for word in app_str.split(' ') if word]

                    if exact_name and app_data[0] != word:
                        continue

                    apps.append({
                        'name': app_data[0],
                        'version': app_data[1],
                        'publisher': app_data[2],
                        'notes': app_data[3] if app_data[3] != '-' else None,
                        'summary': app_data[4] if len(app_data) == 5 else '',
                        'rev': None,
                        'tracking': None,
                        'type': None
                    })

                if exact_name and len(apps) > 0:
                    break

    return apps


def uninstall_and_stream(app_name: str, root_password: str):
    return new_root_subprocess([BASE_CMD, 'remove', app_name], root_password)


def install_and_stream(app_name: str, confinement: str, root_password: str) -> SimpleProcess:

    install_cmd = [BASE_CMD, 'install', app_name]  # default

    if confinement == 'classic':
        install_cmd.append('--classic')

    # return new_root_subprocess(install_cmd, root_password)
    return SimpleProcess(install_cmd, root_password=root_password)


def downgrade_and_stream(app_name: str, root_password: str) -> subprocess.Popen:
    return new_root_subprocess([BASE_CMD, 'revert', app_name], root_password)


def refresh_and_stream(app_name: str, root_password: str) -> subprocess.Popen:
    return new_root_subprocess([BASE_CMD, 'refresh', app_name], root_password)


def run(app: SnapApplication, logger: logging.Logger):
    info = get_info(app.name, 'commands')
    app_name = app.name.lower()

    if info.get('commands'):

        logger.info('Available commands found for {}: {}'.format(app_name, info['commands']))

        commands = [c.strip() for c in info['commands']]

        # trying to find an exact match command:
        command = None

        for c in commands:
            if c.lower() == app_name:
                command = c
                logger.info("Found exact match command for '{}'".format(app_name))
                break

        if not command:
            for c in commands:
                if not c.endswith('.apm'):
                    command = c

        if command:
            logger.info("Running '{}'".format(command))
            subprocess.Popen([BASE_CMD, 'run', command])
            return

        logger.error("No valid command found for '{}'".format(app_name))
    else:
        logger.error("No command found for '{}'".format(app_name))


def is_api_available() -> Tuple[bool, str]:
    output = StringIO()
    for o in SimpleProcess(['snap', 'search']).instance.stdout:
        if o:
            output.write(o.decode())

    output.seek(0)
    output = output.read()
    return 'error:' not in output, output
