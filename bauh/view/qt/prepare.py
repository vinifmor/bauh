from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QTabWidget, QToolBar, QHBoxLayout

from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.handler import TaskManager
from bauh.view.util.translation import I18n


class Prepare(QThread, TaskManager):
    signal_register = pyqtSignal(str, str)
    signal_update = pyqtSignal(str, float, str)
    signal_finished = pyqtSignal(str)

    def __init__(self, manager: SoftwareManager):
        super(Prepare, self).__init__()
        self.manager = manager

    def run(self):
        root_pwd = None
        if self.manager.requires_root('prepare', None):
            root_pwd = None  # TODO

        self.manager.prepare(self, root_pwd)

    def update_progress(self, task_id: str, progress: float, substatus: str):
        self.signal_update.emit(task_id, progress, substatus)

    def register_task(self, id_: str, label: str):
        self.signal_register.emit(id_, label)

    def finish_task(self, task_id: str):
        self.signal_finished.emit(task_id)


class PreparePanel(QWidget, TaskManager):

    def __init__(self, manager: SoftwareManager, screen_size: QSize,  i18n: I18n, manage_window: QWidget):
        super(PreparePanel, self).__init__()
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.i18n = i18n
        self.manage_window = manage_window
        self.setWindowTitle('Iniciando...')
        self.setMinimumWidth(screen_size.width() * 0.35)
        self.setMinimumHeight(screen_size.height() * 0.35)
        self.setLayout(QVBoxLayout())
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.manager = manager
        self.tasks = {}
        self.prepare_thread = Prepare(manager)
        self.prepare_thread.signal_register.connect(self.register_task)
        self.prepare_thread.signal_update.connect(self.update_progress)
        self.prepare_thread.signal_finished.connect(self.finish_task)
        # thread for checking all tasks substatus and close the window when they are finished

    def show(self):
        super(PreparePanel, self).show()
        self.prepare_thread.start()

    def register_task(self, id_: str, label: str):
        lb_progress = QLabel('( {0:.2f}'.format(0) + '% ) ')
        lb_status = QLabel(label)
        lb_sub = QLabel()
        self.tasks[id_] = {'lb_status': lb_status,
                           'lb_prog': lb_progress,
                           'progress': 0,
                           'lb_sub': lb_sub,
                           'finished': False}

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        container.setLayout(QHBoxLayout())
        container.layout().addWidget(lb_progress)
        container.layout().addWidget(lb_status)
        container.layout().addWidget(lb_sub)

        self.layout().addWidget(container)

    def update_progress(self, task_id: str, progress: float, substatus: str):
        task = self.tasks[task_id]

        if progress != task['progress']:
            task['progress'] = progress
            task['lb_prog'].setText('( {0:.2f}'.format(progress) + '% )')

        if substatus:
            task['lb_sub'].setText('( {} )'.format(substatus))
        else:
            task['lb_sub'].setText('')

    def finish_task(self, task_id: str):
        task = self.tasks[task_id]
        task['lb_sub'].setText('')

        for key in ('lb_prog', 'lb_status'):
            task[key].setStyleSheet('QLabel { color: green; text-decoration: line-through; }')

        task['finished'] = True
