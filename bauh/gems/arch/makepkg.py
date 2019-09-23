import re

from bauh.commons.system import SimpleProcess, ProcessHandler

RE_DEPS_PATTERN = re.compile(r'\n?\s+->\s(.+)\n')
RE_UNKNOWN_GPG_KEY = re.compile(r'\(unknown public key (\w+)\)')


def check(pkgdir: str, handler: ProcessHandler) -> dict:
    res = {}
    success, output = handler.handle_simple(SimpleProcess(['makepkg', '-ALcf', '--check', '--noarchive', '--nobuild'], cwd=pkgdir))

    if 'Missing dependencies' in output:
        res['missing_deps'] = RE_DEPS_PATTERN.findall(output)

    gpg_keys = RE_UNKNOWN_GPG_KEY.findall(output)

    if gpg_keys:
        res['gpg_key'] = gpg_keys[0]

    return res
