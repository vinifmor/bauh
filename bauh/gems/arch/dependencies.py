import re
import traceback
from logging import Logger
from threading import Thread
from typing import Set, List, Tuple, Dict, Iterable, Optional, Generator, Pattern

from bauh.api.abstract.handler import ProcessWatcher
from bauh.gems.arch import pacman, message, sorting, confirmation
from bauh.gems.arch.aur import AURClient
from bauh.gems.arch.exceptions import PackageNotFoundException
from bauh.gems.arch.version import match_required_version
from bauh.view.util.translation import I18n


class DependenciesAnalyser:

    _re_dep_operator: Optional[Pattern] = None

    def __init__(self, aur_client: AURClient, i18n: I18n, logger: Logger):
        self.aur_client = aur_client
        self.i18n = i18n
        self._log = logger

    @classmethod
    def re_dep_operator(cls) -> Pattern:
        if not cls._re_dep_operator:
            cls._re_dep_operator = re.compile(r'([<>=]+)')

        return cls._re_dep_operator

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

    def get_missing_packages(self, names: Set[str], repository: Optional[str] = None, in_analysis: Optional[Set[str]] = None) -> \
            List[Tuple[str, str]]:
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

    def map_known_missing_deps(self, known_deps: Dict[str, str], watcher: ProcessWatcher, check_subdeps: bool = True) -> Optional[List[Tuple[str, str]]]:
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
                                dependents = ', '.join(deps[0])  # it is not possible to know which is the exact dependent
                                message.show_dep_not_found(dep[0], self.i18n, watcher, dependent=dependents)
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

    def _find_repo_providers(self, dep_name: str, dep_exp: str, remote_provided_map: Dict[str, Set[str]],
                             deps_data: Dict[str, dict], remote_repo_map: Dict[str, str]) -> Generator[Tuple[str, str, Optional[dict]], None, None]:
        if dep_name == dep_exp:
            providers = remote_provided_map.get(dep_name)

            if providers:
                for pkgname in providers:
                    yield pkgname, remote_repo_map.get(pkgname), None

            else:  # try to find the package through the pacman's search mechanism
                match = pacman.find_one_match(dep_name)

                if match:
                    yield match, remote_repo_map.get(match), None

        else:  # handling cases when the dep has an expression ( e.g: xpto>=0.12 )
            exact_exp_providers = remote_provided_map.get(dep_exp)

            if exact_exp_providers:
                for p in exact_exp_providers:
                    yield p, remote_repo_map.get(p), None
            else:
                providers = remote_provided_map.get(dep_name)

                if not providers:  # try to find the package through the pacman's search mechanism
                    match = pacman.find_one_match(dep_name)

                    if match:
                        providers = {match}

                if providers:
                    providers_no_provided_data = {p for p in providers if p not in deps_data}
                    missing_providers_data = None

                    if providers_no_provided_data:
                        missing_providers_data = pacman.map_updates_data(providers_no_provided_data)

                        if not missing_providers_data:
                            raise Exception(f"Could not retrieve information from providers: "
                                            f"{', '.join(providers_no_provided_data)}")

                        data_not_found = {p for p in providers if p not in missing_providers_data}

                        if data_not_found:
                            raise Exception(f"Could not retrieve information from providers: "
                                            f"{', '.join(data_not_found)}")

                    split_informed_dep = self.re_dep_operator().split(dep_exp)

                    version_required = split_informed_dep[2]
                    exp_op = split_informed_dep[1] if split_informed_dep[1] != '=' else '=='

                    for p in providers:
                        info = deps_data.get(p)

                        if not info and missing_providers_data:
                            info = missing_providers_data[p]

                        for provided_exp in info['p']:
                            split_dep = self.re_dep_operator().split(provided_exp)

                            if len(split_dep) == 3 and split_dep[0] == dep_name:
                                version_provided = split_dep[2]

                                if match_required_version(version_provided, exp_op, version_required):
                                    yield p, remote_repo_map.get(p), info
                                    break

    def _find_aur_providers(self, dep_name: str, dep_exp: str, aur_index: Iterable[str], exact_match: bool) -> Generator[Tuple[str, dict], None, None]:
        if exact_match and dep_name in aur_index:
            if dep_name == dep_exp:
                yield from self.aur_client.gen_updates_data((dep_name,))
                return
            else:
                for _, dep_data in self.aur_client.gen_updates_data((dep_name,)):
                    split_informed_dep = self.re_dep_operator().split(dep_exp)
                    version_required = split_informed_dep[2]
                    exp_op = split_informed_dep[1].strip()

                    if match_required_version(dep_data['v'], exp_op, version_required):
                        yield dep_name, dep_data
                        return

        aur_search = self.aur_client.search(dep_name)

        if aur_search:
            aur_results = aur_search.get('results')

            if aur_results:
                if dep_name == dep_exp:
                    version_required, exp_op = None, None
                else:
                    split_informed_dep = self.re_dep_operator().split(dep_exp)
                    version_required = split_informed_dep[2]
                    exp_op = split_informed_dep[1] if split_informed_dep[1] != '=' else '=='

                for pkgname, pkgdata in self.aur_client.gen_updates_data((aur_res['Name'] for aur_res in aur_results)):
                    if pkgname == dep_name or (dep_name in pkgdata['p']):
                        try:
                            if not version_required or match_required_version(pkgdata['v'], exp_op,
                                                                              version_required):
                                yield pkgname, pkgdata
                        except:
                            self._log.warning(f"Could not compare AUR package '{pkgname}' version '{pkgdata['v']}' "
                                              f"with the dependency expression '{dep_exp}'")
                            traceback.print_exc()

    def _fill_missing_dep(self, dep_name: str, dep_exp: str, aur_index: Iterable[str],
                          missing_deps: Set[Tuple[str, str]],
                          remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                          repo_deps: Set[str], aur_deps: Set[str], deps_data: Dict[str, dict], watcher: ProcessWatcher,
                          automatch_providers: bool, prefer_repository_provider: bool, dependent: Optional[str] = None):

        repo_matches = None

        for pkgname, repo, data in self._find_repo_providers(dep_name=dep_name, dep_exp=dep_exp,
                                                             remote_repo_map=remote_repo_map,
                                                             remote_provided_map=remote_provided_map,
                                                             deps_data=deps_data):
            if automatch_providers and pkgname == dep_name:
                missing_deps.add((pkgname, repo))
                repo_deps.add(pkgname)

                if data:
                    deps_data[pkgname] = data

                return

            if repo_matches is None:
                repo_matches = []

            repo_matches.append((pkgname, repo, data))

        if prefer_repository_provider and repo_matches and len(repo_matches) == 1:
            pkg_name, pkg_repo, pkg_data = repo_matches[0]
            missing_deps.add((pkg_name, pkg_repo))
            repo_deps.add(pkg_name)

            if pkg_data:
                deps_data[pkg_name] = pkg_data

            return

        aur_matches = None

        if aur_index:
            for pkgname, pkgdata in self._find_aur_providers(dep_name=dep_name, dep_exp=dep_exp, aur_index=aur_index,
                                                             exact_match=automatch_providers):
                if automatch_providers and pkgname == dep_name:
                    missing_deps.add((pkgname, 'aur'))
                    aur_deps.add(pkgname)
                    deps_data[pkgname] = pkgdata
                    return

                if aur_matches is None:
                    aur_matches = []

                aur_matches.append((pkgname, pkgdata))

        total_matches = (len(repo_matches) if repo_matches else 0) + (len(aur_matches) if aur_matches else 0)

        if total_matches == 0:
            self.__raise_dependency_not_found(dep_exp, watcher, dependent)
        elif total_matches == 1:
            if repo_matches:
                repo_pkg = [*repo_matches][0]

                if repo_pkg[2]:
                    deps_data[repo_pkg[0]] = repo_pkg[2]  # already updating the deps data (if available)

                match = (repo_pkg[0], repo_pkg[1])
                repo_deps.add(repo_pkg[0])
            else:
                aur_pkg = aur_matches[0]
                deps_data[aur_pkg[0]] = aur_pkg[1]  # already updating the deps data (if available)
                aur_deps.add(aur_pkg[0])
                match = aur_pkg[0], 'aur'

            missing_deps.add(match)

        elif total_matches > 1:
            missing_deps.add((dep_name, '__several__'))

            if repo_matches:
                repo_deps.add(dep_name)

            if aur_matches:
                aur_deps.add(dep_name)

                for pkgname, _ in aur_matches:
                    for key in (dep_name, dep_exp):
                        key_provided = remote_provided_map.get(key, set())
                        remote_provided_map[key] = key_provided
                        key_provided.add(pkgname)

                    if pkgname not in remote_repo_map:
                        remote_repo_map[pkgname] = 'aur'

    def __raise_dependency_not_found(self, dep_exp: str, watcher: Optional[ProcessWatcher], dependent: Optional[str] = None):
        if watcher:
            message.show_dep_not_found(depname=dep_exp, i18n=self.i18n, watcher=watcher, dependent=dependent)
            raise PackageNotFoundException(dep_exp)
        else:
            raise PackageNotFoundException(dep_exp)

    def _fill_aur_updates_data(self, pkgnames: Iterable[str], output_data: dict):
        if pkgnames:
            for pkgname, pkgdata in self.aur_client.gen_updates_data(pkgnames):
                output_data[pkgname] = pkgdata

    def map_missing_deps(self, pkgs_data: Dict[str, dict], provided_map: Dict[str, Set[str]],
                         remote_provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                         aur_index: Iterable[str], deps_checked: Set[str], deps_data: Dict[str, dict],
                         sort: bool, watcher: ProcessWatcher, choose_providers: bool = True,
                         automatch_providers: bool = False, prefer_repository_provider: bool = False) -> Optional[List[Tuple[str, str]]]:
        sorted_deps = []  # it will hold the proper order to install the missing dependencies

        missing_deps, repo_missing, aur_missing = set(), set(), set()

        deps_checked.update(pkgs_data.keys())

        for p, data in pkgs_data.items():
            if data['d']:
                for dep in data['d']:
                    if dep in pkgs_data:
                        continue
                    if dep not in provided_map:
                        dep_split = self.re_dep_operator().split(dep)
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
                                                       automatch_providers=automatch_providers,
                                                       prefer_repository_provider=prefer_repository_provider,
                                                       dependent=p)
                            else:
                                version_pattern = '{}='.format(dep_name)
                                version_found = [p for p in provided_map if p.startswith(version_pattern)]

                                if version_found:
                                    version_found = version_found[0].split('=')[1]
                                    version_required = dep_split[2]
                                    op = dep_split[1].strip()

                                    if not match_required_version(version_found, op, version_required):
                                        self._fill_missing_dep(dep_name=dep_name, dep_exp=dep, aur_index=aur_index,
                                                               missing_deps=missing_deps,
                                                               remote_provided_map=remote_provided_map,
                                                               remote_repo_map=remote_repo_map,
                                                               repo_deps=repo_missing, aur_deps=aur_missing,
                                                               watcher=watcher,
                                                               deps_data=deps_data,
                                                               automatch_providers=automatch_providers,
                                                               prefer_repository_provider=prefer_repository_provider,
                                                               dependent=p)
                                else:
                                    self._fill_missing_dep(dep_name=dep_name, dep_exp=dep, aur_index=aur_index,
                                                           missing_deps=missing_deps,
                                                           remote_provided_map=remote_provided_map,
                                                           remote_repo_map=remote_repo_map,
                                                           repo_deps=repo_missing, aur_deps=aur_missing,
                                                           watcher=watcher,
                                                           deps_data=deps_data,
                                                           automatch_providers=automatch_providers,
                                                           prefer_repository_provider=prefer_repository_provider,
                                                           dependent=p)

        if missing_deps:
            self._fill_single_providers_data(missing_deps, repo_missing, aur_missing, deps_data)

            missing_subdeps = self.map_missing_deps(pkgs_data={**deps_data}, provided_map=provided_map, aur_index=aur_index,
                                                    deps_checked=deps_checked, sort=False, deps_data=deps_data,
                                                    watcher=watcher,
                                                    remote_provided_map=remote_provided_map,
                                                    remote_repo_map=remote_repo_map,
                                                    automatch_providers=automatch_providers,
                                                    choose_providers=False,
                                                    prefer_repository_provider=prefer_repository_provider)

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
                                            automatch_providers=automatch_providers,
                                            prefer_repository_provider=prefer_repository_provider)

        return sorted_deps

    def _fill_single_providers_data(self, all_missing_deps: Iterable[Tuple[str, str]], repo_missing_deps: Iterable[str], aur_missing_deps: Iterable[str], deps_data: Dict[str, dict]):
        """
            fills the missing data of the single dependency providers since they are already considered dependencies
            (when several providers are available for given a dependency, the user must choose first)
        """
        repo_providers_no_data, aur_providers_no_data = None, None

        for dep_name, dep_repo in all_missing_deps:
            if dep_repo == '__several__':
                deps_data[dep_name] = {'d': None, 'p': {dep_name}, 'r': dep_repo}
            elif dep_name not in deps_data:
                if repo_missing_deps and dep_name in repo_missing_deps:
                    if repo_providers_no_data is None:
                        repo_providers_no_data = set()

                    repo_providers_no_data.add(dep_name)
                elif aur_missing_deps and dep_name in aur_missing_deps:
                    if aur_providers_no_data is None:
                        aur_providers_no_data = set()

                    aur_providers_no_data.add(dep_name)

        aur_data_filler, aur_providers_data = None, None

        if aur_providers_no_data:
            aur_providers_data = dict()
            aur_data_filler = Thread(target=self._fill_aur_updates_data,
                                     args=(aur_providers_no_data, aur_providers_data))
            aur_data_filler.start()

        if repo_providers_no_data:
            repo_providers_data = pacman.map_updates_data(repo_providers_no_data)

            if repo_providers_data:
                deps_data.update(repo_providers_data)

        if aur_data_filler:
            aur_data_filler.join()

            if aur_providers_data:
                deps_data.update(aur_providers_data)

    def fill_providers_deps(self, missing_deps: List[Tuple[str, str]],
                            provided_map: Dict[str, Set[str]], remote_repo_map: Dict[str, str],
                            already_checked: Set[str], remote_provided_map: Dict[str, Set[str]],
                            deps_data: Dict[str, dict], aur_idx: Iterable[str], sort: bool,
                            watcher: ProcessWatcher, automatch_providers: bool,
                            prefer_repository_provider: bool) -> Optional[List[Tuple[str, str]]]:
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
        :param prefer_repository_provider
        :return: all deps sorted or None if the user declined the providers options
        """

        deps_providers = map_providers({data[0] for data in missing_deps if data[1] == '__several__'},
                                       remote_provided_map)

        if deps_providers:
            providers_repos = {}
            repos_providers = set()

            for providers in deps_providers.values():
                for provider in providers:
                    if remote_repo_map.get(provider) == 'aur':
                        providers_repos[provider] = 'aur'
                    else:
                        repos_providers.add(provider)

            providers_repos.update(pacman.map_repositories(repos_providers))
            selected_providers = confirmation.request_providers(deps_providers, providers_repos, watcher, self.i18n)

            if not selected_providers:
                return
            else:
                # adding the chosen providers for re-checking the missing dependencies
                repo_selected, aur_selected = set(), set()

                for provider in selected_providers:
                    if provider in repos_providers:
                        repo_selected.add(provider)
                    else:
                        aur_selected.add(provider)

                providers_data = dict()

                if repo_selected:
                    providers_data.update(pacman.map_updates_data(repo_selected))
                    # adding the providers as "installed" packages
                    provided_map.update(pacman.map_provided(remote=True,  pkgs=repo_selected))

                if aur_selected:
                    for pkgname, pkgdata in self.aur_client.gen_updates_data(aur_selected):
                        providers_data[pkgname] = pkgdata
                        for provider in pkgdata['p']:  # adding the providers as "installed" packages
                            currently_provided = provided_map.get(provider, set())
                            provided_map[provider] = currently_provided
                            currently_provided.add(pkgname)

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
                                                       automatch_providers=automatch_providers,
                                                       prefer_repository_provider=prefer_repository_provider)

                if providers_deps is None:  # it means the user called off the installation process
                    return

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
                                                automatch_providers=automatch_providers,
                                                prefer_repository_provider=prefer_repository_provider):
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
