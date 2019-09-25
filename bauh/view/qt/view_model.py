from enum import Enum

from bauh.api.abstract.model import SoftwarePackage


class PackageViewStatus(Enum):
    LOADING = 0
    READY = 1


class PackageView:

    def __init__(self, model: SoftwarePackage):
        self.model = model
        self.update_checked = model.update
        self.status = PackageViewStatus.LOADING
        self.table_index = -1

    def __repr__(self):
        return '{} ( {} )'.format(self.model.name, self.model.get_type())
