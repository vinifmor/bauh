import inspect
import os
import pkgutil
from argparse import Namespace
from typing import Set, List, Dict

from fpakman_api.util.cache import Cache

from fpakman import ROOT_DIR
from fpakman.util import util

ignore_modules = {'fpakman_api'}


def find_manager(member, ):
    if inspect.isclass(member) and inspect.getmro(member)[1].__name__ == 'ApplicationManager':
        return member
    elif inspect.ismodule(member) and member.__name__ not in ignore_modules:
        for name, mod in inspect.getmembers(member):
            manager_found = find_manager(mod)
            if manager_found:
                return manager_found


def load_managers(caches: List[Cache], cache_map: Dict[type, Cache], locale_keys: Dict[str, str], app_args: Namespace, http_session):
    managers = None

    for m in pkgutil.iter_modules():
        if m.ispkg and m.name and m.name not in ignore_modules and m.name.startswith('fpakman_'):
            module = pkgutil.find_loader(m.name).load_module()

            manager = find_manager(module)

            if manager:
                locale_path = '{}/resources/locale'.format(module.__path__[0])

                if os.path.exists(locale_path):
                    locale_keys.update(util.get_locale_keys(app_args.locale, locale_path))

                if not managers:
                    managers = []

                app_cache = Cache(expiration_time=app_args.cache_exp)
                man = manager(app_args=app_args,
                              fpakman_root_dir=ROOT_DIR,
                              http_session=http_session,
                              locale_keys=locale_keys,
                              app_cache=app_cache)
                cache_map[man.get_app_type()] = app_cache
                caches.append(app_cache)
                managers.append(man)

    return managers
