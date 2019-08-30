import inspect
import os
import pkgutil
from typing import List, Dict

from bauh_api.abstract.controller import SoftwareManager, ApplicationContext
from bauh_api.util.cache import Cache

from bauh import __app_name__
from bauh.util import util

ignore_modules = {'{}_api'.format(__app_name__)}
ext_pattern = '{}_'.format(__app_name__)


def find_manager(member):
    if not isinstance(member, str):
        if inspect.isclass(member) and inspect.getmro(member)[1].__name__ == 'SoftwareManager':
            return member
        elif inspect.ismodule(member) and member.__name__ not in ignore_modules:
            for name, mod in inspect.getmembers(member):
                manager_found = find_manager(mod)
                if manager_found:
                    return manager_found


def load_managers(caches: List[Cache], cache_map: Dict[type, Cache], context: ApplicationContext) -> List[SoftwareManager]:
    managers = []

    for m in pkgutil.iter_modules():
        if m.ispkg and m.name and m.name not in ignore_modules and m.name.startswith(ext_pattern):
            module = pkgutil.find_loader(m.name).load_module()

            if hasattr(module, 'controller'):
                manager_class = find_manager(module.controller)

                if manager_class:
                    locale_path = '{}/resources/locale'.format(module.__path__[0])

                    if os.path.exists(locale_path):
                        context.i18n.update(util.get_locale_keys(context.args.locale, locale_path))

                    app_cache = Cache(expiration_time=context.args.cache_exp)
                    man = manager_class(context=context, app_cache=app_cache)

                    for t in man.get_managed_types():
                        cache_map[t] = app_cache

                    caches.append(app_cache)
                    managers.append(man)

    return managers
