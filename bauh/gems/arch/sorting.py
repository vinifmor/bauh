from typing import Dict, Set, Iterable, Tuple, List


def __add_dep_to_sort(pkgname: str, pkgs_data: Dict[str, dict], sorted_names: dict, not_sorted: Set[str],
                      provided_map: Dict[str, str]):
    idx = sorted_names.get(pkgname)

    if idx is not None:
        return idx
    else:
        idx = len(sorted_names)
        sorted_names[pkgname] = idx

        for dep in pkgs_data[pkgname]['d']:
            dep_idx = sorted_names.get(dep)

            if dep_idx is not None and dep_idx + 1 > idx:
                idx = dep_idx + 1
            else:
                real_dep = provided_map.get(dep)  # gets the real package name instead of the provided one

                if not real_dep or real_dep not in pkgs_data:
                    continue  # it means this depends does not belong to the sorting context
                else:
                    dep_idx = sorted_names.get(real_dep)

                    if dep_idx is not None and dep_idx + 1 > idx:
                        idx = dep_idx + 1
                    else:
                        dep_idx = __add_dep_to_sort(real_dep, pkgs_data, sorted_names, not_sorted, provided_map)
                        if dep_idx + 1 > idx:
                            idx = dep_idx + 1

        sorted_names[pkgname] = idx
        return idx


def sort(pkgs: Iterable[str], pkgs_data: Dict[str, dict], provided_map: Dict[str, Set[str]] = None) -> List[Tuple[str, str]]:
    sorted_list, sorted_names, not_sorted = [], set(), set()
    provided = provided_map if provided_map else {}

    # add all packages with no dependencies first
    for pkgname in pkgs:
        data = pkgs_data[pkgname]
        if not provided_map and data['p']:  # mapping provided if reeded
            for p in data['p']:
                provided[p] = {pkgname}

        if not data['d']:
            sorted_list.append(pkgname)
            sorted_names.add(pkgname)
        else:
            not_sorted.add(pkgname)

    deps_map, not_deps_available = {}, set()
    for pkg in not_sorted:  # generating a dependency map with only the dependencies among the informed packages
        pkgsdeps = set()
        data = pkgs_data[pkg]
        for dep in data['d']:
            providers = provided.get(dep)

            if providers:
                for p in providers:
                    if p in pkgs:
                        pkgsdeps.add(p)

        if pkgsdeps:
            deps_map[pkg] = pkgsdeps
        else:
            not_deps_available.add(pkg)
            sorted_list.append(pkg)
            sorted_names.add(pkg)

    for pkg in not_deps_available:  # removing from not_sorted
        not_sorted.remove(pkg)

    while not_sorted:
        sorted_in_round = set()

        for pkg in not_sorted:
            idx = _index_pkg(pkg, sorted_list, sorted_names, deps_map, ignore_not_sorted=False)

            if idx >= 0:
                sorted_in_round.add(pkg)
                sorted_names.add(pkg)
                sorted_list.insert(idx, pkg)

        for pkg in sorted_in_round:
            not_sorted.remove(pkg)

        if not_sorted and not sorted_in_round:  # it means there are cyclic deps
            break

    if not_sorted:  # it means there are cyclic deps
        # filtering deps already mapped
        for pkg in not_sorted:
            deps_map[pkg] = deps_map[pkg].difference(sorted_names)

        dep_lvl_map = {}  # holds the diff between the number of dependents per package and its dependencies
        for pkg in not_sorted:
            dependents = 0
            for pkg2 in not_sorted:
                if pkg != pkg2 and pkg in deps_map[pkg2]:
                    dependents += 1

            dep_lvl_map[pkg] = dependents - len(deps_map[pkg])

        sorted_by_less_deps = [*not_sorted]
        sorted_by_less_deps.sort(key=lambda o: dep_lvl_map[o], reverse=True)  # sorting by higher dep level

        for pkg in sorted_by_less_deps:
            idx = _index_pkg(pkg, sorted_list, sorted_names, deps_map, ignore_not_sorted=True)
            sorted_names.add(pkg)
            sorted_list.insert(idx, pkg)

    # putting arch pkgs in the end:
    aur_pkgs = None
    res = []

    for name in sorted_list:
        repo = pkgs_data[name]['r']
        if repo == 'aur':
            if not aur_pkgs:
                aur_pkgs = []

            aur_pkgs.append((name, 'aur'))
        else:
            res.append((name, repo))

    if aur_pkgs:
        res.extend(aur_pkgs)

    return res


def _index_pkg(name: str, sorted_list: List[str], sorted_names: Set[str], deps_map: Dict[str, Set[str]], ignore_not_sorted: bool) -> int:
    deps_to_check_idx = set()
    for dep in deps_map[name]:
        if dep in sorted_names:
            deps_to_check_idx.add(dep)
        elif not ignore_not_sorted:
            return -1

    if not deps_to_check_idx:
        return len(sorted_list)
    else:
        idxs = {sorted_list.index(dep) for dep in deps_to_check_idx}
        return max(idxs) + 1
