import glob
import locale
from typing import Tuple

from bauh.view.util import resource


class I18n(dict):

    def __init__(self, current_locale: dict, default_locale: dict):
        super(I18n, self).__init__()
        self.current = current_locale
        self.default = default_locale

    def __getitem__(self, item):
        try:
            return self.current.__getitem__(item)
        except KeyError:
            if self.default:
                return self.default.__getitem__(item)
            else:
                raise

    def get(self, *args, **kwargs):
        res = self.current.get(args[0])

        if res is None:
            if self.default:
                return self.default.get(*args, **kwargs)
            else:
                return self.current.get(*args, **kwargs)

        return res


def get_locale_keys(key: str = None, locale_dir: str = resource.get_path('locale')) -> Tuple[str, dict]:

    locale_path = None

    if key is None:
        current_locale = locale.getdefaultlocale()
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
        return key, {}

    with open(locale_path, 'r') as f:
        locale_keys = f.readlines()

    locale_obj = {}
    for line in locale_keys:
        if line:
            keyval = line.strip().split('=')
            locale_obj[keyval[0].strip()] = keyval[1].strip()

    return locale_path.split('/')[-1], locale_obj
