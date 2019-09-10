import logging
import sys
from typing import List, Dict

from bauh_api.abstract.component import ComponentsManager, Component, ComponentType
from bauh_commons.system import run_cmd, new_subprocess

from bauh.components import requirements
from bauh.components.github import GitHubClient

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

    def __init__(self, github_client: GitHubClient, logger: logging.Logger):
        self.github_client = github_client
        self.logger = logger

    def list_components(self) -> Dict[ComponentType, Dict[str, Component]]:
        python_comps = new_subprocess([PIP_PATH, 'list'], global_interpreter=False).stdout

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
                self.logger.warning('Could not retrieve the latest versions')

        return comps

    def _check_component(self, comp: Component, api: Component, commons: Component):
        reqs_text = self.github_client.get_requirements(comp.name, comp.new_version)

        if reqs_text:
            comp_reqs = requirements.full_parse(reqs_text)

            if not comp_reqs:
                self.logger.error("Could not retrieve '{}' requirements from 'requirements.txt'".format(comp.name))
            else:
                if not comp_reqs.get('bauh_api'):
                    self.logger.error("Could not retrieve 'bauh_api' requirement version for '{}'".format(comp.name))
                    return False
                elif not comp_reqs['bauh_api'].accepts(api.new_version):
                    self.logger.warning("'{}' requirement 'bauh_api' ({}) is not compatible with the version {}"
                                        .format(comp.name, comp_reqs['bauh_api'].rules, api.new_version))
                    return False

                if commons:
                    comp_commons = comp_reqs.get('bauh_commons')

                    if comp_commons and not comp_commons.accepts(commons.new_version):
                        self.logger.warning("'{}' requirement 'bauh_commons' ({}) is not compatible with the version {}"
                                            .format(comp.name, comp_reqs['bauh_commons'].rules, commons.new_version))
                        return False

                return True

        return False

    def list_updates(self) -> List[Component]:
        components = self.list_components()

        to_update = []
        if components:

            api = components[ComponentType.LIBRARY]['bauh_api']

            commons = components[ComponentType.LIBRARY]['bauh_commons']

            if not self._check_component(commons, api, None):
                return []

            gui = components[ComponentType.APPLICATION]['bauh']

            if not self._check_component(gui, api, commons):
                return []

            # Gems
            if components[ComponentType.GEM]:
                for gem in components[ComponentType.GEM].values():
                    if not self._check_component(gem, api, commons):
                        return []

            for c in [api, commons, gui, *components[ComponentType.GEM].values()]:
                if c.update:
                    to_update.append(c)

        return to_update

    def update(self, component: Component):
        pass

    def is_enabled(self) -> bool:
        return bool(run_cmd('pip --version', global_interpreter=False))

