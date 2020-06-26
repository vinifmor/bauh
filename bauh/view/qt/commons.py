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
    pkgs_info['not_installed'] += 1 if not pkgv.model.installed else 0


def apply_filters(pkg: PackageView, filters: dict, info: dict, limit: bool = True):
    if not limit or not filters['display_limit'] or len(info['pkgs_displayed']) < filters['display_limit']:
        if not is_package_hidden(pkg, filters):
            info['pkgs_displayed'].append(pkg)


def is_package_hidden(pkg: PackageView, filters: dict) -> bool:
    hidden = filters['only_apps'] and pkg.model.installed and not pkg.model.is_application()

    if not hidden and filters['updates']:
        hidden = not pkg.model.update or pkg.model.is_update_ignored()

    if not hidden and filters['type'] is not None and filters['type'] != 'any':
        hidden = pkg.model.get_type() != filters['type']

    if not hidden and filters['category'] is not None and filters['category'] != 'any':
        hidden = not pkg.model.categories or not [c for c in pkg.model.categories if c.lower() == filters['category']]

    if not hidden and filters['name']:
        hidden = not filters['name'] in pkg.model.name.lower()

    return hidden
