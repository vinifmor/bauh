import re
import subprocess
from datetime import datetime
from io import StringIO
from typing import List

from bauh.api.exception import NoInternetException
from bauh.commons.system import new_subprocess, run_cmd, new_root_subprocess

BASE_CMD = 'flatpak'
RE_SEVERAL_SPACES = re.compile(r'\s+')


def get_app_info_fields(app_id: str, branch: str, fields: List[str] = [], check_runtime: bool = False):
    info = re.findall(r'\w+:\s.+', get_app_info(app_id, branch))
    data = {}
    fields_to_retrieve = len(fields) + (1 if check_runtime and 'ref' not in fields else 0)

    for field in info:

        if fields and fields_to_retrieve == 0:
            break

        field_val = field.split(':')
        field_name = field_val[0].lower()

        if not fields or field_name in fields or (check_runtime and field_name == 'ref'):
            data[field_name] = field_val[1].strip()

            if fields:
                fields_to_retrieve -= 1

        if check_runtime and field_name == 'ref':
            data['runtime'] = data['ref'].startswith('runtime/')

    return data


def get_fields(app_id: str, branch: str, fields: List[str]) -> List[str]:
    cmd = [BASE_CMD, 'info', app_id]

    if branch:
        cmd.append(branch)

    info = new_subprocess(cmd).stdout

    res = []
    for o in new_subprocess(['grep', '-E', '({}):.+'.format('|'.join(fields)), '-o'], stdin=info).stdout:
        if o:
            res.append(o.decode().split(':')[-1].strip())

    return res


def is_installed():
    version = get_version()
    return False if version is None else True


def get_version():
    res = run_cmd('{} --version'.format(BASE_CMD), print_error=False)
    return res.split(' ')[1].strip() if res else None


def get_app_info(app_id: str, branch: str):
    return run_cmd('{} info {} {}'.format(BASE_CMD, app_id, branch))


def get_commit(app_id: str, branch: str) -> str:
    info = new_subprocess([BASE_CMD, 'info', app_id, branch])

    for o in new_subprocess(['grep', 'Commit:', '--color=never'], stdin=info.stdout).stdout:
        if o:
            return o.decode().split(':')[1].strip()


def list_installed(version: str) -> List[dict]:

    apps = []

    if version < '1.2':
        app_list = new_subprocess([BASE_CMD, 'list', '-d'])

        for o in app_list.stdout:
            if o:
                data = o.decode().strip().split('\t')
                ref_split = data[0].split('/')
                runtime = 'runtime' in data[5]

                apps.append({
                    'id': ref_split[0],
                    'name': ref_split[0].split('.')[-1].capitalize(),
                    'ref': data[0],
                    'arch': ref_split[1],
                    'branch': ref_split[2],
                    'description': None,
                    'origin': data[1],
                    'runtime': runtime,
                    'version': ref_split[2] if runtime else None
                })

    else:
        cols = 'application,ref,arch,branch,description,origin,options,{}version'.format('' if version < '1.3' else 'name,')
        app_list = new_subprocess([BASE_CMD, 'list', '--columns=' + cols])

        for o in app_list.stdout:
            if o:
                data = o.decode().strip().split('\t')
                runtime = 'runtime' in data[6]

                if version < '1.3':
                    name = data[0].split('.')[-1]

                    if len(data) > 7 and data[7]:
                        app_ver = data[7]
                    elif runtime:
                        app_ver = data[3]
                    else:
                        app_ver = None
                else:
                    name = data[7]

                    if len(data) > 8 and data[8]:
                        app_ver = data[8]
                    elif runtime:
                        app_ver = data[3]
                    else:
                        app_ver = None

                apps.append({'id': data[0],
                             'name': name,
                             'ref': data[1],
                             'arch': data[2],
                             'branch': data[3],
                             'description': data[4],
                             'origin': data[5],
                             'runtime': runtime,
                             'version': app_ver})
    return apps


def update(app_ref: str):
    """
    Updates the app reference
    :param app_ref:
    :return:
    """
    return new_subprocess([BASE_CMD, 'update', '--no-related', '-y', app_ref])


