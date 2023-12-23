from collections import defaultdict
from typing import Dict, List, Generator, Tuple, Optional, Union

from bauh.view.qt.commons import PackageFilters
from bauh.view.qt.view_model import PackageView


def new_character_idx() -> Dict[str, List[PackageView]]:
    return defaultdict(list)


def new_category_idx() -> Dict[str, Dict[str, List[PackageView]]]:
    return defaultdict(new_character_idx)


def new_type_index() -> Dict[str, Dict[str, Dict[str, List[PackageView]]]]:
    return defaultdict(new_category_idx)


def new_verified_index() -> Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]:
    return defaultdict(new_type_index)


def new_update_index() -> Dict[int, Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]]:
    return defaultdict(new_verified_index)


def new_app_index() -> Dict[int, Dict[int, Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]]]:
    return defaultdict(new_update_index)


def new_package_index() -> Dict[int, Dict[int, Dict[int, Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]]]]:
    return defaultdict(new_app_index)


def add_to_index(pkgv: PackageView, index: dict) -> None:
    # root keys: (1) installed | (0) not installed
    root_idx = index[1 if pkgv.model.installed else 0]

    # app keys: (1) app | (0) not app
    app_lvl = root_idx[1 if pkgv.model.is_application() else 0]

    # update keys: (1) update | (0) no update
    if pkgv.model.installed and pkgv.model.update and not pkgv.model.is_update_ignored():
        update_lvl = app_lvl[1]
    else:
        update_lvl = app_lvl[0]

    # verified keys: (1) verified | (0) unverified
    verified_lvl = update_lvl[1 if pkgv.model.is_trustable() else 0]

    norm_name = pkgv.name.strip().lower()
    starts_with_chars = tuple(norm_name[0:i] for i in range(1, len(norm_name) + 1))

    for cat in ("any", *(pkgv.model.categories if pkgv.model.categories else tuple())):
        category = cat.lower().strip()

        # any type > specific category > any character (None)
        verified_lvl["any"][category][None].append(pkgv)

        # any type > specific category > characters (start
        for chars in starts_with_chars:
            verified_lvl["any"][category][chars].append(pkgv)

        type_lvl = verified_lvl[pkgv.model.get_type()]

        # specific type > specific category > any character (None)
        type_lvl[category][None].append(pkgv)

        # specific type > any category > first character
        for chars in starts_with_chars:
            type_lvl[category][chars].append(pkgv)


def generate_queries(filters: PackageFilters) -> Generator[Tuple[Optional[Union[int, str]], ...], None, None]:
    chars_query = None

    if filters.name:
        chars_query = filters.name.lower()

    installed_queries = (1,) if filters.only_installed else (1, 0)
    apps_queries = (1,) if filters.only_apps else (1, 0)
    updates_queries = (1,) if filters.only_updates else (1, 0)
    verified_queries = (1,) if filters.only_verified else (1, 0)

    for installed in installed_queries:
        for app in apps_queries:
            for update in updates_queries:
                for verified in verified_queries:
                    yield installed, app, update, verified, filters.type, filters.category, chars_query


def query_packages(index: dict, filters: PackageFilters) -> Generator[PackageView, None, None]:
    yield_count = 0
    yield_limit = filters.display_limit if filters.display_limit and filters.display_limit > 0 else -1

    queries = tuple(generate_queries(filters))

    yielded_pkgs = defaultdict(set)

    for query in queries:
        packages = index[query[0]][query[1]][query[2]][query[3]][query[4]][query[5]][query[6]]

        for pkgv in packages:
            yield pkgv
            yield_count += 1
            yielded_pkgs[pkgv.model.get_type()].add(pkgv.model.id)

            # checking if the package display limit has been reached
            if 0 < yield_limit <= yield_count:
                break

    # if there is a limit and the number of yielded packages is not reached, performs also a "contains" query
    # checking if the queries target "any character" (none), if so, there is no need to perform the "contains" query
    any_char_query = next((True for q in queries if q[-1] is None), False)

    if not any_char_query and 0 < yield_limit > yield_count:
        for query in queries:
            # checking if the package display limit has been reached
            if 0 < yield_limit <= yield_count:
                break

            packages = index[query[0]][query[1]][query[2]][query[3]][query[4]][query[5]][None]

            for pkgv in packages:
                # checking if the package has already been yielded
                yield_type_idx = yielded_pkgs.get(pkgv.model.get_type())
                if yield_type_idx and pkgv.model.id in yield_type_idx:
                    continue

                # checking if the package name contains the chars query
                if query[5] in pkgv.model.name:
                    yield pkgv
                    yield_count += 1
                    yielded_pkgs[pkgv.model.get_type()].add(pkgv.model.id)

                # checking if the package display limit has been reached
                if 0 < yield_limit <= yield_count:
                    break
