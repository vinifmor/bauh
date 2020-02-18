from enum import Enum

from bauh.api.abstract.model import SoftwarePackage
from bauh.view.util.translation import I18n


def get_type_label(type_: str, gem: str, i18n: I18n) -> str:
    type_label = 'gem.{}.type.{}.label'.format(gem, type_)
    return i18n.get(type_label, type_.capitalize())


class PackageViewStatus(Enum):
    LOADING = 0
    READY = 1


class PackageView:

    def __init__(self, model: SoftwarePackage, i18n: I18n):
        self.model = model
        self.update_checked = model.update
        self.status = PackageViewStatus.LOADING
        self.table_index = -1
        self.i18n = i18n

    def get_type_label(self) -> str:
        return get_type_label(self.model.get_type(), self.model.gem_name, self.i18n)

    def __repr__(self):
        return '{} ( {} )'.format(self.model.name, self.model.get_type())
