from typing import List

from fpakman.core.model import FlatpakManager


class FlatpakController:

    def __init__(self, model: FlatpakManager):
        self.model = model

    def refresh(self) -> List[dict]:
        return self.model.read_installed()

    def update(self, app_ref: str):
        return self.model.update_app(app_ref)

    def check_installed(self) -> bool:
        version = self.model.get_version()
        return False if version is None else version

    def get_version(self) -> str:
        return self.model.get_version()
