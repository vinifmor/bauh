import re
from typing import Set

RE_PKGBUILD_OPTDEPS = re.compile(r"optdepends = (.+)")
RE_PKGBUILD_DEPSON = re.compile(r"\s+depends = (.+)")


def read_optdeps_as_dict(srcinfo: str) -> dict:
    res = {}
    for optdep in read_optdeps(srcinfo):
        split_dep = optdep.split(':')
        res[split_dep[0].strip()] = split_dep[1].strip() if len(split_dep) > 1 else None

    return res


def read_optdeps(srcinfo: str) -> Set[str]:
    return set(RE_PKGBUILD_OPTDEPS.findall(srcinfo))


def read_depends_on(srcinfo: str) -> Set[str]:
    return set(RE_PKGBUILD_DEPSON.findall(srcinfo))
