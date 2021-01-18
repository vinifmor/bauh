import datetime
import operator
import time
from functools import reduce
from typing import Tuple, Optional

from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal, QCoreApplication, QMutex
from PyQt5.QtGui import QIcon, QCursor, QCloseEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QTableWidget, QHeaderView, QPushButton, \
    QProgressBar, QPlainTextEdit, QToolButton, QHBoxLayout

from bauh import __app_name__
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SoftwareAction
from bauh.api.abstract.handler import TaskManager
from bauh.view.qt.components import new_spacer, QCustomToolbar
from bauh.view.qt.qt_utils import centralize
from bauh.view.qt.root import RootDialog
from bauh.view.qt.thread import AnimateProgress
from bauh.view.util.translation import I18n


class Prepare(QThread, TaskManager):
    signal_register = pyqtSignal(str, str, object)
    signal_update = pyqtSignal(str, float, str)
    signal_finished = pyqtSignal(str)
    signal_started = pyqtSignal(int)
    signal_ask_password = pyqtSignal()
    signal_output = pyqtSignal(str, str)

    def __init__(self, context: ApplicationContext, manager: SoftwareManager, i18n: I18n):
        super(Prepare, self).__init__()
        self.manager = manager
        self.i18n = i18n
        self.context = context
        self.waiting_password = False
        self.password_response = None
        self._tasks_added = set()
        self._tasks_finished = set()
        self._add_lock = QMutex()
        self._finish_lock = QMutex()

    def ask_password(self) -> Tuple[bool, Optional[str]]:
        self.waiting_password = True
        self.signal_ask_password.emit()

        while self.waiting_password:
            self.msleep(100)  # waiting for user input

        return self.password_response

    def set_password_reply(self, valid: bool, password: str):
        self.password_response = valid, password
        self.waiting_password = False

    def run(self):
        root_pwd = None
        if self.manager.requires_root(SoftwareAction.PREPARE, None):
            ok, root_pwd = self.ask_password()

            if not ok:
                QCoreApplication.exit(1)

        self.manager.prepare(self, root_pwd, None)
        self.signal_started.emit(len(self._tasks_added))

    def update_progress(self, task_id: str, progress: float, substatus: str):
        self._add_lock.lock()
        if task_id in self._tasks_added:
            self.signal_update.emit(task_id, progress, substatus)
        self._add_lock.unlock()

    def update_output(self, task_id: str, output: str):
        self._add_lock.lock()
        if task_id in self._tasks_added:
            self.signal_output.emit(task_id, output)
        self._add_lock.unlock()

    def register_task(self, id_: str, label: str, icon_path: str):
        self._add_lock.lock()

        if id_ not in self._tasks_added:
            self._tasks_added.add(id_)
            self.signal_register.emit(id_, label, icon_path)

        self._add_lock.unlock()

    def finish_task(self, task_id: str):
        self._add_lock.lock()
        task_registered = task_id in self._tasks_added
        self._add_lock.unlock()

        if not task_registered:
            return

        self._finish_lock.lock()

        if task_id not in self._tasks_finished:
            self._tasks_finished.add(task_id)
            self.signal_finished.emit(task_id)

        self._finish_lock.unlock()


class CheckFinished(QThread):
    signal_finished = pyqtSignal()

    def __init__(self):
        super(CheckFinished, self).__init__()
        self.total = 0
        self.finished = 0

    def run(self):
        while True:
            if self.finished == self.total:
                break

            self.msleep(5)

        self.signal_finished.emit()

    def update(self, finished: int):
        if finished is not None:
            self.finished = finished


class EnableSkip(QThread):

    signal_timeout = pyqtSignal()

    def run(self):
        ti = datetime.datetime.now()

        while True:
            if datetime.datetime.now() >= ti + datetime.timedelta(minutes=1.5):
                self.signal_timeout.emit()
                break

            self.msleep(100)


