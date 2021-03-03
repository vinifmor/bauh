import re

RE_STRIP_EPIC = re.compile(r'^\d+:')
RE_STRIP_RELEASE = re.compile(r'-[\d\.?]+$')


def clean_version(version: str) -> str:
    treated_version = version.strip()
    if treated_version:
        return RE_STRIP_RELEASE.split(RE_STRIP_EPIC.split(treated_version)[-1])[0]

    return treated_version
