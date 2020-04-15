import logging
import time
from threading import Thread

from bauh.api.abstract.handler import ProcessWatcher
from bauh.view.util.translation import I18n


class TransactionStatusHandler(Thread):

    def __init__(self, watcher: ProcessWatcher, i18n: I18n, npkgs: int, logger: logging.Logger, percentage: bool = True):
        super(TransactionStatusHandler, self).__init__(daemon=True)
        self.watcher = watcher
        self.i18n = i18n
        self.npkgs = npkgs
        self.downloading = 0
        self.upgrading = 0
        self.installing = 0
        self.outputs = []
        self.work = True
        self.logger = logger
        self.percentage = percentage
        self.accepted = {'checking keyring',
                         'checking package integrity',
                         'loading package files',
                         'checking for file conflicts',
                         'checking available disk space'}

    def gen_percentage(self) -> str:
        if self.percentage:
            performed = self.downloading + self.upgrading + self.installing
            return '({0:.2f}%) '.format((performed / (2 * self.npkgs)) * 100)
        else:
            return ''

    def get_performed(self) -> int:
        return self.upgrading + self.installing

    def _handle(self, output: str) -> bool:
        if output:
            if output.startswith('downloading'):
                if self.downloading < self.npkgs:
                    perc = self.gen_percentage()
                    self.downloading += 1

                    self.watcher.change_substatus('{}[{}/{}] {} {}'.format(perc, self.downloading, self.npkgs,
                                                                           self.i18n['downloading'].capitalize(), output.split(' ')[1].strip()))
            elif output.startswith('upgrading'):
                self.downloading = self.npkgs  # to avoid wrong numbers the packages are cached

                if self.get_performed() < self.npkgs:
                    perc = self.gen_percentage()
                    self.upgrading += 1

                    performed = self.upgrading + self.installing

                    if performed <= self.npkgs:
                        self.watcher.change_substatus('{}[{}/{}] {} {}'.format(perc, self.upgrading, self.npkgs,
                                                                                self.i18n['manage_window.status.upgrading'].capitalize(), output.split(' ')[1].strip()))
            elif output.startswith('installing'):
                self.downloading = self.npkgs  # to avoid wrong numbers the packages are cached

                if self.get_performed() < self.npkgs:
                    perc = self.gen_percentage()
                    self.installing += 1

                    performed = self.upgrading + self.installing

                    if performed <= self.npkgs:
                        self.watcher.change_substatus('{}[{}/{}] {} {}'.format(perc, self.installing, self.npkgs,
                                                                               self.i18n['manage_window.status.installing'].capitalize(),
                                                                               output.split(' ')[1].strip()))
            else:
                substatus_found = False
                lower_output = output.lower()
                for msg in self.accepted:
                    if lower_output.startswith(msg):
                        self.watcher.change_substatus(self.i18n['arch.substatus.{}'.format(msg)].capitalize())
                        substatus_found = True
                        break

                if not substatus_found:
                    performed = self.get_performed()

                    if performed == 0 and self.downloading > 0:
                        self.watcher.change_substatus('')
                    elif performed == self.npkgs:
                        self.watcher.change_substatus(self.i18n['finishing'].capitalize())
                        return False

        return True

    def handle(self, output: str):
        self.outputs.append(output)

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
