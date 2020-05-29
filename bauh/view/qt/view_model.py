from enum import Enum

from bauh.api.abstract.model import SoftwarePackage, PackageStatus
from bauh.view.util.translation import I18n


class PackageViewStatus(Enum):
    LOADING = 0
    READY = 1


def get_type_label(type_: str, gem: str, i18n: I18n) -> str:
    type_label = 'gem.{}.type.{}.label'.format(gem, type_.lower())
    return i18n.get(type_label, type_.capitalize()).strip()


class PackageView:

    def __init__(self, model: SoftwarePackage, i18n: I18n):
        self.model = model
        self.update_checked = model.update
        self.status = PackageViewStatus.LOADING if model.status == PackageStatus.LOADING_DATA else PackageViewStatus.READY
        self.table_index = -1
        self.i18n = i18n

    def get_type_label(self) -> str:
        return get_type_label(self.model.get_type(), self.model.gem_name, self.i18n)

    def __repr__(self):
        return '{} ( {} )'.format(self.model.name, self.get_type_label())

    def __eq__(self, other):
        if isinstance(other, PackageView):
            return self.model == other.model
