import sys
from typing import Dict, List

from bauh_api.abstract.component import ComponentsManager, Component, ComponentType
from bauh_api.abstract.context import ApplicationContext
from bauh_api.abstract.handler import ProcessWatcher
from bauh_commons.html import bold
from bauh_commons.system import run_cmd, new_subprocess, ProcessHandler, SystemProcess

from bauh.components import requirements
from bauh.components.github import GitHubClient

PIP_PATH = '/'.join(sys.executable.split('/')[0:-1]) + '/pip'


class PythonComponentsManager(ComponentsManager):

    def __init__(self, context: ApplicationContext, github_client: GitHubClient):
        super(PythonComponentsManager, self).__init__(context=context)
        self.github_client = github_client
        self.logger = context.logger
        self.i18n = context.i18n

    @staticmethod
    def map_type(name: str):
        if name == 'bauh':
            return ComponentType.APPLICATION
        elif name in {'bauh_api', 'bauh_commons'}:
            return ComponentType.LIBRARY
        else:
            return ComponentType.GEM

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
                    comp = Component(name=pkg, version=version, new_version=version, type=self.map_type(pkg), conflicts=[])

                    if pkg in latest:
                        comp.new_version = latest[pkg]

                    comps[comp.type][pkg] = comp
            else:
                self.logger.warning('Could not retrieve the latest versions')

        return comps

    def _add_conflicts(self, comp: Component, api: Component, commons: Component):
        reqs_text = self.github_client.get_requirements(comp.name, comp.new_version)

        if reqs_text:
            comp_reqs = requirements.full_parse(reqs_text)

            if not comp_reqs:
                self.logger.error("Could not retrieve '{}' requirements from 'requirements.txt'".format(comp.name))
            else:
                if not comp_reqs.get('bauh_api'):
                    self.logger.error("Could not retrieve 'bauh_api' requirement version for '{}'".format(comp.name))
                elif not comp_reqs['bauh_api'].accepts(api.new_version):
                    self.logger.warning("'{}' requirement 'bauh_api' ({}) is not compatible with the version {}"
                                        .format(comp.name, comp_reqs['bauh_api'].rules, api.new_version))
                    comp.conflicts.append(api)

                    if api.has_update():
                        api.conflicts.append(comp)

                if commons:
                    comp_commons = comp_reqs.get('bauh_commons')

                    if comp_commons and not comp_commons.accepts(commons.new_version):
                        self.logger.warning("'{}' requirement 'bauh_commons' ({}) is not compatible with the version {}"
                                            .format(comp.name, comp_reqs['bauh_commons'].rules, commons.new_version))
                        comp.conflicts.append(commons)

                        if commons.has_update():
                            commons.conflicts.append(comp)

    def list_updates(self) -> List[Component]:
        components = self.list_components()

        res = []

        if components:

            api = components[ComponentType.LIBRARY]['bauh_api']

            if api.has_update():
                res.append(api)

            commons = components[ComponentType.LIBRARY]['bauh_commons']

            self._add_conflicts(commons, api, None)

            if commons.has_update():
                res.append(commons)

            gui = components[ComponentType.APPLICATION]['bauh']

            self._add_conflicts(gui, api, commons)

            if gui.has_update():
                res.append(gui)

            # Gems
            if components[ComponentType.GEM]:
                for gem in components[ComponentType.GEM].values():
                    self._add_conflicts(gem, api, commons)

                    if gem.has_update():
                        res.append(gem)

        return res

    def _update(self, comp: Component, root_password: str, handler: ProcessHandler) -> bool:
        self.logger.info("Updating '{}' version from {} to {}".format(comp.name, comp.version, comp.new_version))

        info = '{} ({} -> {})'.format(bold(comp.name), comp.version, comp.new_version)
        handler.watcher.change_status(self.i18n['components.update.beginning'].format(info))

        # TODO at the moment 'root' is not necessary because the venv is created in the current user home
        proc = new_subprocess([PIP_PATH, 'install', '{}=={}'.format(comp.name, comp.new_version)], global_interpreter=False)
        res = handler.handle(SystemProcess(proc))

        if not res:
            handler.watcher.change_status(self.i18n['components.update.failed'].format(bold(comp.name)))
            self.logger.error("'{}' failed to updated to version {}".format(comp.name, comp.version))
        else:
            handler.watcher.change_status(self.i18n['components.update.success'].format(bold(comp.name)))
            self.logger.info("'{}' updated".format(comp.name))

        return res

    def requires_root(self):
        return False

    def update(self, components: List[Component], root_password: str, watcher: ProcessWatcher) -> bool:
        self.logger.info('Updating components')

        comps = {t: {} for t in ComponentType}

        handler = ProcessHandler(watcher)

        for c in components:
            comps[c.type][c.name] = c

        api = comps[ComponentType.LIBRARY].get('bauh_api')

        if api and not self._update(api, root_password, handler):
            return False

        commons = comps[ComponentType.LIBRARY].get('bauh_commons')

        if commons and not self._update(commons, root_password, handler):
            return False

        gui = comps[ComponentType.APPLICATION].get('bauh')

        if gui and not self._update(gui, root_password, handler):
            return False

        for gem in comps[ComponentType.GEM].values():
            if not self._update(gem, root_password, handler):
                return False

        return True

    def is_enabled(self) -> bool:
        return bool(run_cmd('pip --version', global_interpreter=False))
