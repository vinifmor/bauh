import sys
from typing import List, Dict

from bauh_api.abstract.component import ComponentsManager, Component, ComponentType
from bauh_commons.system import run_cmd, new_subprocess

from bauh.component.github import GitHubClient

PIP_PATH = '/'.join(sys.executable.split('/')[0:-1]) + '/pip'

# requirements URL -> https://github.com/vinifmor/bauh/blob/0.5.2/requirements.txt


def map_type(name: str):
    if name == 'bauh':
        return ComponentType.APPLICATION
    elif name in {'bauh_api', 'bauh_commons'}:
        return ComponentType.LIBRARY
    else:
        return ComponentType.GEM


class PythonComponentsManager(ComponentsManager):

    def __init__(self):
        self.github_client = GitHubClient()

    def _list_outdated(self) -> Dict[ComponentType, List[Component]]:
        outdated = new_subprocess([PIP_PATH, 'list', '--oudated'], global_interpreter=False).stdout

        comps = {}
        for o in new_subprocess(['grep', 'bauh'], stdin=outdated).stdout:
            line = o.decode().strip() if o else None
            if line:
                pkg_info = line.split(' ')
                comp_type = map_type(pkg_info[0])

                comp_list = comps.get(comp_type)

                if not comp_list:
                    comp_list = []
                    comps[comp_type] = comp_list

                comp_list.append(Component(name=pkg_info[0],
                                           version=pkg_info[1],
                                           new_version=pkg_info[2],
                                           type=comp_type))

        return comps

    def list_outdated_git(self):
        installed = new_subprocess([PIP_PATH, 'list'], global_interpreter=False).stdout

        comps = {}
        for o in new_subprocess(['grep', 'bauh'], stdin=installed).stdout:
            line = o.decode().strip() if o else None
            if line:
                pkg_info = line.split(' ')
                comps[pkg_info[0]] = pkg_info[-1]

        print(comps)
        if comps:
            latest = self.github_client.list_components(comps.keys())
            print(latest)

    def list_updates(self) -> List[Component]:
        print(self.list_outdated_git())
        # comps = self._list_outdated()
        #
        # if comps:
        #     app_update = comps.get(ComponentType.APPLICATION)
        #     # TODO
        #
        # return []

    def update(self, component: Component):
        pass

    def is_enabled(self) -> bool:
        return bool(run_cmd('pip --version', global_interpreter=False))


PythonComponentsManager().list_updates()