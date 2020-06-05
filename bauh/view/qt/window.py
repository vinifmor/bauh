import logging
import time
import traceback
from pathlib import Path
from typing import List, Type, Set, Tuple

from PyQt5.QtCore import QEvent, Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent, QCursor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHeaderView, QToolBar, \
    QLabel, QPlainTextEdit, QLineEdit, QProgressBar, QPushButton, QComboBox, QApplication, QListView, QSizePolicy, \
    QMenu, QAction

from bauh import LOGS_PATH
from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import SoftwarePackage
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.commons import user
from bauh.commons.html import bold
from bauh.view.core.tray_client import notify_tray
from bauh.view.qt import dialog, commons, qt_utils, root, styles
from bauh.view.qt.about import AboutDialog
from bauh.view.qt.apps_table import AppsTable, UpdateToggleButton
from bauh.view.qt.colors import GREEN
from bauh.view.qt.components import new_spacer, InputFilter, IconButton
from bauh.view.qt.confirmation import ConfirmationDialog
from bauh.view.qt.history import HistoryDialog
from bauh.view.qt.info import InfoDialog
from bauh.view.qt.root import ask_root_password
from bauh.view.qt.screenshots import ScreenshotsDialog
from bauh.view.qt.settings import SettingsWindow
from bauh.view.qt.thread import UpgradeSelected, RefreshApps, UninstallApp, DowngradeApp, GetAppInfo, \
    GetAppHistory, SearchPackages, InstallPackage, AnimateProgress, NotifyPackagesReady, FindSuggestions, \
    ListWarnings, \
    AsyncAction, LaunchApp, ApplyFilters, CustomSoftwareAction, GetScreenshots, CustomAction, NotifyInstalledLoaded, \
    IgnorePackageUpdates
from bauh.view.qt.view_model import PackageView, PackageViewStatus
from bauh.view.util import util, resource
from bauh.view.util.translation import I18n

DARK_ORANGE = '#FF4500'


def toolbar_button_style(bg: str = None, color: str = None):
    style = 'QPushButton { font-weight: 500;'

    if bg:
        style += 'background: {};'.format(bg)

    if color:
        style += 'color: {};'.format(color)

    style += ' }'
    return style


