import sys
from typing import List, Dict

from bauh_api.abstract.component import ComponentsManager, Component, ComponentType, ComponentUpdate
from bauh_commons.system import run_cmd, new_subprocess

from bauh.component import requirements
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
        outdated = new_subprocess([PIP_PATH, 'list', '--oudated']).stdout

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

    def list_components_git(self) -> Dict[ComponentType, Dict[str, Component]]:
        python_comps = new_subprocess([PIP_PATH, 'list']).stdout

        installed = {}
        for o in new_subprocess(['grep', 'bauh'], stdin=python_comps).stdout:
            line = o.decode().strip() if o else None
            if line:
                pkg_info = line.split(' ')
                installed[pkg_info[0]] = pkg_info[-1]

        comps = {t: {} for t in ComponentType}

        if installed:
            latest = self.github_client.list_components(installed.keys())

            if latest:
                for pkg, version in installed.items():
                    comp = Component(name=pkg, version=version, new_version=version, type=map_type(pkg))

                    if pkg in latest:
                        comp.new_version = latest[pkg]

                    comps[comp.type][pkg] = comp
            else:
                print('Could not retrieve the latest versions')

        return comps

    def _check_commons(self, commons: Component, api: Component) -> bool:
        reqs_text = self.github_client.get_requirements('bauh_commons', commons.new_version)

        if reqs_text:
            commons_reqs = requirements.full_parse(reqs_text)

            commons_api = commons_reqs.get('bauh_api')

            if commons_api:
                res = commons_api.accepts(api.new_version)
                if not res:
                    print("'bauh_commons' is not compatible with 'bauh_api' ({}). Aborting...".format(api.new_version))

                return res

            return True
        return False

    def _check_gui(self, gui: Component, api: Component, commons: Component):
        # the GUI update type does not matter:
        reqs_text = self.github_client.get_requirements(gui.name, gui.new_version)

        if reqs_text:
            gui_reqs = requirements.full_parse(reqs_text)

            if not gui_reqs:
                print("Could not retrieve 'bauh' requirements from 'requirements.txt'")
            else:
                if not gui_reqs.get('bauh_api'):
                    print("Could not retrieve 'bauh_api' requirement version for 'bauh'")
                    return False
                elif not gui_reqs['bauh_api'].accepts(api.new_version):
                    print("'bauh' requirement 'bauh_api' ({}) is not compatible with the version {}".format(gui_reqs['bauh_api'].rules, api.new_version))
                    return False
                elif not gui_reqs.get('bauh-commons'):
                    print("Could not retrieve 'bauh_commons' requirement version for 'bauh'")
                    return False
                elif not gui_reqs['bauh_commons'].accepts(commons.new_version):
                    print("'bauh' requirement 'bauh_commons' ({}) is not compatible with the version {}".format(gui_reqs['bauh_commons'].rules, commons.new_version))
                    return False

                return True

        return False

    def list_updates(self) -> List[Component]:
        components = self.list_components_git()
        res = []

        to_update = []
        if components:

            api = components[ComponentType.LIBRARY]['bauh-api']

            commons = components[ComponentType.LIBRARY]['bauh-commons']

            if not self._check_commons(commons, api):
                return []

            gui = components[ComponentType.APPLICATION]['bauh']

            if not self._check_gui(gui, api, commons):
                return []

            # Gems
            if components[ComponentType.GEM]:
                for gem in components[ComponentType.GEM].values():
                    reqs_text = self.github_client.get_requirements(gem.name, gem.new_version)

                    if not reqs_text:
                        print("Could not retrieve requirements file of '{}'. Skipping updates...".format(gem.name))
                        return []
                    else:
                        gem_reqs = requirements.full_parse(reqs_text)

                        if not gem_reqs.get('bauh_api'):
                            print("'bauh_api' is not declared in '{n}' requirements file. Skipping '{n}' updates...".format(n=gem.name))
                            continue
                        else:
                            if not gem_reqs['bauh_api'].accepts(api.new_version):
                                print("Cannot perform updates since '{}' requirement 'bauh_api' is not compatible with 'bauh_api' version {}. Aborting...".format(gem.name, api.new_version))
                                return []

                        gem_commons = gem_reqs.get('bauh_commons')

                        if gem_commons and not gem_commons.accepts(commons.new_version):
                            print("Cannot perform updates since '{}' requirement 'bauh_commons' is not compatible with 'bauh_commons' version {}. Aborting...".format(gem.name, commons.new_version))
                            return []

                        if gem.update:
                            to_update.append(gem)

        return res

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


# PythonComponentsManager().list_updates()
