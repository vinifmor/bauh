import re

from packaging.version import LegacyVersion

RE_VERSION_WITH_RELEASE = re.compile(r'^(.+)-\d+$')
RE_VERSION_WITH_EPOCH = re.compile(r'^\d+:(.+)$')


def normalize_version(version: str) -> LegacyVersion:
    final_version = version.strip()

    if not RE_VERSION_WITH_EPOCH.match(final_version):
        final_version = '0:{}'.format(final_version)

    if not RE_VERSION_WITH_RELEASE.match(final_version):
        final_version = '{}-1'.format(final_version)

    return LegacyVersion(final_version)


def match_required_version(current_version: str, operator: str, required_version: str) -> bool:
    final_required, final_current = required_version.strip(), current_version.strip()

    required_has_epoch, current_no_epoch = bool(RE_VERSION_WITH_EPOCH.match(final_required)), RE_VERSION_WITH_EPOCH.split(final_current)
    current_has_epoch = len(current_no_epoch) > 1

    if required_has_epoch and not current_has_epoch:
        final_current = '0:{}'.format(final_current)
    elif current_has_epoch and not required_has_epoch:
        final_current = current_no_epoch[1]

    required_has_release, current_no_release = bool(RE_VERSION_WITH_RELEASE.match(final_required)), RE_VERSION_WITH_RELEASE.split(final_current)
    current_has_release = len(current_no_release) > 1

    if required_has_release and not current_has_release:
        final_current = '{}-1'.format(final_current)
    elif current_has_release and not required_has_release:
        final_current = current_no_release[1]

    final_required, final_current = LegacyVersion(final_required), LegacyVersion(final_current)

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
