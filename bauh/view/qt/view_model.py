from enum import Enum

from bauh_api.abstract.model import SoftwarePackage


class PackageViewStatus(Enum):
    LOADING = 0
    READY = 1


class PackageView:

    def __init__(self, model: SoftwarePackage):
        self.model = model
        self.update_checked = model.update
        self.status = PackageViewStatus.LOADING

    def __repr__(self):
        return '{} ( {} )'.format(self.model.base_data.name, self.model.get_type())
