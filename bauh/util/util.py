import locale

from bauh.core import resource
import glob
import re

HTML_RE = re.compile(r'<[^>]+>')


def get_locale_keys(key: str = None):

    locale_path = None

    if key is None:
        current_locale = locale.getdefaultlocale()
    else:
        current_locale = [key.strip().lower()]

    if current_locale:
        current_locale = current_locale[0]

        locale_dir = resource.get_path('locale')

        for locale_file in glob.glob(locale_dir + '/*'):
            name = locale_file.split('/')[-1]

            if current_locale == name or current_locale.startswith(name + '_'):
                locale_path = locale_file
                break

    if not locale_path:
        locale_path = resource.get_path('locale/en')

    with open(locale_path, 'r') as f:
        locale_keys = f.readlines()

    locale_obj = {}
    for line in locale_keys:
        if line:
            keyval = line.strip().split('=')
            locale_obj[keyval[0].strip()] = keyval[1].strip()

    return locale_obj


def strip_html(string: str):
    return HTML_RE.sub('', string)