def uninstall(app_ref: str):
    """
    Removes the app by its reference
    :param app_ref:
    :return:
    """
    return new_subprocess([BASE_CMD, 'uninstall', app_ref, '-y'])


def list_updates_as_str(version: str):
    if version < '1.2':
        return run_cmd('{} update --no-related'.format(BASE_CMD), ignore_return_code=True)
    else:
        updates = new_subprocess([BASE_CMD, 'update']).stdout

        out = StringIO()

        reg = r'[0-9]+\.\s+(\w+|\.)+\s+(\w|\.)+' if version >= '1.5.0' else r'[0-9]+\.\s+(\w+|\.)+\s+\w+\s+(\w|\.)+'

        for o in new_subprocess(['grep', '-E', reg, '-o', '--color=never'], stdin=updates).stdout:
            if o:
                out.write('/'.join(o.decode().strip().split('\t')[2:]) + '\n')

        out.seek(0)
        return out.read()


def downgrade(app_ref: str, commit: str, root_password: str) -> subprocess.Popen:
    return new_root_subprocess([BASE_CMD, 'update', '--no-related', '--commit={}'.format(commit), app_ref, '-y'], root_password)


def get_app_commits(app_ref: str, origin: str) -> List[str]:
    log = run_cmd('{} remote-info --log {} {}'.format(BASE_CMD, origin, app_ref))

    if log:
        return re.findall(r'Commit+:\s(.+)', log)
    else:
        raise NoInternetException()


def get_app_commits_data(app_ref: str, origin: str) -> List[dict]:
    log = run_cmd('{} remote-info --log {} {}'.format(BASE_CMD, origin, app_ref))

    if not log:
        raise NoInternetException()

    res = re.findall(r'(Commit|Subject|Date):\s(.+)', log)

    commits = []

    commit = {}

    for idx, data in enumerate(res):
        attr = data[0].strip().lower()
        commit[attr] = data[1].strip()

        if attr == 'date':
            commit[attr] = datetime.strptime(commit[attr], '%Y-%m-%d %H:%M:%S +0000')

        if (idx + 1) % 3 == 0:
            commits.append(commit)
            commit = {}

    return commits


def search(version: str, word: str, app_id: bool = False) -> List[dict]:

    res = run_cmd('{} search {}'.format(BASE_CMD, word))

    found = []

    split_res = res.split('\n')

    if split_res and split_res[0].lower() != 'no matches found':
        for info in split_res:
            if info:
                info_list = info.split('\t')
                if version >= '1.3.0':
                    id_ = info_list[2].strip()

                    if app_id and id_ != word:
                        continue

                    pkg_ver = info_list[3].strip()
                    app = {
                        'name': info_list[0].strip(),
                        'description': info_list[1].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[4].strip(),
                        'origin': info_list[5].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }
                elif version >= '1.2.0':
                    id_ = info_list[1].strip()

                    if app_id and id_ != word:
                        continue

                    desc = info_list[0].split('-')
                    pkg_ver = info_list[2].strip()
                    app = {
                        'name': desc[0].strip(),
                        'description': desc[1].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[3].strip(),
                        'origin': info_list[4].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }
                else:
                    id_ = info_list[0].strip()

                    if app_id and id_ != word:
                        continue

                    pkg_ver = info_list[1].strip()
                    app = {
                        'name': '',
                        'description': info_list[4].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[2].strip(),
                        'origin': info_list[3].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }

                found.append(app)

                if app_id and len(found) > 0:
                    break

    return found


def install(app_id: str, origin: str):
    return new_subprocess([BASE_CMD, 'install', origin, app_id, '-y'])


def set_default_remotes():
    run_cmd('{} remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo'.format(BASE_CMD))


def has_remotes_set() -> bool:
    return bool(run_cmd('{} remotes'.format(BASE_CMD)).strip())


def run(app_id: str):
    subprocess.Popen([BASE_CMD, 'run', app_id])
