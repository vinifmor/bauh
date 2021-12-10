import inspect
import os
import pkgutil
from logging import Logger
from typing import List, Generator

from bauh import __app_name__, ROOT_DIR
from bauh.api.abstract.controller import SoftwareManager, ApplicationContext
from bauh.view.util import translation

FORBIDDEN_GEMS_FILE = f'/etc/{__app_name__}/gems.forbidden'


def find_manager(member):
    if not isinstance(member, str):
        if inspect.isclass(member) and inspect.getmro(member)[1].__name__ == 'SoftwareManager':
            return member
        elif inspect.ismodule(member):
            for name, mod in inspect.getmembers(member):
                manager_found = find_manager(mod)
                if manager_found:
                    return manager_found


def read_forbidden_gems() -> Generator[str, None, None]:
    try:
        with open(FORBIDDEN_GEMS_FILE) as f:
            forbidden_lines = f.readlines()

        for line in forbidden_lines:
            clean_line = line.strip()

            if clean_line and not clean_line.startswith('#'):
                yield clean_line

    except FileNotFoundError:
        pass


def load_managers(locale: str, context: ApplicationContext, config: dict, default_locale: str, logger: Logger) -> List[SoftwareManager]:
    managers = []

    forbidden_gems = {gem for gem in read_forbidden_gems()}

    for f in os.scandir(f'{ROOT_DIR}/gems'):
        if f.is_dir() and f.name != '__pycache__':

            if f.name in forbidden_gems:
                logger.warning(f"gem '{f.name}' could not be loaded because it was marked as forbidden in '{FORBIDDEN_GEMS_FILE}'")
                continue

            loader = pkgutil.find_loader(f'bauh.gems.{f.name}.controller')

            if loader:
                module = loader.load_module()

                manager_class = find_manager(module)

                if manager_class:
                    if locale:
                        locale_path = f'{f.path}/resources/locale'

                        if os.path.exists(locale_path):
                            context.i18n.current.update(translation.get_locale_keys(locale, locale_path)[1])

                            if default_locale and context.i18n.default:
                                context.i18n.default.update(translation.get_locale_keys(default_locale, locale_path)[1])

                    man = manager_class(context=context)

                    if config['gems'] is None:
                        man.set_enabled(man.is_default_enabled())
                    else:
                        man.set_enabled(f.name in config['gems'])

                    managers.append(man)

    return managers