class PreparePanel(QWidget, TaskManager):

    signal_status = pyqtSignal(int)
    signal_password_response = pyqtSignal(bool, str)

    def __init__(self, context: ApplicationContext, manager: SoftwareManager, screen_size: QSize,
                 i18n: I18n, manage_window: QWidget, app_config: dict):
        super(PreparePanel, self).__init__(flags=Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.i18n = i18n
        self.context = context
        self.app_config = app_config
        self.manage_window = manage_window
        self.setWindowTitle('{} ({})'.format(__app_name__, self.i18n['prepare_panel.title.start'].lower()))
        self.setMinimumWidth(screen_size.width() * 0.5)
        self.setMinimumHeight(screen_size.height() * 0.35)
        self.setMaximumHeight(screen_size.height() * 0.95)
        self.setLayout(QVBoxLayout())
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.manager = manager
        self.tasks = {}
        self.output = {}
        self.added_tasks = 0
        self.ftasks = 0
        self.started_at = None
        self.self_close = False

        self.prepare_thread = Prepare(self.context, manager, self.i18n)
        self.prepare_thread.signal_register.connect(self.register_task)
        self.prepare_thread.signal_update.connect(self.update_progress)
        self.prepare_thread.signal_finished.connect(self.finish_task)
        self.prepare_thread.signal_started.connect(self.start)
        self.prepare_thread.signal_ask_password.connect(self.ask_root_password)
        self.prepare_thread.signal_output.connect(self.update_output)
        self.signal_password_response.connect(self.prepare_thread.set_password_reply)

        self.check_thread = CheckFinished()
        self.signal_status.connect(self.check_thread.update)
        self.check_thread.signal_finished.connect(self.finish)

        self.skip_thread = EnableSkip()
        self.skip_thread.signal_timeout.connect(self._enable_skip_button)

        self.progress_thread = AnimateProgress()
        self.progress_thread.signal_change.connect(self._change_progress)

        self.label_top = QLabel()
        self.label_top.setCursor(QCursor(Qt.WaitCursor))
        self.label_top.setText("{}...".format(self.i18n['prepare_panel.title.start'].capitalize()))
        self.label_top.setObjectName('prepare_status')
        self.label_top.setAlignment(Qt.AlignHCenter)
        self.layout().addWidget(self.label_top)
        self.layout().addWidget(QLabel())

        self.table = QTableWidget()
        self.table.setObjectName('tasks')
        self.table.setCursor(QCursor(Qt.WaitCursor))
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['' for _ in range(4)])
        self.table.horizontalScrollBar().setCursor(QCursor(Qt.PointingHandCursor))
        self.table.verticalScrollBar().setCursor(QCursor(Qt.PointingHandCursor))
        self.layout().addWidget(self.table)

        self.textarea_details = QPlainTextEdit(self)
        self.textarea_details.setObjectName('task_details')
        self.textarea_details.setProperty('console', 'true')
        self.textarea_details.resize(self.table.size())
        self.layout().addWidget(self.textarea_details)
        self.textarea_details.setVisible(False)
        self.textarea_details.setReadOnly(True)
        self.textarea_details.setMaximumHeight(100)
        self.current_output_task = None

        self.bottom_widget = QWidget()
        self.bottom_widget.setLayout(QHBoxLayout())
        self.bottom_widget.layout().addStretch()

        bt_hide_details = QPushButton(self.i18n['prepare.bt_hide_details'])
        bt_hide_details.setObjectName('bt_hide_details')
        bt_hide_details.clicked.connect(self.hide_output)
        bt_hide_details.setCursor(QCursor(Qt.PointingHandCursor))
        self.bottom_widget.layout().addWidget(bt_hide_details)
        self.bottom_widget.layout().addStretch()
        self.layout().addWidget(self.bottom_widget)
        self.bottom_widget.setVisible(False)

        self.bt_bar = QCustomToolbar()
        self.bt_close = QPushButton(self.i18n['close'].capitalize())
        self.bt_close.setObjectName('bt_cancel')
        self.bt_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_close.clicked.connect(self.close)
        self.bt_close.setVisible(False)
        self.bt_bar.add_widget(self.bt_close)
        self.bt_bar.add_widget(new_spacer())

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('prepare_progress')
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setCursor(QCursor(Qt.WaitCursor))
        self.bt_bar.add_widget(self.progress_bar)
        self.bt_bar.add_widget(new_spacer())

        self.bt_skip = QPushButton(self.i18n['prepare_panel.bt_skip.label'].capitalize())
        self.bt_skip.clicked.connect(self.finish)
        self.bt_skip.setEnabled(False)
        self.bt_skip.setCursor(QCursor(Qt.WaitCursor))
        self.bt_bar.add_widget(self.bt_skip)

        self.layout().addWidget(self.bt_bar)

    def hide_output(self):
        self.current_output_task = None
        self.textarea_details.setVisible(False)
        self.textarea_details.clear()
        self.bottom_widget.setVisible(False)
        self._resize_columns()
        self.setFocus(Qt.NoFocusReason)

        if not self.bt_bar.isVisible():
            self.bt_bar.setVisible(True)

    def ask_root_password(self):
        valid, root_pwd = RootDialog.ask_password(self.context, self.i18n)
        self.signal_password_response.emit(valid, root_pwd)

    def _enable_skip_button(self):
        self.bt_skip.setEnabled(True)
        self.bt_skip.setCursor(QCursor(Qt.PointingHandCursor))

    def _change_progress(self, value: int):
        self.progress_bar.setValue(value)

    def get_table_width(self) -> int:
        return reduce(operator.add, [self.table.columnWidth(i) for i in range(self.table.columnCount())])

    def _resize_columns(self):
        header_horizontal = self.table.horizontalHeader()
        for i in range(self.table.columnCount()):
            header_horizontal.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.resize(int(self.get_table_width() * 1.05), self.sizeHint().height())

    def show(self):
        super(PreparePanel, self).show()
        self.prepare_thread.start()
        centralize(self)

    def start(self, tasks: int):
        self.started_at = time.time()
        self.check_thread.total = tasks
        self.check_thread.start()
        self.skip_thread.start()

        self.progress_thread.start()

        self.bt_close.setVisible(True)
        self.progress_bar.setVisible(True)

    def closeEvent(self, ev: QCloseEvent):
        if not self.self_close:
            QCoreApplication.exit()

    def register_task(self, id_: str, label: str, icon_path: str):
        self.added_tasks += 1
        self.table.setRowCount(self.added_tasks)
        task_row = self.added_tasks - 1

        icon_widget = QWidget()
        icon_widget.setProperty('container', 'true')
        icon_widget.setLayout(QHBoxLayout())
        icon_widget.layout().setContentsMargins(10, 0, 10, 0)

        bt_icon = QToolButton()
        bt_icon.setObjectName('bt_task')
        bt_icon.setCursor(QCursor(Qt.WaitCursor))
        bt_icon.setEnabled(False)
        bt_icon.setToolTip(self.i18n['prepare.bt_icon.no_output'])

        if icon_path:
            bt_icon.setIcon(QIcon(icon_path))

        def _show_output():
            lines = self.output[id_]

            if lines:
                self.current_output_task = id_
                self.textarea_details.clear()
                self.textarea_details.setVisible(True)

                for l in lines:
                    self.textarea_details.appendPlainText(l)

                self.bottom_widget.setVisible(True)

            self.setFocus(Qt.NoFocusReason)

            if self.bt_bar.isVisible():
                self.bt_bar.setVisible(False)

        bt_icon.clicked.connect(_show_output)
        icon_widget.layout().addWidget(bt_icon)

        self.table.setCellWidget(task_row, 0, icon_widget)

        lb_status = QLabel(label)
        lb_status.setObjectName('task_status')
        lb_status.setProperty('status', 'running')
        lb_status.setCursor(Qt.WaitCursor)
        lb_status.setMinimumWidth(50)
        lb_status.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        lb_status_col = 1
        self.table.setCellWidget(task_row, lb_status_col, lb_status)

        lb_progress = QLabel('{0:.2f}'.format(0) + '%')
        lb_progress.setObjectName('task_progress')
        lb_progress.setProperty('status', 'running')
        lb_progress.setCursor(Qt.WaitCursor)
        lb_progress.setContentsMargins(10, 0, 10, 0)
        lb_progress.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        lb_progress_col = 2

        self.table.setCellWidget(task_row, lb_progress_col, lb_progress)

        lb_sub = QLabel()
        lb_sub.setObjectName('task_substatus')
        lb_sub.setCursor(Qt.WaitCursor)
        lb_sub.setContentsMargins(10, 0, 10, 0)
        lb_sub.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        lb_sub.setMinimumWidth(50)
        self.table.setCellWidget(task_row, 3, lb_sub)

        self.tasks[id_] = {'bt_icon': bt_icon,
                           'lb_status': lb_status,
                           'lb_status_col': lb_status_col,
                           'lb_prog': lb_progress,
                           'lb_prog_col': lb_progress_col,
                           'progress': 0,
                           'lb_sub': lb_sub,
                           'finished': False,
                           'row': task_row}

    def update_progress(self, task_id: str, progress: float, substatus: str):
        task = self.tasks[task_id]

        if progress != task['progress']:
            task['progress'] = progress
            task['lb_prog'].setText('{0:.2f}'.format(progress) + '%')

        if substatus:
            task['lb_sub'].setText('({})'.format(substatus))
        else:
            task['lb_sub'].setText('')

        self._resize_columns()

    def update_output(self, task_id: str, output: str):
        full_output = self.output.get(task_id)

        if full_output is None:
            full_output = []
            self.output[task_id] = full_output
            task = self.tasks[task_id]
            task['bt_icon'].setEnabled(True)
            task['bt_icon'].setCursor(QCursor(Qt.PointingHandCursor))
            task['bt_icon'].setToolTip(self.i18n['prepare.bt_icon.output'])

        full_output.append(output)

        if self.current_output_task == task_id:
            self.textarea_details.appendPlainText(output)

    def finish_task(self, task_id: str):
        task = self.tasks[task_id]

        for key in ('lb_prog', 'lb_status', 'lb_sub'):
            label = task[key]
            label.setProperty('status', 'done')
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()

        task['finished'] = True
        self._resize_columns()

        self.ftasks += 1
        self.signal_status.emit(self.ftasks)

    def finish(self):
        now = time.time()
        self.context.logger.info("{0} tasks finished in {1:.9f} seconds".format(self.ftasks, (now - self.started_at)))
        if self.isVisible():
            self.manage_window.show()

            if self.app_config['boot']['load_apps']:
                self.manage_window.begin_refresh_packages()
            else:
                self.manage_window.load_without_packages()

            self.self_close = True
            self.close()
