import re
from typing import Set

RE_PKGBUILD_OPTDEPS = re.compile(r"optdepends = ([^:\s]+)")
RE_PKGBUILD_DEPSON = re.compile(r"depends = ([^:\s]+)")


def read_optdeps(srcinfo: str) -> Set[str]:
    return set(RE_PKGBUILD_OPTDEPS.findall(srcinfo))


def read_depends_on(srcinfo: str) -> Set[str]:
    return set(RE_PKGBUILD_DEPSON.findall(srcinfo))
