from typing import Iterable, List

from bauh.api.abstract.model import SoftwarePackage
from bauh.view.qt.view_model import PackageView


def new_pkgs_info() -> dict:
    return {'apps_count': 0,  # number of application packages
            'napps_count': 0,  # number of not application packages (libraries, runtimes or something else)
            'available_types': {},  # available package types in 'new_pkgs'
            'updates': 0,
            'app_updates': 0,
            'napp_updates': 0,
            'pkgs_displayed': [],
            'not_installed': 0,
            'installed': 0,
            'categories': set(),
            'pkgs': []}  # total packages


def update_info(pkgv: PackageView, pkgs_info: dict):
    pkgs_info['available_types'][pkgv.model.get_type()] = {'icon': pkgv.model.get_type_icon_path(), 'label': pkgv.get_type_label()}

    if pkgv.model.is_application():
        pkgs_info['apps_count'] += 1
    else:
        pkgs_info['napps_count'] += 1

    if pkgv.model.update and not pkgv.model.is_update_ignored():
        if pkgv.model.is_application():
            pkgs_info['app_updates'] += 1
        else:
            pkgs_info['napp_updates'] += 1

        pkgs_info['updates'] += 1

    if pkgv.model.categories:
        for c in pkgv.model.categories:
            if c:
                cat = c.lower().strip()
                if cat:
                    pkgs_info['categories'].add(cat)

    pkgs_info['pkgs'].append(pkgv)

    if pkgv.model.installed:
        pkgs_info['installed'] += 1
    else:
        pkgs_info['not_installed'] += 1


def apply_filters(pkg: PackageView, filters: dict, info: dict, limit: bool = True):
    if not limit or not filters['display_limit'] or len(info['pkgs_displayed']) < filters['display_limit']:
        if not is_package_hidden(pkg, filters):
            info['pkgs_displayed'].append(pkg)


def sum_updates_displayed(info: dict) -> int:
    updates = 0
    if info['pkgs_displayed']:
        for p in info['pkgs_displayed']:
            if p.model.update and not p.model.is_update_ignored():
                updates += 1

    return updates


def is_package_hidden(pkg: PackageView, filters: dict) -> bool:
    hidden = filters['only_installed'] and not pkg.model.installed

    if not hidden and filters['only_apps']:
        hidden = pkg.model.installed and not pkg.model.is_application()

    if not hidden and filters['updates']:
        hidden = not pkg.model.update or pkg.model.is_update_ignored()

    if not hidden and filters['type'] is not None and filters['type'] != 'any':
        hidden = pkg.model.get_type() != filters['type']

    if not hidden and filters['category'] is not None and filters['category'] != 'any':
        hidden = not pkg.model.categories or not [c for c in pkg.model.categories if c.lower() == filters['category']]

    if not hidden and filters['name']:
        hidden = not filters['name'] in pkg.model.name.lower()

    return hidden


def sort_packages(pkgs: Iterable[SoftwarePackage], word: str, limit: int = 0) -> List[SoftwarePackage]:
    exact, starts_with, contains, others = [], [], [], []

    for p in pkgs:
        lower_name = p.name.lower()

        if word == lower_name:
            exact.append(p)
        elif lower_name.startswith(word):
            starts_with.append(p)
        elif word in lower_name:
            contains.append(p)
        else:
            others.append(p)

    res = []
    for app_list in (exact, starts_with, contains, others):
        if app_list:
            last = limit - len(res) if limit is not None and limit > 0 else None

            if last is not None and last <= 0:
                break

            to_add = app_list[0:last]
            to_add.sort(key=lambda a: a.name.lower())
            res.extend(to_add)

    return res
