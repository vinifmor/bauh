from io import StringIO
from threading import Thread

from colorama import Fore

from bauh.core.model import Application


class AsyncDataLoader(Thread):

    def __init__(self, app: Application):
        super(AsyncDataLoader, self).__init__(daemon=True)
        self.id_ = '{}#{}'.format(self.__class__.__name__, id(self))
        self.app = app

    def log_msg(self, msg: str, color: int = None):
        final_msg = StringIO()

        if color:
            final_msg.write(str(color))

        final_msg.write('[{}] '.format(self.id_))

        final_msg.write(msg)

        if color:
            final_msg.write(Fore.RESET)

        final_msg.seek(0)

        print(final_msg.read())
