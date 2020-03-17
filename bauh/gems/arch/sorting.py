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


def sort(pkgs: Iterable[str], pkgs_data: Dict[str, dict], provided_map: Dict[str, str] = None) -> List[Tuple[str, str]]:
    sorted_names, not_sorted = {}, set()

    provided = provided_map if provided_map else {}

    for pkgname in pkgs:
        data = pkgs_data[pkgname]
        if not provided_map and data['p']:
            for p in data['p']:
                provided[p] = pkgname

        if not data['d']:
            sorted_names[pkgname] = len(sorted_names)
        else:
            not_sorted.add(pkgname)

    # now adding all that depends on another:
    for name in not_sorted:
        __add_dep_to_sort(name, pkgs_data, sorted_names, not_sorted, provided)

    position_map = {'{}-{}'.format(i, n): (n, pkgs_data[n]['r']) for n, i in sorted_names.items()}
    return [position_map[idx] for idx in sorted(position_map)]
