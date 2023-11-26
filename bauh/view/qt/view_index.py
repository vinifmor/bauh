from collections import defaultdict
from typing import Dict, List

from bauh.view.qt.view_model import PackageView


def new_character_idx() -> Dict[str, List[PackageView]]:
    return defaultdict(list)


def new_category_idx() -> Dict[str, Dict[str, List[PackageView]]]:
    return defaultdict(new_character_idx)


def new_type_index() -> Dict[str, Dict[str, Dict[str, List[PackageView]]]]:
    return defaultdict(new_category_idx)


def new_update_index() -> Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]:
    return defaultdict(new_type_index)


def new_app_index() -> Dict[int, Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]]:
    return defaultdict(new_update_index)


def new_package_index() -> Dict[int, Dict[int, Dict[int, Dict[str, Dict[str, Dict[str, List[PackageView]]]]]]]:
    return defaultdict(new_app_index)


def add_to_index(pkgv: PackageView, index: dict) -> None:
    # root keys: (1) installed | (0) not installed
    root_idx = index[1 if pkgv.model.installed else 0]

    # app keys: (1) app | (0) not app
    app_lvl = root_idx[1 if pkgv.model.is_application() else 0]

    # update keys: (1) update | (0) no update
    if pkgv.model.installed and not pkgv.model.is_update_ignored and pkgv.model.update:
        update_lvl = app_lvl[1]
    else:
        update_lvl = app_lvl[0]

    first_char = pkgv.name[0].lower()

    if pkgv.model.categories:
        for cat in ("any", *pkgv.model.categories):
            category = cat.lower().strip()

            # any type > specific category > any character
            update_lvl["any"][category]["any"].append(pkgv)

            # any type > specific category > first character
            update_lvl["any"][category][first_char].append(pkgv)

            type_lvl = update_lvl[pkgv.model.get_type()]

            # specific type > specific category > any character
            type_lvl[category]["any"].append(pkgv)

            # specific type > any category > first character
            type_lvl[category][first_char].append(pkgv)
