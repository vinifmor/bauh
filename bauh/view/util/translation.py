import glob
import locale
import os
from typing import Tuple, Set

from bauh.view.util import resource


class I18n(dict):

    def __init__(self, current_key: str, current_locale: dict, default_key: str, default_locale: dict):
        super(I18n, self).__init__()
        self.current_key = current_key
        self.current = current_locale
        self.default_key = default_key
        self.default = default_locale

    def __getitem__(self, item):
        try:
            return self.current.__getitem__(item)
        except KeyError:
            if self.default:
                try:
                    return self.default.__getitem__(item)
                except KeyError:
                    return item
            else:
                return item

    def get(self, *args, **kwargs):
        res = self.current.get(args[0])

        if res is None:
            if self.default:
                return self.default.get(*args, **kwargs)
            else:
                return self.current.get(*args, **kwargs)

        return res


def get_available_keys() -> Set[str]:
    locale_dir = resource.get_path('locale')
    return {file.split('/')[-1] for file in glob.glob(locale_dir + '/*') if os.path.isfile(file)}


def get_locale_keys(key: str = None, locale_dir: str = resource.get_path('locale')) -> Tuple[str, dict]:

    locale_path = None

    if key is None:
        try:
            current_locale = locale.getdefaultlocale()

            if current_locale is None or current_locale[0] is None:
                current_locale = ('en', 'UTF-8')
        except:
            current_locale = ('en', 'UTF-8')

    else:
        current_locale = [key.strip().lower()]

    if current_locale:
        current_locale = current_locale[0]

        for locale_file in glob.glob(locale_dir + '/*'):
            name = locale_file.split('/')[-1]

            if current_locale == name or current_locale.startswith(name + '_'):
                locale_path = locale_file
                break

    if not locale_path:
        return current_locale if current_locale else key, {}

    with open(locale_path, 'r') as f:
        locale_keys = f.readlines()

    locale_obj = {}
    for line in locale_keys:
        line_strip = line.strip()
        if line_strip:
            try:
                keyval = line_strip.split('=')
                locale_obj[keyval[0].strip()] = keyval[1].strip()
            except:
                print("Error decoding i18n line '{}'".format(line))

    return locale_path.split('/')[-1], locale_obj
