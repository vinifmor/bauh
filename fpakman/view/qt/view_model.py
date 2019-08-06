from enum import Enum

from fpakman.core.model import Application


class ApplicationViewStatus(Enum):
    LOADING = 0
    READY = 1


class ApplicationView:

    def __init__(self, model: Application, visible: bool = True):
        self.model = model
        self.update_checked = model.update
        self.visible = visible
        self.status = ApplicationViewStatus.LOADING

    def __repr__(self):
        return '{} ( {} )'.format(self.model.base_data.name, self.model.get_type())