class ManageWindow(QWidget):
    signal_user_res = pyqtSignal(bool)
    signal_root_password = pyqtSignal(str, bool)
    signal_table_update = pyqtSignal()

    def __init__(self, i18n: I18n, icon_cache: MemoryCache, manager: SoftwareManager, screen_size, config: dict,
                 context: ApplicationContext, http_client: HttpClient, logger: logging.Logger, icon: QIcon):
        super(ManageWindow, self).__init__()
        self.i18n = i18n
        self.logger = logger
        self.manager = manager
        self.working = False  # restrict the number of threaded actions
        self.pkgs = []  # packages current loaded in the table
        self.pkgs_available = []  # all packages loaded in memory
        self.pkgs_installed = []  # cached installed packages
        self.display_limit = config['ui']['table']['max_displayed']
        self.icon_cache = icon_cache
        self.screen_size = screen_size
        self.config = config
        self.context = context
        self.http_client = http_client

        self.icon_app = icon
        self.setWindowIcon(self.icon_app)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.toolbar_top = QToolBar()
        self.toolbar_top.addWidget(new_spacer())

        self.label_status = QLabel()
        self.label_status.setText('')
        self.label_status.setStyleSheet("font-weight: bold")
        self.toolbar_top.addWidget(self.label_status)

        self.toolbar_search = QToolBar()
        self.toolbar_search.setStyleSheet("spacing: 0px;")
        self.toolbar_search.setContentsMargins(0, 0, 0, 0)

        label_pre_search = QLabel()
        label_pre_search.setStyleSheet("""
            background: white; 
            border-top-left-radius: 5px; 
            border-bottom-left-radius: 5px;
            border-left: 1px solid lightgrey; 
            border-top: 1px solid lightgrey; 
            border-bottom: 1px solid lightgrey;
        """)

        self.toolbar_search.addWidget(label_pre_search)

        self.input_search = QLineEdit()
        self.input_search.setFrame(False)
        self.input_search.setPlaceholderText(self.i18n['window_manage.input_search.placeholder'] + "...")
        self.input_search.setToolTip(self.i18n['window_manage.input_search.tooltip'])
        self.input_search.setStyleSheet("""QLineEdit { 
                background-color: white; 
                color: grey; 
                spacing: 0; 
                height: 30px; 
                font-size: 12px; 
                width: 300px; 
                border-bottom: 1px solid lightgrey; 
                border-top: 1px solid lightgrey; 
        } 
        """)
        self.input_search.returnPressed.connect(self.search)
        self.toolbar_search.addWidget(self.input_search)

        label_pos_search = QLabel()
        label_pos_search.setPixmap(QIcon(resource.get_path('img/search.svg')).pixmap(QSize(10, 10)))
        label_pos_search.setStyleSheet("""
            background: white; padding-right: 10px; 
            border-top-right-radius: 5px; 
            border-bottom-right-radius: 5px; 
            border-right: 1px solid lightgrey; 
            border-top: 1px solid lightgrey; 
            border-bottom: 1px solid lightgrey;
        """)

        self.toolbar_search.addWidget(label_pos_search)

        self.ref_toolbar_search = self.toolbar_top.addWidget(self.toolbar_search)
        self.toolbar_top.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_top)

        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet('QToolBar {spacing: 4px; margin-top: 15px; margin-bottom: 5px}')
        self.toolbar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.checkbox_updates = QCheckBox()
        self.checkbox_updates.setCursor(QCursor(Qt.PointingHandCursor))
        self.checkbox_updates.setText(self.i18n['updates'].capitalize())
        self.checkbox_updates.stateChanged.connect(self._handle_updates_filter)
        self.ref_checkbox_updates = self.toolbar.addWidget(self.checkbox_updates)

        self.checkbox_only_apps = QCheckBox()
        self.checkbox_only_apps.setCursor(QCursor(Qt.PointingHandCursor))
        self.checkbox_only_apps.setText(self.i18n['manage_window.checkbox.only_apps'])
        self.checkbox_only_apps.setChecked(True)
        self.checkbox_only_apps.stateChanged.connect(self._handle_filter_only_apps)
        self.ref_checkbox_only_apps = self.toolbar.addWidget(self.checkbox_only_apps)

        self.any_type_filter = 'any'
        self.cache_type_filter_icons = {}
        self.combo_filter_type = QComboBox()
        self.combo_filter_type.setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_filter_type.setView(QListView())
        self.combo_filter_type.setStyleSheet('QLineEdit { height: 2px; }')
        self.combo_filter_type.setIconSize(QSize(14, 14))
        self.combo_filter_type.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_filter_type.setEditable(True)
        self.combo_filter_type.lineEdit().setReadOnly(True)
        self.combo_filter_type.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_filter_type.activated.connect(self._handle_type_filter)
        self.combo_filter_type.addItem('--- {} ---'.format(self.i18n['type'].capitalize()), self.any_type_filter)
        self.ref_combo_filter_type = self.toolbar.addWidget(self.combo_filter_type)

        self.any_category_filter = 'any'
        self.combo_categories = QComboBox()
        self.combo_categories.setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_categories.setStyleSheet('QLineEdit { height: 2px; }')
        self.combo_categories.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_categories.setEditable(True)
        self.combo_categories.lineEdit().setReadOnly(True)
        self.combo_categories.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_categories.activated.connect(self._handle_category_filter)
        self.combo_categories.addItem('--- {} ---'.format(self.i18n['category'].capitalize()), self.any_category_filter)
        self.ref_combo_categories = self.toolbar.addWidget(self.combo_categories)

        self.input_name_filter = InputFilter(self.apply_filters_async)
        self.input_name_filter.setPlaceholderText(self.i18n['manage_window.name_filter.placeholder'] + '...')
        self.input_name_filter.setToolTip(self.i18n['manage_window.name_filter.tooltip'])
        self.input_name_filter.setStyleSheet("QLineEdit { background-color: white; color: gray;}")
        self.input_name_filter.setFixedWidth(130)
        self.ref_input_name_filter = self.toolbar.addWidget(self.input_name_filter)

        self.toolbar.addWidget(new_spacer())

        toolbar_bts = []

        if config['suggestions']['enabled']:
            self.bt_suggestions = QPushButton()
            self.bt_suggestions.setCursor(QCursor(Qt.PointingHandCursor))
            self.bt_suggestions.setToolTip(self.i18n['manage_window.bt.suggestions.tooltip'])
            self.bt_suggestions.setText(self.i18n['manage_window.bt.suggestions.text'].capitalize())
            self.bt_suggestions.setIcon(QIcon(resource.get_path('img/suggestions.svg')))
            self.bt_suggestions.setStyleSheet(toolbar_button_style())
            self.bt_suggestions.clicked.connect(self.read_suggestions)
            self.ref_bt_suggestions = self.toolbar.addWidget(self.bt_suggestions)
            toolbar_bts.append(self.bt_suggestions)
        else:
            self.bt_suggestions = None
            self.ref_bt_suggestions = None

        self.bt_installed = QPushButton()
        self.bt_installed.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_installed.setToolTip(self.i18n['manage_window.bt.installed.tooltip'])
        self.bt_installed.setIcon(QIcon(resource.get_path('img/disk.svg')))
        self.bt_installed.setText(self.i18n['manage_window.bt.installed.text'].capitalize())
        self.bt_installed.clicked.connect(self._begin_loading_installed)
        self.bt_installed.setStyleSheet(toolbar_button_style())
        self.ref_bt_installed = self.toolbar.addWidget(self.bt_installed)
        toolbar_bts.append(self.bt_installed)

        self.bt_refresh = QPushButton()
        self.bt_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_refresh.setToolTip(i18n['manage_window.bt.refresh.tooltip'])
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        self.bt_refresh.setText(self.i18n['manage_window.bt.refresh.text'])
        self.bt_refresh.setStyleSheet(toolbar_button_style())
        self.bt_refresh.clicked.connect(lambda: self.refresh_packages(keep_console=False))
        toolbar_bts.append(self.bt_refresh)
        self.ref_bt_refresh = self.toolbar.addWidget(self.bt_refresh)

        self.bt_upgrade = QPushButton()
        self.bt_upgrade.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_upgrade.setToolTip(i18n['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setIcon(QIcon(resource.get_path('img/app_update.svg')))
        self.bt_upgrade.setText(i18n['manage_window.bt.upgrade.text'])
        self.bt_upgrade.setStyleSheet(toolbar_button_style(GREEN, 'white'))
        self.bt_upgrade.clicked.connect(self.update_selected)
        toolbar_bts.append(self.bt_upgrade)
        self.ref_bt_upgrade = self.toolbar.addWidget(self.bt_upgrade)

        # setting all buttons to the same size:
        bt_biggest_size = 0
        for bt in toolbar_bts:
            bt_width = bt.sizeHint().width()
            if bt_width > bt_biggest_size:
                bt_biggest_size = bt_width

        for bt in toolbar_bts:
            bt_width = bt.sizeHint().width()
            if bt_biggest_size > bt_width:
                bt.setFixedWidth(bt_biggest_size)

        self.layout.addWidget(self.toolbar)

        self.table_apps = AppsTable(self, self.icon_cache, download_icons=bool(self.config['download']['icons']))
        self.table_apps.change_headers_policy()

        self.layout.addWidget(self.table_apps)

        toolbar_console = QToolBar()

        self.checkbox_console = QCheckBox()
        self.checkbox_console.setCursor(QCursor(Qt.PointingHandCursor))
        self.checkbox_console.setText(self.i18n['manage_window.checkbox.show_details'])
        self.checkbox_console.stateChanged.connect(self._handle_console)
        self.checkbox_console.setVisible(False)
        self.ref_checkbox_console = toolbar_console.addWidget(self.checkbox_console)

        toolbar_console.addWidget(new_spacer())

        self.label_displayed = QLabel()
        toolbar_console.addWidget(self.label_displayed)

        self.layout.addWidget(toolbar_console)

        self.textarea_output = QPlainTextEdit(self)
        self.textarea_output.resize(self.table_apps.size())
        self.textarea_output.setStyleSheet("background: black; color: white;")
        self.layout.addWidget(self.textarea_output)
        self.textarea_output.setVisible(False)
        self.textarea_output.setReadOnly(True)

        self.toolbar_substatus = QToolBar()
        self.toolbar_substatus.addWidget(new_spacer())
        self.label_substatus = QLabel()
        self.toolbar_substatus.addWidget(self.label_substatus)
        self.toolbar_substatus.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_substatus)
        self._change_label_substatus('')

        self.thread_update = self._bind_async_action(UpgradeSelected(self.manager, self.i18n), finished_call=self._finish_upgrade_selected)
        self.thread_refresh = self._bind_async_action(RefreshApps(self.manager), finished_call=self._finish_refresh_apps, only_finished=True)
        self.thread_uninstall = self._bind_async_action(UninstallApp(self.manager, self.icon_cache, self.i18n), finished_call=self._finish_uninstall)
        self.thread_get_info = self._bind_async_action(GetAppInfo(self.manager), finished_call=self._finish_get_info)
        self.thread_get_history = self._bind_async_action(GetAppHistory(self.manager, self.i18n), finished_call=self._finish_get_history)
        self.thread_search = self._bind_async_action(SearchPackages(self.manager), finished_call=self._finish_search, only_finished=True)
        self.thread_downgrade = self._bind_async_action(DowngradeApp(self.manager, self.i18n), finished_call=self._finish_downgrade)
        self.thread_suggestions = self._bind_async_action(FindSuggestions(man=self.manager), finished_call=self._finish_search, only_finished=True)
        self.thread_run_app = self._bind_async_action(LaunchApp(self.manager), finished_call=self._finish_run_app, only_finished=False)
        self.thread_custom_action = self._bind_async_action(CustomAction(manager=self.manager, i18n=self.i18n), finished_call=self._finish_custom_action)
        self.thread_screenshots = self._bind_async_action(GetScreenshots(self.manager), finished_call=self._finish_get_screenshots)

        self.thread_apply_filters = ApplyFilters()
        self.thread_apply_filters.signal_finished.connect(self._finish_apply_filters_async)
        self.thread_apply_filters.signal_table.connect(self._update_table_and_upgrades)
        self.signal_table_update.connect(self.thread_apply_filters.stop_waiting)

        self.thread_install = InstallPackage(manager=self.manager, icon_cache=self.icon_cache, i18n=self.i18n)
        self._bind_async_action(self.thread_install, finished_call=self._finish_install)

        self.thread_animate_progress = AnimateProgress()
        self.thread_animate_progress.signal_change.connect(self._update_progress)

        self.thread_notify_pkgs_ready = NotifyPackagesReady()
        self.thread_notify_pkgs_ready.signal_changed.connect(self._update_package_data)
        self.thread_notify_pkgs_ready.signal_finished.connect(self._update_state_when_pkgs_ready)

        self.thread_ignore_updates = IgnorePackageUpdates(manager=self.manager)
        self._bind_async_action(self.thread_ignore_updates, finished_call=self.finish_ignore_updates)

        self.toolbar_bottom = QToolBar()
        self.toolbar_bottom.setIconSize(QSize(16, 16))
        self.toolbar_bottom.setStyleSheet('QToolBar { spacing: 3px }')

        self.toolbar_bottom.addWidget(new_spacer())

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(styles.PROGRESS_BAR)
        self.progress_bar.setMaximumHeight(10 if QApplication.instance().style().objectName().lower() == 'windows' else 4)

        self.progress_bar.setTextVisible(False)
        self.ref_progress_bar = self.toolbar_bottom.addWidget(self.progress_bar)

        self.toolbar_bottom.addWidget(new_spacer())

        self.custom_actions = manager.get_custom_actions()
        bt_custom_actions = IconButton(QIcon(resource.get_path('img/custom_actions.svg')),
                                       action=self.show_custom_actions,
                                       i18n=self.i18n,
                                       tooltip=self.i18n['manage_window.bt_custom_actions.tip'])
        bt_custom_actions.setVisible(bool(self.custom_actions))
        self.ref_bt_custom_actions = self.toolbar_bottom.addWidget(bt_custom_actions)

        bt_settings = IconButton(QIcon(resource.get_path('img/settings.svg')),
                                 action=self.show_settings,
                                 i18n=self.i18n,
                                 tooltip=self.i18n['manage_window.bt_settings.tooltip'])
        self.ref_bt_settings = self.toolbar_bottom.addWidget(bt_settings)

        bt_about = IconButton(QIcon(resource.get_path('img/info.svg')),
                              action=self._show_about,
                              i18n=self.i18n,
                              tooltip=self.i18n['manage_window.settings.about'])
        self.ref_bt_about = self.toolbar_bottom.addWidget(bt_about)

        self.layout.addWidget(self.toolbar_bottom)

        qt_utils.centralize(self)

        self.filter_only_apps = True
        self.type_filter = self.any_type_filter
        self.category_filter = self.any_category_filter
        self.filter_updates = False
        self._maximized = False
        self.progress_controll_enabled = True
        self.recent_installation = False
        self.recent_uninstall = False
        self.types_changed = False

        self.dialog_about = None
        self.load_suggestions = bool(config['suggestions']['enabled'])
        self.first_refresh = True

        self.thread_warnings = ListWarnings(man=manager, i18n=i18n)
        self.thread_warnings.signal_warnings.connect(self._show_warnings)
        self.settings_window = None
        self.search_performed = False

        self.thread_load_installed = NotifyInstalledLoaded()
        self.thread_load_installed.signal_loaded.connect(self._finish_loading_installed)
        self.setMinimumHeight(int(screen_size.height() * 0.5))
        self.setMinimumWidth(int(screen_size.width() * 0.6))

    def update_custom_actions(self):
        self.custom_actions = self.manager.get_custom_actions()
        self.ref_bt_custom_actions.setVisible(bool(self.custom_actions))

    def _update_process_progress(self, val: int):
        if self.progress_controll_enabled:
            self.thread_animate_progress.set_progress(val)

    def apply_filters_async(self):
        self.thread_notify_pkgs_ready.work = False
        self.thread_notify_pkgs_ready.wait(5)
        self.label_status.setText(self.i18n['manage_window.status.filtering'] + '...')

        self.ref_toolbar_search.setVisible(False)

        if self.ref_input_name_filter.isVisible():
            self.input_name_filter.setReadOnly(True)

        self.thread_apply_filters.filters = self._gen_filters()
        self.thread_apply_filters.pkgs = self.pkgs_available
        self.thread_apply_filters.start()
        self.table_apps.setEnabled(False)
        self.checkbox_only_apps.setEnabled(False)
        self.combo_categories.setEnabled(False)
        self.combo_filter_type.setEnabled(False)
        self.input_name_filter.setEnabled(False)
        self.checkbox_updates.setEnabled(False)
        self.setFocus(Qt.NoFocusReason)

    def _update_table_and_upgrades(self, pkgs_info: dict):
        self._update_table(pkgs_info=pkgs_info, signal=True)
        self.table_apps.setEnabled(False)
        self.update_bt_upgrade(pkgs_info)

        if self.pkgs:
            self._update_state_when_pkgs_ready()
            self.thread_notify_pkgs_ready.work = False
            self.thread_notify_pkgs_ready.wait(5)
            self.thread_notify_pkgs_ready.pkgs = self.pkgs
            self.thread_notify_pkgs_ready.work = True
            self.thread_notify_pkgs_ready.start()

    def _finish_apply_filters_async(self, success: bool):
        self.table_apps.setEnabled(True)
        self.checkbox_only_apps.setEnabled(True)
        self.checkbox_updates.setEnabled(True)
        self.combo_categories.setEnabled(True)
        self.combo_filter_type.setEnabled(True)
        self.input_name_filter.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.label_status.setText('')
        self.ref_toolbar_search.setVisible(True)

        if self.ref_input_name_filter.isVisible():
            self.input_name_filter.setReadOnly(False)

    def _bind_async_action(self, action: AsyncAction, finished_call, only_finished: bool = False) -> AsyncAction:
        action.signal_finished.connect(finished_call)

        if not only_finished:
            action.signal_confirmation.connect(self._ask_confirmation)
            action.signal_output.connect(self._update_action_output)
            action.signal_message.connect(self._show_message)
            action.signal_status.connect(self._change_label_status)
            action.signal_substatus.connect(self._change_label_substatus)
            action.signal_progress.connect(self._update_process_progress)
            action.signal_progress_control.connect(self.set_progress_controll)
            action.signal_root_password.connect(self._pause_and_ask_root_password)

            self.signal_user_res.connect(action.confirm)
            self.signal_root_password.connect(action.set_root_password)

        return action

    def _ask_confirmation(self, msg: dict):
        self.thread_animate_progress.pause()
        diag = ConfirmationDialog(title=msg['title'],
                                  body=msg['body'],
                                  i18n=self.i18n,
                                  components=msg['components'],
                                  confirmation_label=msg['confirmation_label'],
                                  deny_label=msg['deny_label'],
                                  deny_button=msg['deny_button'],
                                  window_cancel=msg['window_cancel'],
                                  screen_size=self.screen_size)
        res = diag.is_confirmed()
        self.thread_animate_progress.animate()
        self.signal_user_res.emit(res)

    def _pause_and_ask_root_password(self):
        self.thread_animate_progress.pause()
        password, valid = root.ask_root_password(self.context, self.i18n)

        self.thread_animate_progress.animate()
        self.signal_root_password.emit(password, valid)

    def _show_message(self, msg: dict):
        self.thread_animate_progress.pause()
        dialog.show_message(title=msg['title'], body=msg['body'], type_=msg['type'])
        self.thread_animate_progress.animate()

    def _show_warnings(self, warnings: List[str]):
        if warnings:
            dialog.show_message(title=self.i18n['warning'].capitalize(), body='<p>{}</p>'.format('<br/><br/>'.join(warnings)), type_=MessageType.WARNING)

    def show(self):
        super(ManageWindow, self).show()

        if not self.thread_warnings.isFinished():
            self.thread_warnings.start()

        qt_utils.centralize(self)

    def verify_warnings(self):
        self.thread_warnings.start()

    def _begin_loading_installed(self):
        if self.pkgs_installed:
            self.search_performed = False
            self.ref_bt_upgrade.setVisible(True)
            self.ref_checkbox_only_apps.setVisible(True)
            self.input_search.setText('')
            self.input_name_filter.setText('')
            self._begin_action(self.i18n['manage_window.status.installed'], keep_bt_installed=False, clear_filters=not self.recent_uninstall)
            self.thread_load_installed.start()

    def _finish_loading_installed(self):
        self.finish_action()
        self.update_pkgs(new_pkgs=None, as_installed=True)

    def _show_about(self):
        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.config)

        self.dialog_about.show()

    def _handle_updates_filter(self, status: int):
        self.filter_updates = status == 2
        self.apply_filters_async()

    def _handle_filter_only_apps(self, status: int):
        self.filter_only_apps = status == 2
        self.apply_filters_async()

    def _handle_type_filter(self, idx: int):
        self.type_filter = self.combo_filter_type.itemData(idx)
        self.combo_filter_type.adjustSize()
        self.apply_filters_async()

    def _handle_category_filter(self, idx: int):
        self.category_filter = self.combo_categories.itemData(idx)
        self.apply_filters_async()

    def _update_state_when_pkgs_ready(self):
        if self.progress_bar.isVisible():
            return

        if not self.recent_installation:
            self._reload_categories()

        self._resize()

    def _update_package_data(self, idx: int):
        if self.table_apps.isEnabled():
            pkg = self.pkgs[idx]
            pkg.status = PackageViewStatus.READY
            self.table_apps.update_package(pkg)

    def _reload_categories(self):
        categories = set()

        for p in self.pkgs_available:
            if p.model.categories:
                for c in p.model.categories:
                    categories.add(c.lower())

        if categories:
            self._update_categories(categories, keep_selected=True)

    def changeEvent(self, e: QEvent):
        if isinstance(e, QWindowStateChangeEvent):
            self._maximized = self.isMaximized()
            self.table_apps.change_headers_policy(maximized=self._maximized)

    def _handle_console(self, checked: bool):

        if checked:
            self.textarea_output.show()
        else:
            self.textarea_output.hide()

    def _handle_console_option(self, enable: bool):

        if enable:
            self.textarea_output.clear()

        self.ref_checkbox_console.setVisible(enable)
        self.checkbox_console.setChecked(False)
        self.textarea_output.hide()

    def refresh_packages(self, keep_console: bool = True, top_app: PackageView = None, pkg_types: Set[Type[SoftwarePackage]] = None):
        self.recent_installation = False
        self.input_search.clear()

        if not keep_console:
            self._handle_console_option(False)

        self.ref_checkbox_updates.setVisible(False)
        self.ref_checkbox_only_apps.setVisible(False)
        self._begin_action(self.i18n['manage_window.status.refreshing'], keep_bt_installed=False, clear_filters=not self.recent_uninstall)

        self.thread_refresh.app = top_app  # the app will be on top when refresh happens
        self.thread_refresh.pkg_types = pkg_types
        self.thread_refresh.start()

    def read_suggestions(self):
        self.input_search.clear()
        self._handle_console_option(False)
        self.ref_checkbox_updates.setVisible(False)
        self.ref_checkbox_only_apps.setVisible(False)
        self._begin_action(self.i18n['manage_window.status.suggestions'], keep_bt_installed=False, clear_filters=not self.recent_uninstall)
        self.thread_suggestions.filter_installed = True
        self.thread_suggestions.start()

    def _finish_refresh_apps(self, res: dict, as_installed: bool = True):
        self.finish_action()
        self.search_performed = False

        self.ref_checkbox_only_apps.setVisible(bool(res['installed']))
        self.ref_bt_upgrade.setVisible(True)
        self.update_pkgs(res['installed'], as_installed=as_installed, types=res['types'], keep_filters=self.recent_uninstall and res['types'])
        self.load_suggestions = False
        self.recent_uninstall = False
        self.types_changed = False
        self._hide_fields_after_recent_installation()

    def uninstall_app(self, app: PackageView):
        pwd, proceed = self._ask_root_password('uninstall', app)

        if not proceed:
            return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.i18n['manage_window.status.uninstalling'], app.model.name), clear_filters=False)

        self.thread_uninstall.app = app
        self.thread_uninstall.root_pwd = pwd
        self.thread_uninstall.start()

    def run_app(self, app: PackageView):
        self._begin_action(self.i18n['manage_window.status.running_app'].format(app.model.name))
        self.thread_run_app.app = app
        self.thread_run_app.start()

    def _finish_uninstall(self, pkgv: PackageView):
        self.finish_action()

        if pkgv:
            if self._can_notify_user():
                util.notify_user('{} ({}) {}'.format(pkgv.model.name, pkgv.model.get_type(), self.i18n['uninstalled']))

            if not self.search_performed:
                only_pkg_type = len([p for p in self.pkgs if p.model.get_type() == pkgv.model.get_type()]) >= 2
            else:
                only_pkg_type = False

            self.recent_uninstall = True
            self.refresh_packages(pkg_types={pkgv.model.__class__} if only_pkg_type else None)
            self.update_custom_actions()

            notify_tray()
        else:
            if self._can_notify_user():
                util.notify_user('{}: {}'.format(pkgv.model.name, self.i18n['notification.uninstall.failed']))

            self.checkbox_console.setChecked(True)

    def _can_notify_user(self):
        return bool(self.config['system']['notifications']) and (self.isHidden() or self.isMinimized())

    def _finish_downgrade(self, res: dict):
        self.finish_action()

        if res['success']:
            if self._can_notify_user():
                util.notify_user('{} {}'.format(res['app'], self.i18n['downgraded']))

            self.refresh_packages(pkg_types={res['app'].model.__class__} if len(self.pkgs) > 1 else None)
            self.update_custom_actions()
            notify_tray()
        else:
            if self._can_notify_user():
                util.notify_user(self.i18n['notification.downgrade.failed'])

            self.checkbox_console.setChecked(True)

    def _change_label_status(self, status: str):
        self.label_status.setText(status)

    def _change_label_substatus(self, substatus: str):
        self.label_substatus.setText('<p>{}</p>'.format(substatus))
        if not substatus:
            self.toolbar_substatus.hide()
        elif not self.toolbar_substatus.isVisible():
            self.toolbar_substatus.show()

    def _update_table(self, pkgs_info: dict, signal: bool = False):
        self.pkgs = pkgs_info['pkgs_displayed']

        self.table_apps.update_packages(self.pkgs, update_check_enabled=pkgs_info['not_installed'] == 0)

        if not self._maximized:
            self.table_apps.change_headers_policy(QHeaderView.Stretch)
            self.table_apps.change_headers_policy()
            self._resize(accept_lower_width=len(self.pkgs) > 0)
            self.label_displayed.setText('{} / {}'.format(len(self.pkgs), len(self.pkgs_available)))
        else:
            self.label_displayed.setText('')

        if signal:
            self.signal_table_update.emit()

    def update_bt_upgrade(self, pkgs_info: dict = None):
        show_bt_upgrade = False

        if not pkgs_info or pkgs_info['not_installed'] == 0:
            for app_v in (pkgs_info['pkgs_displayed'] if pkgs_info else self.pkgs):
                if not app_v.model.is_update_ignored() and app_v.update_checked:
                    show_bt_upgrade = True
                    break

        self.ref_bt_upgrade.setVisible(show_bt_upgrade)

    def change_update_state(self, pkgs_info: dict, trigger_filters: bool = True, keep_selected: bool = False):
        self.update_bt_upgrade(pkgs_info)

        if pkgs_info['updates'] > 0:

            if pkgs_info['not_installed'] == 0:
                if not self.ref_checkbox_updates.isVisible():
                    self.ref_checkbox_updates.setVisible(True)

                if not self.filter_updates and not keep_selected:
                    self._change_checkbox(self.checkbox_updates, True, 'filter_updates', trigger_filters)

            if pkgs_info['napp_updates'] > 0 and self.filter_only_apps and not keep_selected:
                self._change_checkbox(self.checkbox_only_apps, False, 'filter_only_apps', trigger_filters)
        else:
            if not keep_selected:
                self._change_checkbox(self.checkbox_updates, False, 'filter_updates', trigger_filters)

            self.ref_checkbox_updates.setVisible(False)

    def _change_checkbox(self, checkbox: QCheckBox, checked: bool, attr: str = None, trigger: bool = True):
        if not trigger:
            checkbox.blockSignals(True)

        checkbox.setChecked(checked)

        if not trigger:
            setattr(self, attr, checked)
            checkbox.blockSignals(False)

    def _gen_filters(self, ignore_updates: bool = False) -> dict:
        return {
            'only_apps': False if self.search_performed else self.filter_only_apps,
            'type': self.type_filter,
            'category': self.category_filter,
            'updates': False if ignore_updates else self.filter_updates,
            'name': self.input_name_filter.get_text().lower() if self.input_name_filter.get_text() else None,
            'display_limit': None if self.filter_updates else self.display_limit
        }

    def update_pkgs(self, new_pkgs: List[SoftwarePackage], as_installed: bool, types: Set[type] = None, ignore_updates: bool = False, keep_filters: bool = False):
        self.input_name_filter.setText('')
        pkgs_info = commons.new_pkgs_info()
        filters = self._gen_filters(ignore_updates=ignore_updates)

        if new_pkgs is not None:
            old_installed = None

            if as_installed:
                old_installed = self.pkgs_installed
                self.pkgs_installed = []

            for pkg in new_pkgs:
                app_model = PackageView(model=pkg, i18n=self.i18n)
                commons.update_info(app_model, pkgs_info)
                commons.apply_filters(app_model, filters, pkgs_info)

            if old_installed and types:
                for pkgv in old_installed:
                    if pkgv.model.__class__ not in types:
                        commons.update_info(pkgv, pkgs_info)
                        commons.apply_filters(pkgv, filters, pkgs_info)

        else:  # use installed
            for pkgv in self.pkgs_installed:
                commons.update_info(pkgv, pkgs_info)
                commons.apply_filters(pkgv, filters, pkgs_info)

        if pkgs_info['apps_count'] == 0:
            if self.load_suggestions or self.types_changed:
                self._begin_search('')
                self.thread_suggestions.filter_installed = False
                self.thread_suggestions.start()
                return
            else:
                if not keep_filters:
                    self._change_checkbox(self.checkbox_only_apps, False, 'filter_only_apps', trigger=False)
                    self.checkbox_only_apps.setCheckable(False)
        else:
            if not keep_filters:
                self.checkbox_only_apps.setCheckable(True)
                self._change_checkbox(self.checkbox_only_apps, True, 'filter_only_apps', trigger=False)

        self.change_update_state(pkgs_info=pkgs_info, trigger_filters=False, keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._update_categories(pkgs_info['categories'], keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._update_type_filters(pkgs_info['available_types'], keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._apply_filters(pkgs_info, ignore_updates=ignore_updates)
        self.change_update_state(pkgs_info=pkgs_info, trigger_filters=False, keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))

        self.pkgs_available = pkgs_info['pkgs']

        if as_installed:
            self.pkgs_installed = pkgs_info['pkgs']

        self.pkgs = pkgs_info['pkgs_displayed']

        if self.pkgs:
            self.ref_input_name_filter.setVisible(True)

        self._update_table(pkgs_info=pkgs_info)

        if new_pkgs:
            self.thread_notify_pkgs_ready.pkgs = self.pkgs
            self.thread_notify_pkgs_ready.start()

        if self.pkgs_installed:
            self.ref_bt_installed.setVisible(not as_installed and not self.recent_installation)

        self._resize(accept_lower_width=bool(self.pkgs_installed))

        if self.first_refresh:
            qt_utils.centralize(self)
            self.first_refresh = False

    def _apply_filters(self, pkgs_info: dict, ignore_updates: bool):
        pkgs_info['pkgs_displayed'] = []
        filters = self._gen_filters(ignore_updates=ignore_updates)
        for pkgv in pkgs_info['pkgs']:
            commons.apply_filters(pkgv, filters, pkgs_info)

    def _update_type_filters(self, available_types: dict = None, keep_selected: bool = False):

        if available_types is None:
            self.ref_combo_filter_type.setVisible(self.combo_filter_type.count() > 1)
        else:
            keeping_selected = keep_selected and available_types and self.type_filter in available_types

            if not keeping_selected:
                self.type_filter = self.any_type_filter

            if available_types and len(available_types) > 1:
                if self.combo_filter_type.count() > 1:
                    for _ in range(self.combo_filter_type.count() - 1):
                        self.combo_filter_type.removeItem(1)

                sel_type = -1
                for idx, item in enumerate(available_types.items()):
                    app_type, icon_path, label = item[0], item[1]['icon'], item[1]['label']

                    icon = self.cache_type_filter_icons.get(app_type)

                    if not icon:
                        icon = QIcon(icon_path)
                        self.cache_type_filter_icons[app_type] = icon

                    self.combo_filter_type.addItem(icon, label, app_type)

                    if keeping_selected and app_type == self.type_filter:
                        sel_type = idx + 1

                self.combo_filter_type.blockSignals(True)
                self.combo_filter_type.setCurrentIndex(sel_type if sel_type > -1 else 0)
                self.combo_filter_type.blockSignals(False)
                self.ref_combo_filter_type.setVisible(True)
            else:
                self.ref_combo_filter_type.setVisible(False)

    def _update_categories(self, categories: Set[str] = None, keep_selected: bool = False):
        if categories is None:
            self.ref_combo_categories.setVisible(self.combo_categories.count() > 1)
        else:
            keeping_selected = keep_selected and categories and self.category_filter in categories

            if not keeping_selected:
                self.category_filter = self.any_category_filter

            if categories:
                if self.combo_categories.count() > 1:
                    for _ in range(self.combo_categories.count() - 1):
                        self.combo_categories.removeItem(1)

                selected_cat = -1
                cat_list = list(categories)
                cat_list.sort()

                for idx, c in enumerate(cat_list):
                    i18n_cat = self.i18n.get('category.{}'.format(c), self.i18n.get(c, c))
                    self.combo_categories.addItem(i18n_cat.capitalize(), c)

                    if keeping_selected and c == self.category_filter:
                        selected_cat = idx + 1

                self.combo_categories.blockSignals(True)
                self.combo_categories.setCurrentIndex(selected_cat if selected_cat > -1 else 0)
                self.combo_categories.blockSignals(False)
                self.ref_combo_categories.setVisible(True)

            else:
                self.ref_combo_categories.setVisible(False)

    def _resize(self, accept_lower_width: bool = True):
        table_width = self.table_apps.get_width()
        toolbar_width = self.toolbar.sizeHint().width()
        topbar_width = self.toolbar_top.sizeHint().width()

        new_width = max(table_width, toolbar_width, topbar_width)
        new_width *= 1.05  # this extra size is not because of the toolbar button, but the table upgrade buttons

        if (self.pkgs and accept_lower_width) or new_width > self.width():
            self.resize(new_width, self.height())

    def set_progress_controll(self, enabled: bool):
        self.progress_controll_enabled = enumerate

    def update_selected(self):
        if dialog.ask_confirmation(title=self.i18n['manage_window.upgrade_all.popup.title'],
                                   body=self.i18n['manage_window.upgrade_all.popup.body'],
                                   i18n=self.i18n,
                                   widgets=[UpdateToggleButton(None, self, self.i18n, clickable=False)]):

            self._handle_console_option(True)
            self._begin_action(self.i18n['manage_window.status.upgrading'])
            self.thread_update.pkgs = self.pkgs
            self.thread_update.start()

    def _finish_upgrade_selected(self, res: dict):
        self.finish_action()

        if res.get('id'):
            output = self.textarea_output.toPlainText()

            if output:
                try:
                    Path(UpgradeSelected.LOGS_DIR).mkdir(parents=True, exist_ok=True)
                    logs_path = '{}/{}.log'.format(UpgradeSelected.LOGS_DIR, res['id'])
                    with open(logs_path, 'w+') as f:
                        f.write(output)

                    self.textarea_output.appendPlainText('\n*Upgrade summary generated at: {}'.format(UpgradeSelected.SUMMARY_FILE.format(res['id'])))
                    self.textarea_output.appendPlainText('*Upgrade logs generated at: {}'.format(logs_path))
                except:
                    traceback.print_exc()

        if res['success']:
            if self._can_notify_user():
                util.notify_user('{} {}'.format(res['updated'], self.i18n['notification.update_selected.success']))

            self.refresh_packages(pkg_types=res['types'])

            notify_tray()
        else:
            if self._can_notify_user():
                util.notify_user(self.i18n['notification.update_selected.failed'])

            self.ref_bt_upgrade.setVisible(True)
            self.checkbox_console.setChecked(True)

        self.update_custom_actions()

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str, keep_search: bool = False, keep_bt_installed: bool = True, clear_filters: bool = False):
        self.ref_input_name_filter.setVisible(False)
        self.ref_combo_filter_type.setVisible(False)
        self.ref_combo_categories.setVisible(False)
        self.ref_bt_custom_actions.setVisible(False)
        self.ref_bt_settings.setVisible(False)
        self.ref_bt_about.setVisible(False)
        self.thread_animate_progress.stop = False
        self.thread_animate_progress.start()
        self.ref_progress_bar.setVisible(True)

        self.label_status.setText(action_label + "...")
        self.ref_bt_upgrade.setVisible(False)
        self.ref_bt_refresh.setVisible(False)

        if self.ref_bt_suggestions:
            self.ref_bt_suggestions.setVisible(False)

        self.checkbox_only_apps.setEnabled(False)
        self.table_apps.setEnabled(False)
        self.checkbox_updates.setEnabled(False)

        if not keep_bt_installed:
            self.ref_bt_installed.setVisible(False)
        elif self.ref_bt_installed.isVisible():
            self.ref_bt_installed.setEnabled(False)

        if keep_search:
            self.ref_toolbar_search.setVisible(True)
        else:
            self.ref_toolbar_search.setVisible(False)

        if clear_filters:
            self._update_type_filters({})
            self._update_categories(set())
        else:
            self.combo_filter_type.setEnabled(False)

    def finish_action(self, keep_filters: bool = False):
        self.thread_animate_progress.stop = True
        self.thread_animate_progress.wait(msecs=1000)
        self.ref_progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        self._change_label_substatus('')
        self.ref_bt_custom_actions.setVisible(bool(self.custom_actions))
        self.ref_bt_settings.setVisible(True)
        self.ref_bt_about.setVisible(True)

        self.ref_bt_refresh.setVisible(True)
        self.checkbox_only_apps.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.input_search.setEnabled(True)
        self.label_status.setText('')
        self.label_substatus.setText('')
        self.ref_toolbar_search.setVisible(True)
        self.ref_toolbar_search.setEnabled(True)
        self.combo_filter_type.setEnabled(True)
        self.checkbox_updates.setEnabled(True)
        self.progress_controll_enabled = True

        if self.ref_bt_suggestions:
            self.ref_bt_suggestions.setVisible(True)

        if self.pkgs:
            self.ref_input_name_filter.setVisible(True)
            self.update_bt_upgrade()
            self._update_type_filters(keep_selected=keep_filters)
            self._update_categories(keep_selected=keep_filters)

            if self.ref_bt_installed.isVisible():
                self.ref_bt_installed.setEnabled(True)

        self._hide_fields_after_recent_installation()

    def _hide_fields_after_recent_installation(self):
        if self.recent_installation:
            self.ref_combo_filter_type.setVisible(False)
            self.ref_combo_categories.setVisible(False)
            self.ref_input_name_filter.setVisible(False)

    def downgrade(self, pkgv: PackageView):
        pwd, proceed = self._ask_root_password('downgrade', pkgv)

        if not proceed:
            return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.i18n['manage_window.status.downgrading'], pkgv.model.name))

        self.thread_downgrade.app = pkgv
        self.thread_downgrade.root_pwd = pwd
        self.thread_downgrade.start()

    def get_app_info(self, pkg: dict):
        self._handle_console_option(False)
        self._begin_action(self.i18n['manage_window.status.info'])

        self.thread_get_info.app = pkg
        self.thread_get_info.start()

    def get_screenshots(self, pkg: PackageView):
        self._handle_console_option(False)
        self._begin_action(self.i18n['manage_window.status.screenshots'].format(bold(pkg.model.name)))

        self.thread_screenshots.pkg = pkg
        self.thread_screenshots.start()

    def _finish_get_screenshots(self, res: dict):
        self.finish_action()

        if res.get('screenshots'):
            diag = ScreenshotsDialog(pkg=res['pkg'],
                                     http_client=self.http_client,
                                     icon_cache=self.icon_cache,
                                     logger=self.logger,
                                     i18n=self.i18n,
                                     screenshots=res['screenshots'])
            diag.exec_()
        else:
            dialog.show_message(title=self.i18n['error'],
                                body=self.i18n['popup.screenshots.no_screenshot.body'].format(bold(res['pkg'].model.name)),
                                type_=MessageType.ERROR)

    def get_app_history(self, app: PackageView):
        self._handle_console_option(False)
        self._begin_action(self.i18n['manage_window.status.history'])

        self.thread_get_history.app = app
        self.thread_get_history.start()

    def _finish_get_info(self, app_info: dict):
        self.finish_action()
        dialog_info = InfoDialog(app=app_info, icon_cache=self.icon_cache, i18n=self.i18n, screen_size=self.screen_size)
        dialog_info.exec_()

    def _finish_get_history(self, res: dict):
        self.finish_action()

        if res.get('error'):
            self._handle_console_option(True)
            self.textarea_output.appendPlainText(res['error'])
            self.checkbox_console.setChecked(True)
        elif not res['history'].history:
            dialog.show_message(title=self.i18n['action.history.no_history.title'],
                                body=self.i18n['action.history.no_history.body'].format(bold(res['history'].pkg.name)),
                                type_=MessageType.WARNING)
        else:
            dialog_history = HistoryDialog(res['history'], self.icon_cache, self.i18n)
            dialog_history.exec_()

    def _begin_search(self, word):
        self._handle_console_option(False)
        self.ref_checkbox_only_apps.setVisible(False)
        self.ref_checkbox_updates.setVisible(False)
        self.filter_updates = False
        self._begin_action('{} {}'.format(self.i18n['manage_window.status.searching'], word if word else ''), clear_filters=True)

    def search(self):
        word = self.input_search.text().strip()
        if word:
            self._begin_search(word)
            self.thread_search.word = word
            self.thread_search.start()

    def _finish_search(self, res: dict):
        self.finish_action()
        self.search_performed = True

        if not res['error']:
            self.ref_bt_upgrade.setVisible(False)
            self.update_pkgs(res['pkgs_found'], as_installed=False, ignore_updates=True)
        else:
            dialog.show_message(title=self.i18n['warning'].capitalize(), body=self.i18n[res['error']], type_=MessageType.WARNING)

    def _ask_root_password(self, action: str, pkg: PackageView) -> Tuple[str, bool]:
        pwd = None
        requires_root = self.manager.requires_root(action, pkg.model)

        if not user.is_root() and requires_root:
            pwd, ok = ask_root_password(self.context, self.i18n)

            if not ok:
                return pwd, False

        return pwd, True

    def install(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password('install', pkg)

        if not proceed:
            return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.i18n['manage_window.status.installing'], pkg.model.name))

        self.thread_install.pkg = pkg
        self.thread_install.root_pwd = pwd
        self.thread_install.start()

    def _finish_install(self, res: dict):
        self.input_search.setText('')
        self.finish_action()

        console_output = self.textarea_output.toPlainText()

        if console_output:
            log_path = '{}/install/{}/{}'.format(LOGS_PATH, res['pkg'].model.get_type(), res['pkg'].model.name)
            try:
                Path(log_path).mkdir(parents=True, exist_ok=True)

                log_file = log_path + '/{}.log'.format(int(time.time()))
                with open(log_file, 'w+') as f:
                    f.write(console_output)

                self.textarea_output.appendPlainText(self.i18n['console.install_logs.path'].format('"{}"'.format(log_file)))
            except:
                self.textarea_output.appendPlainText("[warning] Could not write install log file to '{}'".format(log_path))

        if res['success']:
            self.recent_installation = True
            if self._can_notify_user():
                util.notify_user(msg='{} ({}) {}'.format(res['pkg'].model.name, res['pkg'].model.get_type(), self.i18n['installed']))

            self._finish_refresh_apps({'installed': [res['pkg'].model], 'total': 1, 'types': None})
            self.ref_bt_installed.setVisible(False)
            self.ref_checkbox_only_apps.setVisible(False)
            self.update_custom_actions()
        else:
            if self._can_notify_user():
                util.notify_user('{}: {}'.format(res['pkg'].model.name, self.i18n['notification.install.failed']))

            self.checkbox_console.setChecked(True)

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _finish_run_app(self, success: bool):
        self.finish_action()

    def execute_custom_action(self, pkg: PackageView, action: CustomSoftwareAction):

        if pkg is None and not dialog.ask_confirmation(title=self.i18n['confirmation'].capitalize(),
                                                       body=self.i18n['custom_action.proceed_with'].capitalize().format('"{}"'.format(self.i18n[action.i18_label_key])),
                                                       icon=QIcon(action.icon_path) if action.icon_path else QIcon(resource.get_path('img/logo.svg')),
                                                       i18n=self.i18n):
            return False

        pwd = None

        if not user.is_root() and action.requires_root:
            pwd, ok = ask_root_password(self.context, self.i18n)

            if not ok:
                return

        self._handle_console_option(True)
        self._begin_action('{}{}'.format(self.i18n[action.i18n_status_key], ' {}'.format(pkg.model.name) if pkg else ''))

        self.thread_custom_action.pkg = pkg
        self.thread_custom_action.root_pwd = pwd
        self.thread_custom_action.custom_action = action
        self.thread_custom_action.start()

    def _finish_custom_action(self, res: dict):
        self.finish_action()
        if res['success']:
            if res['action'].refresh:
                self.refresh_packages(pkg_types={res['pkg'].model.__class__} if res['pkg'] else None)
        else:
            self.checkbox_console.setChecked(True)

    def show_settings(self):
        if self.settings_window:
            self.settings_window.handle_display()
        else:
            self.settings_window = SettingsWindow(self.manager, self.i18n, self.screen_size, self)
            self.settings_window.setMinimumWidth(int(self.screen_size.width() / 4))
            self.settings_window.resize(self.size())
            self.settings_window.adjustSize()
            qt_utils.centralize(self.settings_window)
            self.settings_window.show()

    def _map_custom_action(self, action: CustomSoftwareAction) -> QAction:
        custom_action = QAction(self.i18n[action.i18_label_key])

        if action.icon_path:
            try:
                if action.icon_path.startswith('/'):
                    icon = QIcon(action.icon_path)
                else:
                    icon = QIcon.fromTheme(action.icon_path)

                custom_action.setIcon(icon)

            except:
                pass

        custom_action.triggered.connect(lambda: self.execute_custom_action(None, action))
        return custom_action

    def show_custom_actions(self):
        if self.custom_actions:
            menu_row = QMenu()
            menu_row.setCursor(QCursor(Qt.PointingHandCursor))
            actions = [self._map_custom_action(a) for a in self.custom_actions]
            menu_row.addActions(actions)
            menu_row.adjustSize()
            menu_row.popup(QCursor.pos())
            menu_row.exec_()

    def ignore_updates(self, pkg: PackageView):
        status_key = 'ignore_updates' if not pkg.model.is_update_ignored() else 'ignore_updates_reverse'
        self._begin_action(self.i18n['manage_window.status.{}'.format(status_key)].format(pkg.model.name))
        self.thread_ignore_updates.pkg = pkg
        self.thread_ignore_updates.start()

    def finish_ignore_updates(self, res: dict):
        self.finish_action()

        if res['success']:
            self.apply_filters_async()

            if self.pkgs_installed:
                cached_installed = [idx for idx, p in enumerate(self.pkgs_installed) if p == res['pkg']]

                for idx in cached_installed:
                    self.pkgs_installed[idx] = res['pkg']

            dialog.show_message(title=self.i18n['success'].capitalize(),
                                body=self.i18n['action.{}.success'.format(res['action'])].format(bold(res['pkg'].model.name)),
                                type_=MessageType.INFO)
        else:
            dialog.show_message(title=self.i18n['fail'].capitalize(),
                                body=self.i18n['action.{}.fail'.format(res['action'])].format(bold(res['pkg'].model.name)),
                                type_=MessageType.ERROR)

