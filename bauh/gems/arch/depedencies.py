import re
from distutils.version import LooseVersion
from threading import Thread
from typing import Set, List, Tuple, Dict

from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman, message
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.exceptions import PackageNotFoundException
from bauh.view.util.translation import I18n


class DependenciesAnalyser:

    def __init__(self, aur_client: AURClient, i18n: I18n):
        self.aur_client = aur_client
        self.i18n = i18n
        self.re_dep_operator = re.compile(r'([<>=]+)')

    def _fill_repository(self, name: str, output: List[Tuple[str, str]]):

        repository = pacman.read_repository_from_info(name)

        if repository:
            output.append((name, repository))
            return

        guess = pacman.guess_repository(name)

        if guess:
            output.append(guess)
            return

        aur_info = self.aur_client.get_src_info(name)

        if aur_info:
            output.append((name, 'aur'))
            return

        output.append((name, ''))

    def get_missing_packages(self, names: Set[str], repository: str = None, in_analysis: Set[str] = None) -> List[Tuple[str, str]]:
        """
        :param names:
        :param repository:
        :param in_analysis: global set storing all names in analysis to avoid repeated recursion
        :return:
        """
        global_in_analysis = in_analysis if in_analysis else set()

        missing_names = pacman.check_missing({n for n in names if n not in in_analysis})

        if missing_names:
            missing_root = []
            threads = []

            if not repository:
                for name in missing_names:
                    t = Thread(target=self._fill_repository, args=(name, missing_root))
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

                threads.clear()

                # checking if there is any unknown dependency:
                for rdep in missing_root:
                    if not rdep[1]:
                        return missing_root
                    else:
                        global_in_analysis.add(rdep[0])
            else:
                for missing in missing_names:
                    missing_root.append((missing, repository))
                    global_in_analysis.add(missing)

            missing_sub = []
            for rdep in missing_root:
                subdeps = self.aur_client.get_required_dependencies(rdep[0]) if rdep[1] == 'aur' else pacman.read_dependencies(rdep[0])
                subdeps_not_analysis = {sd for sd in subdeps if sd not in global_in_analysis}

                if subdeps_not_analysis:
                    missing_subdeps = self.get_missing_packages(subdeps_not_analysis, in_analysis=global_in_analysis)

                    # checking if there is any unknown:
                    if missing_subdeps:
                        for subdep in missing_subdeps:
                            if not subdep[0]:
                                return [*missing_subdeps, *missing_root]

                            if subdep[0] not in missing_names:
                                missing_sub.append(subdep)
            return [*missing_sub, *missing_root]

    def get_missing_subdeps_of(self, names: Set[str], repository: str) -> List[Tuple[str, str]]:
        missing = []
        already_added = {*names}
        in_analyses = {*names}

        for name in names:
            subdeps = self.aur_client.get_required_dependencies(name) if repository == 'aur' else pacman.read_dependencies(name)

            if subdeps:
                missing_subdeps = self.get_missing_packages(subdeps, in_analysis=in_analyses)

                if missing_subdeps:
                    for subdep in missing_subdeps:  # checking if there is any unknown:
                        if subdep[0] not in already_added:
                            missing.append(subdep)

                        if not subdep[0]:
                            return missing
        return missing

    def get_missing_subdeps(self, name: str, repository: str, srcinfo: dict = None) -> List[Tuple[str, str]]:
        missing = []
        already_added = {name}
        in_analyses = {name}

        if repository == 'aur':
            subdeps = self.aur_client.get_required_dependencies(name) if not srcinfo else self.aur_client.extract_required_dependencies(srcinfo)
        else:
            subdeps = pacman.read_dependencies(name)

        if subdeps:
            missing_subdeps = self.get_missing_packages(subdeps, in_analysis=in_analyses)

            if missing_subdeps:
                for subdep in missing_subdeps:  # checking if there is any unknown:
                    if subdep[0] not in already_added:
                        missing.append(subdep)

                    if not subdep[0]:
                        return missing
        return missing

    def map_known_missing_deps(self, known_deps: Dict[str, str], watcher: ProcessWatcher, check_subdeps: bool = True) -> List[Tuple[str, str]]:
        sorted_deps = []  # it will hold the proper order to install the missing dependencies

        repo_deps, aur_deps = set(), set()

        for dep, repo in known_deps.items():
            if repo == 'aur':
                aur_deps.add(dep)
            else:
                repo_deps.add(dep)

        if check_subdeps:
            for deps in ((repo_deps, 'repo'), (aur_deps, 'aur')):
                if deps[0]:
                    missing_subdeps = self.get_missing_subdeps_of(deps[0], deps[1])

                    if missing_subdeps:
                        for dep in missing_subdeps:
                            if not dep[1]:
                                message.show_dep_not_found(dep[0], self.i18n, watcher)
                                return

                        for dep in missing_subdeps:
                            if dep not in sorted_deps:
                                sorted_deps.append(dep)

        for dep, repo in known_deps.items():
            if repo != 'aur':
                data = (dep, repo)
                if data not in sorted_deps:
                    sorted_deps.append(data)

        for dep in aur_deps:
            sorted_deps.append((dep, 'aur'))

        return sorted_deps

    def _map_missing_dep(self, name: str, pkgs_data: Dict[str, dict], provided_names: Dict[str, str], aur_index: Set[str], watcher: ProcessWatcher) -> Tuple[str, str]:
        dep_found = pacman.guess_repository(name)

        if dep_found:
            return dep_found[0], dep_found[1]

        elif aur_index and name in aur_index:
            return name, 'aur'
        else:
            if watcher:
                message.show_dep_not_found(name, self.i18n, watcher)
                raise PackageNotFoundException(name)
            else:
                raise PackageNotFoundException(name)

    def map_updates_missing_deps(self, pkgs_data: Dict[str, dict],  provided_names: Dict[str, str], aur_index: Set[str], check_subdeps: bool, watcher: ProcessWatcher) -> List[Tuple[str, str]]:
        sorted_deps = []  # it will hold the proper order to install the missing dependencies

        missing_deps = set()  # TODO find out the repositories for each dep added here
        deps_already_mapped = set()
        all_provided = provided_names.keys()

        for p, data in pkgs_data.items():
            if data['d']:
                for dep in data['d']:
                    if dep not in all_provided:
                        dep_split = self.re_dep_operator.split(dep)
                        dep_name = dep_split[0].strip()

                        if dep_name not in deps_already_mapped:
                            deps_already_mapped.add(dep_name)

                            if dep_name not in all_provided:
                                missing_deps.add(self._map_missing_dep(dep_name, pkgs_data, provided_names, aur_index, watcher))
                            else:
                                version_pattern = '{}='.format(dep_name)
                                version_found = [p for p in provided_names if p.startswith(version_pattern)]

                                if version_found:
                                    version_found = version_found[0].split('=')[1]
                                    version_informed = dep_split[2].strip()

                                    if ':' not in version_informed:
                                        version_found = version_found.split(':')[-1]

                                    if '-' not in version_informed:
                                        version_found = version_found.split('-')[0]

                                    version_found = LooseVersion(version_found)
                                    version_informed = LooseVersion(version_informed)

                                    op = dep_split[1] if dep_split[1] != '=' else '=='
                                    if not eval('version_found {} version_informed'.format(op)):
                                        print('Dep version not matched: {} ( installed: {} )'.format(dep, version_found.vstring))  # TODO remove
                                        missing_deps.add(self._map_missing_dep(dep_name, pkgs_data, provided_names, aur_index, watcher))  # TODO add version ?
                                else:
                                    missing_deps.add(self._map_missing_dep(dep_name, pkgs_data, provided_names, aur_index, watcher))

        if check_subdeps:  # TODO remove this 'check_subdeps' option ?
            # for deps in ((repo_deps, 'repo'), (aur_deps, 'aur')):
            #     if deps[0]:
            #         missing_subdeps = self.get_missing_subdeps_of(deps[0], deps[1])
            #
            #         if missing_subdeps:
            #             for dep in missing_subdeps:
            #                 if not dep[1]:
            #                     message.show_dep_not_found(dep[0], self.i18n, watcher)
            #                     return
            #
            #             for dep in missing_subdeps:
            #                 if dep not in sorted_deps:
            #                     sorted_deps.append(dep)
            pass

        # TODO sort deps
        sorted_deps.extend(missing_deps)

        return sorted_deps
