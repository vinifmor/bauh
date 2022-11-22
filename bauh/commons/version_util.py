import re
from typing import Tuple

RE_VERSION_WITH_EPOCH = re.compile(r'^\d+:(.+)$')
RE_VERSION_WITH_RELEASE = re.compile(r'^(.+)-\d+$')


def map_str_version(version: str) -> Tuple[str, ...]:
    return tuple(part.zfill(8) for part in version.split("."))


def normalize_version(version: str) -> Tuple[int, Tuple[str, ...], int]:
    raw_version = version.strip()

    epoch = 0

    if RE_VERSION_WITH_EPOCH.match(raw_version):
        epoch_version = raw_version.split(":", maxsplit=1)
        epoch = int(epoch_version[0])
        raw_version = epoch_version[1]

    release = 1
    if RE_VERSION_WITH_RELEASE.match(raw_version):
        version_release = raw_version.rsplit("-", maxsplit=1)
        raw_version = version_release[0]
        release = int(version_release[1])

    if not raw_version.split(".")[0].isdigit():
        # this is required to properly compare versions starting with a number against versions starting with alpha
        raw_version = f"0.{raw_version}"

    return epoch, map_str_version(raw_version), release


def match_required_version(current_version: str, operator: str, required_version: str) -> bool:
    final_required, final_current = required_version.strip(), current_version.strip()

    required_has_epoch = bool(RE_VERSION_WITH_EPOCH.match(final_required))
    current_no_epoch = RE_VERSION_WITH_EPOCH.split(final_current)
    current_has_epoch = len(current_no_epoch) > 1

    if required_has_epoch and not current_has_epoch:
        final_current = f'0:{final_current}'
    elif current_has_epoch and not required_has_epoch:
        final_current = current_no_epoch[1]

    required_has_release = bool(RE_VERSION_WITH_RELEASE.match(final_required))
    current_no_release = RE_VERSION_WITH_RELEASE.split(final_current)
    current_has_release = len(current_no_release) > 1

    if required_has_release and not current_has_release:
        final_current = f'{final_current}-1'
    elif current_has_release and not required_has_release:
        final_current = current_no_release[1]

    final_required, final_current = map_str_version(final_required), map_str_version(final_current)

    if operator == '==' or operator == '=':
        return final_current == final_required
    elif operator == '>':
        return final_current > final_required
    elif operator == '>=':
        return final_current >= final_required
    elif operator == '<':
        return final_current < final_required
    elif operator == '<=':
        return final_current <= final_required
