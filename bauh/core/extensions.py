import inspect
import os
import pkgutil
from argparse import Namespace
from typing import List, Dict

from bauh_api.abstract.controller import ApplicationManager
from bauh_api.util.cache import Cache
from bauh_api.util.http import HttpClient

from bauh import ROOT_DIR, __app_name__
from bauh.util import util

ignore_modules = {'{}_api'.format(__app_name__)}
ext_pattern = '{}_'.format(__app_name__)


def find_manager(member):
    if not isinstance(member, str):
        if inspect.isclass(member) and inspect.getmro(member)[1].__name__ == 'ApplicationManager':
            return member
        elif inspect.ismodule(member) and member.__name__ not in ignore_modules:
            for name, mod in inspect.getmembers(member):
                manager_found = find_manager(mod)
                if manager_found:
                    return manager_found


def load_managers(caches: List[Cache], cache_map: Dict[type, Cache], locale_keys: Dict[str, str], app_args: Namespace, http_client: HttpClient) -> List[ApplicationManager]:
    managers = []

    for m in pkgutil.iter_modules():
        if m.ispkg and m.name and m.name not in ignore_modules and m.name.startswith(ext_pattern):
            module = pkgutil.find_loader(m.name).load_module()

            if hasattr(module, 'controller'):
                manager_class = find_manager(module.controller)

                if manager_class:
                    locale_path = '{}/resources/locale'.format(module.__path__[0])

                    if os.path.exists(locale_path):
                        locale_keys.update(util.get_locale_keys(app_args.locale, locale_path))

                    app_cache = Cache(expiration_time=app_args.cache_exp)
                    man = manager_class(app_args=app_args,
                                        app_root_dir=ROOT_DIR,
                                        http_client=http_client,
                                        locale_keys=locale_keys,
                                        app_cache=app_cache)

                    for t in man.get_managed_types():
                        cache_map[t] = app_cache

                    caches.append(app_cache)
                    managers.append(man)

    return managers
