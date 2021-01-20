import re
import traceback
from threading import Thread
from typing import Set, List, Tuple, Dict, Iterable

from packaging.version import parse as parse_version

from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman, message, sorting, confirmation
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

    def get_missing_packages(self, names: Set[str], repository: str = None, in_analysis: Set[str] = None) -> List[
        Tuple[str, str]]:
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

    def map_known_missing_deps(self, known_deps: Dict[str, str], watcher: ProcessWatcher, check_subdeps: bool = True) -> \
    List[Tuple[str, str]]:
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

    def _fill_missing_dep(self, dep_name: str, dep_exp: str, aur_index: Iterable[str],
                          missing_deps: Set[Tuple[str, str]],
                          remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                          repo_deps: Set[str], aur_deps: Set[str], deps_data: Dict[str, dict], watcher: ProcessWatcher,
                          automatch_providers: bool):

        if dep_name == dep_exp:
            providers = remote_provided_map.get(dep_name)

            if not providers:  # try to find the package through the pacman's search mechanism
                match = pacman.find_one_match(dep_name)

                if match:
                    providers = {match}

        else:  # handling cases when the dep has an expression ( e.g: xpto>=0.12 )
            providers = remote_provided_map.get(dep_exp)

            if providers is None:
                providers = remote_provided_map.get(dep_name)

                if not providers:  # try to find the package through the pacman's search mechanism
                    match = pacman.find_one_match(dep_name)

                    if match:
                        providers = {match}

                if providers and len(providers) > 1:
                    no_mapped_data = {p for p in providers if
                                      p not in deps_data}  # checking providers with no mapped data

                    if no_mapped_data:
                        providers_data = pacman.map_updates_data(no_mapped_data)

                        if not providers_data:
                            raise Exception("Could not retrieve the info from providers: {}".format(no_mapped_data))

                        deps_data.update(providers_data)  # adding missing providers data

                    matched_providers = set()
                    split_informed_dep = self.re_dep_operator.split(dep_exp)
                    try:
                        version_informed = parse_version(split_informed_dep[2])
                        exp_op = split_informed_dep[1] if split_informed_dep[1] != '=' else '=='

                        for p in providers:
                            provided = deps_data[p]['p']

                            for provided_exp in provided:
                                split_dep = self.re_dep_operator.split(provided_exp)

                                if len(split_dep) == 3 and split_dep[0] == dep_name:
                                    provided_version = parse_version(split_dep[2])

                                    if eval('provided_version {} version_informed'.format(exp_op)):
                                        matched_providers.add(p)
                                        break

                        providers = matched_providers
                    except:
                        traceback.print_exc()

        if providers:
            if len(providers) > 1:
                dep_data = None

                if automatch_providers:
                    exact_matches = [p for p in providers if p == dep_name]

                    if exact_matches:
                        dep_data = (exact_matches[0], remote_repo_map.get(exact_matches[0]))

                if not dep_data:
                    dep_data = (dep_name, '__several__')
            else:
                real_name = providers.pop()
                dep_data = (real_name, remote_repo_map.get(real_name))

            repo_deps.add(dep_data[0])
            missing_deps.add(dep_data)

        elif aur_index and dep_name in aur_index:
            aur_deps.add(dep_name)
            missing_deps.add((dep_name, 'aur'))
        else:
            if watcher:
                message.show_dep_not_found(dep_exp, self.i18n, watcher)
                raise PackageNotFoundException(dep_exp)
            else:
                raise PackageNotFoundException(dep_exp)

    def __fill_aur_update_data(self, pkgname: str, output: dict):
        output[pkgname] = self.aur_client.map_update_data(pkgname, None)

    def map_missing_deps(self, pkgs_data: Dict[str, dict], provided_map: Dict[str, Set[str]],
                         remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                         aur_index: Iterable[str], deps_checked: Set[str], deps_data: Dict[str, dict],
                         sort: bool, watcher: ProcessWatcher, choose_providers: bool = True,
                         automatch_providers: bool = False) -> List[Tuple[str, str]]:
        sorted_deps = []  # it will hold the proper order to install the missing dependencies

        missing_deps, repo_missing, aur_missing = set(), set(), set()

        deps_checked.update(pkgs_data.keys())

        for p, data in pkgs_data.items():
            if data['d']:
                for dep in data['d']:
                    if dep in pkgs_data:
                        continue
                    if dep not in provided_map:
                        dep_split = self.re_dep_operator.split(dep)
                        dep_name = dep_split[0].strip()

                        if dep_name not in deps_checked:
                            deps_checked.add(dep_name)

                            if dep_name not in provided_map:
                                self._fill_missing_dep(dep_name=dep_name, dep_exp=dep, aur_index=aur_index,
                                                       missing_deps=missing_deps,
                                                       remote_provided_map=remote_provided_map,
                                                       remote_repo_map=remote_repo_map,
                                                       repo_deps=repo_missing, aur_deps=aur_missing, watcher=watcher,
                                                       deps_data=deps_data,
                                                       automatch_providers=automatch_providers)
                            else:
                                version_pattern = '{}='.format(dep_name)
                                version_found = [p for p in provided_map if p.startswith(version_pattern)]

                                if version_found:
                                    version_found = version_found[0].split('=')[1]
                                    version_informed = dep_split[2].strip()

                                    if ':' not in version_informed:
                                        version_found = version_found.split(':')[-1]

                                    if '-' not in version_informed:
                                        version_found = version_found.split('-')[0]

                                    try:
                                        version_found = parse_version(version_found)
                                        version_informed = parse_version(version_informed)

                                        op = dep_split[1] if dep_split[1] != '=' else '=='
                                        match = eval('version_found {} version_informed'.format(op))
                                    except:
                                        match = False
                                        traceback.print_exc()

                                    if not match:
                                        self._fill_missing_dep(dep_name=dep_name, dep_exp=dep, aur_index=aur_index,
                                                               missing_deps=missing_deps,
                                                               remote_provided_map=remote_provided_map,
                                                               remote_repo_map=remote_repo_map,
                                                               repo_deps=repo_missing, aur_deps=aur_missing,
                                                               watcher=watcher,
                                                               deps_data=deps_data,
                                                               automatch_providers=automatch_providers)
                                else:
                                    self._fill_missing_dep(dep_name=dep_name, dep_exp=dep, aur_index=aur_index,
                                                           missing_deps=missing_deps,
                                                           remote_provided_map=remote_provided_map,
                                                           remote_repo_map=remote_repo_map,
                                                           repo_deps=repo_missing, aur_deps=aur_missing,
                                                           watcher=watcher,
                                                           deps_data=deps_data,
                                                           automatch_providers=automatch_providers)

        if missing_deps:
            if repo_missing:
                with_single_providers = []

                for d in missing_deps:
                    if d[0] in repo_missing and d[0] not in deps_data:
                        if d[1] == '__several__':
                            deps_data[d[0]] = {'d': None, 'p': d[0], 'r': d[1]}
                        else:
                            with_single_providers.append(d[0])

                if with_single_providers:
                    data = pacman.map_updates_data(with_single_providers)

                    if data:
                        deps_data.update(data)

            if aur_missing:
                aur_threads = []
                for pkgname in aur_missing:
                    t = Thread(target=self.__fill_aur_update_data, args=(pkgname, deps_data), daemon=True)
                    t.start()
                    aur_threads.append(t)

                for t in aur_threads:
                    t.join()

            missing_subdeps = self.map_missing_deps(pkgs_data=deps_data, provided_map=provided_map, aur_index=aur_index,
                                                    deps_checked=deps_checked, sort=False, deps_data=deps_data,
                                                    watcher=watcher,
                                                    remote_provided_map=remote_provided_map,
                                                    remote_repo_map=remote_repo_map,
                                                    automatch_providers=automatch_providers,
                                                    choose_providers=False)

            if missing_subdeps:
                missing_deps.update(missing_subdeps)

        if sort:
            sorted_deps.extend(sorting.sort(deps_data.keys(), deps_data))
        else:
            sorted_deps.extend(((dep[0], dep[1]) for dep in missing_deps))

        if sorted_deps and choose_providers:
            return self.fill_providers_deps(missing_deps=sorted_deps, provided_map=provided_map,
                                            remote_provided_map=remote_provided_map, remote_repo_map=remote_repo_map,
                                            watcher=watcher, sort=sort, already_checked=deps_checked,
                                            aur_idx=aur_index, deps_data=deps_data,
                                            automatch_providers=automatch_providers)

        return sorted_deps

    def fill_providers_deps(self, missing_deps: List[Tuple[str, str]],
                            provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                            already_checked: Set[str], remote_provided_map: Dict[str, Set[str]],
                            deps_data: Dict[str, dict], aur_idx: Iterable[str], sort: bool,
                            watcher: ProcessWatcher, automatch_providers: bool) -> List[Tuple[str, str]]:
        """
        :param missing_deps:
        :param provided_map:
        :param remote_repo_map:
        :param already_checked:
        :param remote_provided_map:
        :param deps_data:
        :param aur_idx:
        :param sort:
        :param watcher:
        :param automatch_providers
        :return: all deps sorted or None if the user declined the providers options
        """

        deps_providers = map_providers({data[0] for data in missing_deps if data[1] == '__several__'},
                                       remote_provided_map)

        if deps_providers:
            all_providers = set()

            for providers in deps_providers.values():
                all_providers.update(providers)

            providers_repos = pacman.map_repositories(all_providers)
            selected_providers = confirmation.request_providers(deps_providers, providers_repos, watcher, self.i18n)

            if not selected_providers:
                return
            else:
                providers_data = pacman.map_updates_data(
                    selected_providers)  # adding the chosen providers to re-check the missing deps
                provided_map.update(pacman.map_provided(remote=True,
                                                        pkgs=selected_providers))  # adding the providers as "installed" packages

                providers_deps = self.map_missing_deps(pkgs_data=providers_data,
                                                       provided_map=provided_map,
                                                       aur_index=aur_idx,
                                                       deps_checked=already_checked,
                                                       deps_data=deps_data,
                                                       sort=False,
                                                       remote_provided_map=remote_provided_map,
                                                       remote_repo_map=remote_repo_map,
                                                       watcher=watcher,
                                                       choose_providers=True,
                                                       automatch_providers=automatch_providers)

                # cleaning the already mapped providers deps:
                to_remove = []

                for idx, dep in enumerate(missing_deps):
                    if dep[1] == '__several__':
                        to_remove.append(idx)

                for idx, to_remove in enumerate(to_remove):
                    del missing_deps[to_remove - idx]

                missing_deps.extend(((p, providers_repos.get(p, 'aur')) for p in selected_providers))

                for dep in providers_deps:
                    if dep not in missing_deps and dep[1] != '__several__':
                        missing_deps.append(dep)

                deps_data.update(providers_data)

                if not self.fill_providers_deps(missing_deps=missing_deps, provided_map=provided_map,
                                                remote_repo_map=remote_repo_map, already_checked=already_checked,
                                                aur_idx=aur_idx, remote_provided_map=remote_provided_map,
                                                deps_data=deps_data, sort=False, watcher=watcher,
                                                automatch_providers=automatch_providers):
                    return

                if sort:
                    missing_to_sort = {d[0] for d in missing_deps if d[1] != '__several__'}
                    return sorting.sort(missing_to_sort, deps_data, provided_map)

        return missing_deps

    def map_all_required_by(self, pkgnames: Iterable[str], to_ignore: Set[str]) -> Set[str]:
        if pkgnames:
            to_ignore.update(pkgnames)

        all_requirements = {req for reqs in pacman.map_required_by(pkgnames).values() for req in reqs if req not in to_ignore}

        if all_requirements:
            sub_requirements = self.map_all_required_by(all_requirements, to_ignore)

            if sub_requirements:
                all_requirements.update(sub_requirements)
                return all_requirements

        return all_requirements


def map_providers(pkgs: Iterable[str], remote_provided_map: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    res = {}

    for p in pkgs:
        providers = remote_provided_map.get(p)

        if providers and len(providers) > 1:
            res[p] = providers

    return res
