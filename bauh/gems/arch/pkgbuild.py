import re
from typing import Set

RE_PKGBUILD_OPTDEPS = re.compile(r"optdepends = (.+)")
RE_PKGBUILD_OPTDEPS_x86_64 = re.compile(r"optdepends_x86_64 = (.+)")
RE_PKGBUILD_OPTDEPS_i686 = re.compile(r"optdepends_i686 = (.+)")


def read_optdeps_as_dict(srcinfo: str, x86_64: bool) -> dict:
    res = {}
    for optdep in read_optdeps(srcinfo, x86_64):
        split_dep = optdep.split(':')
        res[split_dep[0].strip()] = split_dep[1].strip() if len(split_dep) > 1 else None

    return res


def read_optdeps(srcinfo: str, x86_64: bool) -> Set[str]:
    optdeps = set(RE_PKGBUILD_OPTDEPS.findall(srcinfo))

    if x86_64:
        optdeps.update(set(RE_PKGBUILD_OPTDEPS_x86_64.findall(srcinfo)))
    else:
        optdeps.update(set(RE_PKGBUILD_OPTDEPS_i686.findall(srcinfo)))

    return optdeps
