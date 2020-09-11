import logging
import time
from threading import Thread
from typing import Set

from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons.html import bold
from bauh.view.util.translation import I18n


class TransactionStatusHandler(Thread):

    def __init__(self, watcher: ProcessWatcher, i18n: I18n, names: Set[str], logger: logging.Logger,
                 percentage: bool = True, downloading: int = 0, pkgs_to_remove: int = 0):
        super(TransactionStatusHandler, self).__init__(daemon=True)
        self.watcher = watcher
        self.i18n = i18n
        self.pkgs_to_sync = len(names)
        self.names = names
        self.pkgs_to_remove = pkgs_to_remove
        self.downloading = downloading
        self.upgrading = 0
        self.installing = 0
        self.removing = 0
        self.outputs = []
        self.work = True
        self.logger = logger
        self.percentage = percentage
        self.accepted = {'checking keyring': 'keyring',
                         'checking package integrity': 'integrity',
                         'loading package files': 'loading_files',
                         'checking for file conflicts': 'conflicts',
                         'checking available disk space': 'disk_space',
                         ':: Running pre-transaction hooks': 'pre_hooks'}

    def gen_percentage(self) -> str:
        if self.percentage:
            performed = self.downloading + self.upgrading + self.installing
            return '({0:.2f}%) '.format((performed / (2 * self.pkgs_to_sync)) * 100)
        else:
            return ''

    def get_performed(self) -> int:
        return self.upgrading + self.installing

    def _handle(self, output: str) -> bool:
        if output:
            output_split = output.split(' ')

            if output_split[0].lower() == 'removing' and (not self.names or output_split[1].split('.')[0] in self.names):
                if self.pkgs_to_remove > 0:
                    self.removing += 1

                    self.watcher.change_substatus('[{}/{}] {} {}'.format(self.removing, self.pkgs_to_remove,
                                                  self.i18n['uninstalling'].capitalize(), output.split(' ')[1].strip()))
                else:
                    self.watcher.change_substatus('{} {}'.format(self.i18n['uninstalling'].capitalize(), output_split[1].strip()))

            elif output_split[0].lower() == 'downloading' and (not self.names or (n for n in self.names if n in output_split[1])):
                if self.downloading < self.pkgs_to_sync:
                    perc = self.gen_percentage()
                    self.downloading += 1

                    self.watcher.change_substatus('{}[{}/{}] {} {} {}'.format(perc, self.downloading, self.pkgs_to_sync, bold('[pacman]'),
                                                                              self.i18n['downloading'].capitalize(), output_split[1].strip()))
            elif output_split[0].lower() == 'upgrading' and (not self.names or output_split[1].split('.')[0] in self.names):
                if self.get_performed() < self.pkgs_to_sync:
                    perc = self.gen_percentage()
                    self.upgrading += 1

                    performed = self.upgrading + self.installing

                    if performed <= self.pkgs_to_sync:
                        self.watcher.change_substatus('{}[{}/{}] {} {}'.format(perc, performed, self.pkgs_to_sync,
                                                                               self.i18n['manage_window.status.upgrading'].capitalize(), output_split[1].strip()))
            elif output_split[0].lower() == 'installing' and (not self.names or output_split[1].split('.')[0] in self.names):
                if self.get_performed() < self.pkgs_to_sync:
                    perc = self.gen_percentage()
                    self.installing += 1

                    performed = self.upgrading + self.installing

                    if performed <= self.pkgs_to_sync:
                        self.watcher.change_substatus('{}[{}/{}] {} {}'.format(perc, performed, self.pkgs_to_sync,
                                                                               self.i18n['manage_window.status.installing'].capitalize(),
                                                                               output_split[1].strip()))
            else:
                substatus_found = False
                lower_output = output.lower()
                for msg, key in self.accepted.items():
                    if lower_output.startswith(msg):
                        self.watcher.change_substatus(self.i18n['arch.substatus.{}'.format(key)].capitalize())
                        substatus_found = True
                        break

                if not substatus_found:
                    if self.pkgs_to_remove > 0:
                        if self.pkgs_to_remove == self.removing:
                            self.watcher.change_substatus('')
                            return False
                    else:
                        performed = self.get_performed()

                        if performed == 0 and self.downloading > 0:
                            self.watcher.change_substatus('')
                        elif performed == self.pkgs_to_sync:
                            self.watcher.change_substatus(self.i18n['finishing'].capitalize())
                            return False

        return True

    def handle(self, output: str):
        self.outputs.insert(0, output)

    def stop_working(self):
        self.work = False

    def run(self):
        self.logger.info("Starting")
        while self.work:
            if self.outputs:
                output = self.outputs.pop()
                if not self._handle(output):
                    break
            else:
                time.sleep(0.005)

        self.logger.info("Finished")
