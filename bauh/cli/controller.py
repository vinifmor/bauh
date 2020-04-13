import json

from bauh.cli import __app_name__
from bauh.view.core.controller import GenericSoftwareManager


class CLIManager:

    def __init__(self, manager: GenericSoftwareManager):
        self.manager = manager

    def _print(self, msg: str):
        print('[{}] {}'.format(__app_name__, msg))

    def list_updates(self, output_format: str):
        updates = self.manager.list_updates()

        json_output = output_format == 'json'

        if not updates and not json_output:
            self._print('No updates available')
            return

        if not json_output:
            self._print('There are {} updates available:\n'.format(len(updates)))

            for idx, u in enumerate(updates):
                print('{}. Name: {}\tVersion: {}\tType: {}'.format(idx+1, u.name, u.version, u.type))
        else:
            print(json.dumps([u.__dict__ for u in updates]))
