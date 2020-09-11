import logging
import logging
import operator
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
from bauh.view.qt.components import new_spacer, InputFilter, IconButton, QtComponentsManager
from bauh.view.qt.confirmation import ConfirmationDialog
from bauh.view.qt.history import HistoryDialog
from bauh.view.qt.info import InfoDialog
from bauh.view.qt.root import ask_root_password
from bauh.view.qt.screenshots import ScreenshotsDialog
from bauh.view.qt.settings import SettingsWindow
from bauh.view.qt.thread import UpgradeSelected, RefreshApps, UninstallPackage, DowngradePackage, ShowPackageInfo, \
    ShowPackageHistory, SearchPackages, InstallPackage, AnimateProgress, NotifyPackagesReady, FindSuggestions, \
    ListWarnings, \
    AsyncAction, LaunchPackage, ApplyFilters, CustomSoftwareAction, ShowScreenshots, CustomAction, \
    NotifyInstalledLoaded, \
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


# action ids
ACTION_APPLY_FILTERS = 1
ACTION_SEARCH = 2
ACTION_INSTALL = 3
ACTION_UNINSTALL = 4
ACTION_INFO = 5
ACTION_HISTORY = 6
ACTION_DOWNGRADE = 7
ACTION_UPGRADE = 8
ACTION_LAUNCH = 9
ACTION_CUSTOM_ACTION = 10
ACTION_SCREENSHOTS = 11
ACTION_IGNORE_UPDATES = 12

# components ids
SEARCH_BAR = 1
BT_INSTALLED = 2
BT_REFRESH = 3
BT_SUGGESTIONS = 4
BT_UPGRADE = 5
CHECK_UPDATES = 6
CHECK_APPS = 7
COMBO_TYPES = 8
COMBO_CATEGORIES = 9
INP_NAME = 10
CHECK_CONSOLE = 11
BT_SETTINGS = 12
BT_CUSTOM_ACTIONS = 13
BT_ABOUT = 14

# component groups ids
GROUP_FILTERS = 1
GROUP_VIEW_INSTALLED = 2
GROUP_VIEW_SEARCH = 3
GROUP_UPPER_BAR = 4
GROUP_LOWER_BTS = 5


class ManageWindow(QWidget):
    signal_user_res = pyqtSignal(bool)
    signal_root_password = pyqtSignal(str, bool)
    signal_table_update = pyqtSignal()
    signal_stop_notifying = pyqtSignal()

    def __init__(self, i18n: I18n, icon_cache: MemoryCache, manager: SoftwareManager, screen_size, config: dict,
                 context: ApplicationContext, http_client: HttpClient, logger: logging.Logger, icon: QIcon):
        super(ManageWindow, self).__init__()
        self.comp_manager = QtComponentsManager()
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

        self.search_bar = QToolBar()
        self.search_bar.setStyleSheet("spacing: 0px;")
        self.search_bar.setContentsMargins(0, 0, 0, 0)

        self.inp_search = QLineEdit()
        self.inp_search.setFrame(False)
        self.inp_search.setPlaceholderText(self.i18n['window_manage.input_search.placeholder'] + "...")
        self.inp_search.setToolTip(self.i18n['window_manage.input_search.tooltip'])
        self.inp_search.setStyleSheet("""QLineEdit { 
                color: grey;
                spacing: 0; 
                height: 30px; 
                font-size: 12px; 
                width: 300px; 
                border-bottom: 1px solid lightgrey; 
                border-top: 1px solid lightgrey; 
        } 
        """)
        self.inp_search.returnPressed.connect(self.search)
        search_background_color = self.inp_search.palette().color(self.inp_search.backgroundRole()).name()

        label_pre_search = QLabel()
        label_pre_search.setStyleSheet("""
            border-top-left-radius: 5px; 
            border-bottom-left-radius: 5px;
            border-left: 1px solid lightgrey; 
            border-top: 1px solid lightgrey; 
            border-bottom: 1px solid lightgrey;
            background: %s;
        """ % search_background_color)

        self.search_bar.addWidget(label_pre_search)

        self.search_bar.addWidget(self.inp_search)

        label_pos_search = QLabel()
        label_pos_search.setPixmap(QIcon(resource.get_path('img/search.svg')).pixmap(QSize(10, 10)))
        label_pos_search.setStyleSheet("""
            padding-right: 10px; 
            border-top-right-radius: 5px; 
            border-bottom-right-radius: 5px; 
            border-right: 1px solid lightgrey; 
            border-top: 1px solid lightgrey; 
            border-bottom: 1px solid lightgrey;
            background: %s;
        """ % search_background_color)

        self.search_bar.addWidget(label_pos_search)

        self.comp_manager.register_component(SEARCH_BAR, self.search_bar, self.toolbar_top.addWidget(self.search_bar))

        self.toolbar_top.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_top)

        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet('QToolBar {spacing: 4px; margin-top: 15px;}')
        self.toolbar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.toolbar.setContentsMargins(0, 0, 0, 0)

        self.check_updates = QCheckBox()
        self.check_updates.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_updates.setText(self.i18n['updates'].capitalize())
        self.check_updates.stateChanged.connect(self._handle_updates_filter)
        self.check_updates.sizePolicy().setRetainSizeWhenHidden(True)
        self.comp_manager.register_component(CHECK_UPDATES, self.check_updates, self.toolbar.addWidget(self.check_updates))

        self.check_apps = QCheckBox()
        self.check_apps.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_apps.setText(self.i18n['manage_window.checkbox.only_apps'])
        self.check_apps.setChecked(True)
        self.check_apps.stateChanged.connect(self._handle_filter_only_apps)
        self.check_apps.sizePolicy().setRetainSizeWhenHidden(True)
        self.comp_manager.register_component(CHECK_APPS, self.check_apps, self.toolbar.addWidget(self.check_apps))

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
        self.combo_filter_type.sizePolicy().setRetainSizeWhenHidden(True)
        self.comp_manager.register_component(COMBO_TYPES, self.combo_filter_type, self.toolbar.addWidget(self.combo_filter_type))

        self.any_category_filter = 'any'
        self.combo_categories = QComboBox()
        self.combo_categories.setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_categories.setStyleSheet('QLineEdit { height: 2px; }')
        self.combo_categories.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_categories.setEditable(True)
        self.combo_categories.lineEdit().setReadOnly(True)
        self.combo_categories.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_categories.activated.connect(self._handle_category_filter)
        self.combo_categories.sizePolicy().setRetainSizeWhenHidden(True)
        self.combo_categories.addItem('--- {} ---'.format(self.i18n['category'].capitalize()), self.any_category_filter)
        self.comp_manager.register_component(COMBO_CATEGORIES, self.combo_categories, self.toolbar.addWidget(self.combo_categories))

        self.input_name = InputFilter(self.begin_apply_filters)
        self.input_name.setPlaceholderText(self.i18n['manage_window.name_filter.placeholder'] + '...')
        self.input_name.setToolTip(self.i18n['manage_window.name_filter.tooltip'])
        self.input_name.setStyleSheet("QLineEdit { color: grey; }")
        self.input_name.setFixedWidth(130)
        self.input_name.sizePolicy().setRetainSizeWhenHidden(True)
        self.comp_manager.register_component(INP_NAME, self.input_name, self.toolbar.addWidget(self.input_name))

        self.toolbar.addWidget(new_spacer())

        toolbar_bts = []

        if config['suggestions']['enabled']:
            bt_sugs = QPushButton()
            bt_sugs.setCursor(QCursor(Qt.PointingHandCursor))
            bt_sugs.setToolTip(self.i18n['manage_window.bt.suggestions.tooltip'])
            bt_sugs.setText(self.i18n['manage_window.bt.suggestions.text'].capitalize())
            bt_sugs.setIcon(QIcon(resource.get_path('img/suggestions.svg')))
            bt_sugs.setStyleSheet(toolbar_button_style())
            bt_sugs.clicked.connect(lambda: self._begin_load_suggestions(filter_installed=True))
            bt_sugs.sizePolicy().setRetainSizeWhenHidden(True)
            ref_bt_sugs = self.toolbar.addWidget(bt_sugs)
            toolbar_bts.append(bt_sugs)
            self.comp_manager.register_component(BT_SUGGESTIONS, bt_sugs, ref_bt_sugs)

        bt_inst = QPushButton()
        bt_inst.setCursor(QCursor(Qt.PointingHandCursor))
        bt_inst.setToolTip(self.i18n['manage_window.bt.installed.tooltip'])
        bt_inst.setIcon(QIcon(resource.get_path('img/disk.svg')))
        bt_inst.setText(self.i18n['manage_window.bt.installed.text'].capitalize())
        bt_inst.clicked.connect(self._begin_loading_installed)
        bt_inst.setStyleSheet(toolbar_button_style())
        bt_inst.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(bt_inst)
        self.comp_manager.register_component(BT_INSTALLED, bt_inst, self.toolbar.addWidget(bt_inst))

        bt_ref = QPushButton()
        bt_ref.setCursor(QCursor(Qt.PointingHandCursor))
        bt_ref.setToolTip(i18n['manage_window.bt.refresh.tooltip'])
        bt_ref.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        bt_ref.setText(self.i18n['manage_window.bt.refresh.text'])
        bt_ref.setStyleSheet(toolbar_button_style())
        bt_ref.clicked.connect(self.begin_refresh_packages)
        bt_ref.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(bt_ref)
        self.comp_manager.register_component(BT_REFRESH, bt_ref, self.toolbar.addWidget(bt_ref))

        self.bt_upgrade = QPushButton()
        self.bt_upgrade.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_upgrade.setToolTip(i18n['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setIcon(QIcon(resource.get_path('img/app_update.svg')))
        self.bt_upgrade.setText(i18n['manage_window.bt.upgrade.text'])
        self.bt_upgrade.setStyleSheet(toolbar_button_style(GREEN, 'white'))
        self.bt_upgrade.clicked.connect(self.upgrade_selected)
        self.bt_upgrade.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(self.bt_upgrade)
        self.comp_manager.register_component(BT_UPGRADE, self.bt_upgrade, self.toolbar.addWidget(self.bt_upgrade))

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

        self.table_container = QWidget()
        self.table_container.setContentsMargins(0, 0, 0, 0)
        self.table_container.setLayout(QVBoxLayout())
        self.table_container.layout().setContentsMargins(0, 0, 0, 0)

        self.table_apps = AppsTable(self, self.icon_cache, download_icons=bool(self.config['download']['icons']))
        self.table_apps.change_headers_policy()
        self.table_container.layout().addWidget(self.table_apps)

        self.layout.addWidget(self.table_container)

        toolbar_console = QToolBar()

        self.check_console = QCheckBox()
        self.check_console.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_console.setText(self.i18n['manage_window.checkbox.show_details'])
        self.check_console.stateChanged.connect(self._handle_console)
        self.comp_manager.register_component(CHECK_CONSOLE, self.check_console, toolbar_console.addWidget(self.check_console))

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
        self.label_substatus.setCursor(QCursor(Qt.WaitCursor))
        self.toolbar_substatus.addWidget(self.label_substatus)
        self.toolbar_substatus.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_substatus)
        self._change_label_substatus('')

        self.thread_update = self._bind_async_action(UpgradeSelected(self.manager, self.i18n), finished_call=self._finish_upgrade_selected)
        self.thread_refresh = self._bind_async_action(RefreshApps(self.manager), finished_call=self._finish_refresh_packages, only_finished=True)
        self.thread_uninstall = self._bind_async_action(UninstallPackage(self.manager, self.icon_cache, self.i18n), finished_call=self._finish_uninstall)
        self.thread_show_info = self._bind_async_action(ShowPackageInfo(self.manager), finished_call=self._finish_show_info)
        self.thread_show_history = self._bind_async_action(ShowPackageHistory(self.manager, self.i18n), finished_call=self._finish_show_history)
        self.thread_search = self._bind_async_action(SearchPackages(self.manager), finished_call=self._finish_search, only_finished=True)
        self.thread_downgrade = self._bind_async_action(DowngradePackage(self.manager, self.i18n), finished_call=self._finish_downgrade)
        self.thread_suggestions = self._bind_async_action(FindSuggestions(man=self.manager), finished_call=self._finish_load_suggestions, only_finished=True)
        self.thread_launch = self._bind_async_action(LaunchPackage(self.manager), finished_call=self._finish_launch_package, only_finished=False)
        self.thread_custom_action = self._bind_async_action(CustomAction(manager=self.manager, i18n=self.i18n), finished_call=self._finish_execute_custom_action)
        self.thread_screenshots = self._bind_async_action(ShowScreenshots(self.manager), finished_call=self._finish_show_screenshots)

        self.thread_apply_filters = ApplyFilters()
        self.thread_apply_filters.signal_finished.connect(self._finish_apply_filters)
        self.thread_apply_filters.signal_table.connect(self._update_table_and_upgrades)
        self.signal_table_update.connect(self.thread_apply_filters.stop_waiting)

        self.thread_install = InstallPackage(manager=self.manager, icon_cache=self.icon_cache, i18n=self.i18n)
        self._bind_async_action(self.thread_install, finished_call=self._finish_install)

        self.thread_animate_progress = AnimateProgress()
        self.thread_animate_progress.signal_change.connect(self._update_progress)

        self.thread_notify_pkgs_ready = NotifyPackagesReady()
        self.thread_notify_pkgs_ready.signal_changed.connect(self._update_package_data)
        self.thread_notify_pkgs_ready.signal_finished.connect(self._update_state_when_pkgs_ready)
        self.signal_stop_notifying.connect(self.thread_notify_pkgs_ready.stop_working)

        self.thread_ignore_updates = IgnorePackageUpdates(manager=self.manager)
        self._bind_async_action(self.thread_ignore_updates, finished_call=self.finish_ignore_updates)

        self.toolbar_bottom = QToolBar()
        self.toolbar_bottom.setIconSize(QSize(16, 16))
        self.toolbar_bottom.setStyleSheet('QToolBar { spacing: 3px }')

        self.toolbar_bottom.addWidget(new_spacer())

        self.progress_bar = QProgressBar()
        self.progress_bar.setCursor(QCursor(Qt.WaitCursor))
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
        self.comp_manager.register_component(BT_CUSTOM_ACTIONS, bt_custom_actions, self.toolbar_bottom.addWidget(bt_custom_actions))

        bt_settings = IconButton(QIcon(resource.get_path('img/settings.svg')),
                                 action=self.show_settings,
                                 i18n=self.i18n,
                                 tooltip=self.i18n['manage_window.bt_settings.tooltip'])
        self.comp_manager.register_component(BT_SETTINGS, bt_settings, self.toolbar_bottom.addWidget(bt_settings))

        bt_about = IconButton(QIcon(resource.get_path('img/info.svg')),
                              action=self._show_about,
                              i18n=self.i18n,
                              tooltip=self.i18n['manage_window.settings.about'])
        self.comp_manager.register_component(BT_ABOUT, bt_about, self.toolbar_bottom.addWidget(bt_about))

        self.layout.addWidget(self.toolbar_bottom)

        qt_utils.centralize(self)

        self.filter_only_apps = True
        self.type_filter = self.any_type_filter
        self.category_filter = self.any_category_filter
        self.filter_updates = False
        self._maximized = False
        self.progress_controll_enabled = True
        self.recent_uninstall = False
        self.types_changed = False

        self.dialog_about = None
        self.load_suggestions = bool(config['suggestions']['enabled'])
        self.suggestions_requested = False
        self.first_refresh = True

        self.thread_warnings = ListWarnings(man=manager, i18n=i18n)
        self.thread_warnings.signal_warnings.connect(self._show_warnings)
        self.settings_window = None
        self.search_performed = False

        self.thread_load_installed = NotifyInstalledLoaded()
        self.thread_load_installed.signal_loaded.connect(self._finish_loading_installed)
        self.setMinimumHeight(int(screen_size.height() * 0.5))
        self.setMinimumWidth(int(screen_size.width() * 0.6))
        self._register_groups()

    def _register_groups(self):
        filters = (CHECK_APPS, CHECK_UPDATES, COMBO_CATEGORIES, COMBO_TYPES, INP_NAME)
        self.comp_manager.register_group(GROUP_FILTERS, False, *filters)

        self.comp_manager.register_group(GROUP_VIEW_SEARCH, False,
                                         COMBO_CATEGORIES, COMBO_TYPES, INP_NAME,  # filters
                                         BT_INSTALLED, BT_SUGGESTIONS)  # buttons

        self.comp_manager.register_group(GROUP_VIEW_INSTALLED, False,
                                         BT_SUGGESTIONS, BT_REFRESH, BT_UPGRADE,  # buttons
                                         *filters)

        self.comp_manager.register_group(GROUP_UPPER_BAR, False,
                                         CHECK_APPS, CHECK_UPDATES, COMBO_CATEGORIES, COMBO_TYPES, INP_NAME,
                                         BT_INSTALLED, BT_SUGGESTIONS, BT_REFRESH, BT_UPGRADE)

        self.comp_manager.register_group(GROUP_LOWER_BTS, False, BT_ABOUT, BT_SETTINGS, BT_CUSTOM_ACTIONS)

    def update_custom_actions(self):
        self.custom_actions = self.manager.get_custom_actions()

    def _update_process_progress(self, val: int):
        if self.progress_controll_enabled:
            self.thread_animate_progress.set_progress(val)

    def _change_status(self, status: str = None):
        if status:
            self.label_status.setText(status + '...')
            self.label_status.setCursor(QCursor(Qt.WaitCursor))
        else:
            self.label_status.setText('')
            self.label_status.unsetCursor()

    def _set_table_enabled(self, enabled: bool):
        self.table_apps.setEnabled(enabled)
        if enabled:
            self.table_container.unsetCursor()
        else:
            self.table_container.setCursor(QCursor(Qt.WaitCursor))

    def begin_apply_filters(self):
        self.stop_notifying_package_states()
        self._begin_action(action_label=self.i18n['manage_window.status.filtering'],
                           action_id=ACTION_APPLY_FILTERS)
        self.comp_manager.disable_visible_from_groups(GROUP_UPPER_BAR, GROUP_LOWER_BTS)
        self.comp_manager.set_component_read_only(INP_NAME, True)

        self.thread_apply_filters.filters = self._gen_filters()
        self.thread_apply_filters.pkgs = self.pkgs_available
        self.thread_apply_filters.start()
        self.setFocus(Qt.NoFocusReason)

    def _finish_apply_filters(self):
        self._finish_action(ACTION_APPLY_FILTERS)
        self.update_bt_upgrade()

    def stop_notifying_package_states(self):
        if self.thread_notify_pkgs_ready.isRunning():
            self.signal_stop_notifying.emit()
            self.thread_notify_pkgs_ready.wait(1000)

    def _update_table_and_upgrades(self, pkgs_info: dict):
        self._update_table(pkgs_info=pkgs_info, signal=True)

        if self.pkgs:
            self._update_state_when_pkgs_ready()

            self.stop_notifying_package_states()
            self.thread_notify_pkgs_ready.pkgs = self.pkgs
            self.thread_notify_pkgs_ready.work = True
            self.thread_notify_pkgs_ready.start()

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
                                  confirmation_button=msg.get('confirmation_button', True),
                                  screen_size=self.screen_size)
        res = diag.is_confirmed()
        self.thread_animate_progress.animate()
        self.signal_user_res.emit(res)

    def _pause_and_ask_root_password(self):
        self.thread_animate_progress.pause()
        password, valid = root.ask_root_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)

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
        self.inp_search.setText('')
        self.input_name.setText('')
        self._begin_action(self.i18n['manage_window.status.installed'])
        self._handle_console_option(False)
        self.comp_manager.set_components_visible(False)
        self.suggestions_requested = False
        self.search_performed = False
        self.thread_load_installed.start()

    def _finish_loading_installed(self):
        self._finish_action()
        self.comp_manager.set_group_visible(GROUP_VIEW_INSTALLED, True)
        self.update_pkgs(new_pkgs=None, as_installed=True)
        self._hide_filters_no_packages()
        self._update_bts_installed_and_suggestions()
        self._set_lower_buttons_visible(True)
        self._reorganize()

    def _update_bts_installed_and_suggestions(self):
        available_types = len(self.manager.get_managed_types())
        self.comp_manager.set_component_visible(BT_INSTALLED, available_types > 0 and any([self.suggestions_requested, self.search_performed]))
        self.comp_manager.set_component_visible(BT_SUGGESTIONS, available_types > 0)

    def _hide_filters_no_packages(self):
        if not self.pkgs:
            self.comp_manager.set_group_visible(GROUP_FILTERS, False)

    def _show_about(self):
        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.config)

        self.dialog_about.show()

    def _handle_updates_filter(self, status: int):
        self.filter_updates = status == 2
        self.begin_apply_filters()

    def _handle_filter_only_apps(self, status: int):
        self.filter_only_apps = status == 2
        self.begin_apply_filters()

    def _handle_type_filter(self, idx: int):
        self.type_filter = self.combo_filter_type.itemData(idx)
        self.combo_filter_type.adjustSize()
        self.begin_apply_filters()

    def _handle_category_filter(self, idx: int):
        self.category_filter = self.combo_categories.itemData(idx)
        self.begin_apply_filters()

    def _update_state_when_pkgs_ready(self):
        if self.progress_bar.isVisible():
            return

        self._reload_categories()
        self._reorganize()

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
                    if c:
                        cat = c.strip().lower()
                        if cat:
                            categories.add(cat)

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

        self.comp_manager.set_component_visible(CHECK_CONSOLE, enable)
        self.check_console.setChecked(False)
        self.textarea_output.hide()

    def begin_refresh_packages(self, pkg_types: Set[Type[SoftwarePackage]] = None):
        self.inp_search.clear()

        self._begin_action(self.i18n['manage_window.status.refreshing'])
        self.comp_manager.set_components_visible(False)
        self._handle_console_option(False)

        self.suggestions_requested = False
        self.search_performed = False

        self.thread_refresh.pkg_types = pkg_types
        self.thread_refresh.start()

    def _finish_refresh_packages(self, res: dict, as_installed: bool = True):
        self._finish_action()
        self._set_lower_buttons_visible(True)
        self.comp_manager.set_component_visible(SEARCH_BAR, True)

        if self.search_performed or self.suggestions_requested:
            self.comp_manager.set_group_visible(GROUP_VIEW_SEARCH, True)
        else:
            self.comp_manager.set_group_visible(GROUP_VIEW_INSTALLED, True)

        if self.update_pkgs(res['installed'], as_installed=as_installed, types=res['types']):
            self._hide_filters_no_packages()
            self._update_bts_installed_and_suggestions()
            self._reorganize()

        self.load_suggestions = False
        self.types_changed = False

    def _begin_load_suggestions(self, filter_installed: bool):
        self.inp_search.clear()
        self._begin_action(self.i18n['manage_window.status.suggestions'])
        self._handle_console_option(False)
        self.comp_manager.set_components_visible(False)
        self.suggestions_requested = True
        self.thread_suggestions.filter_installed = filter_installed
        self.thread_suggestions.start()

    def _finish_load_suggestions(self, res: dict):
        self._finish_search(res)

    def begin_uninstall(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password('uninstall', pkg)

        if not proceed:
            return

        self._begin_action(action_label='{} {}'.format(self.i18n['manage_window.status.uninstalling'], pkg.model.name),
                           action_id=ACTION_UNINSTALL)
        self.comp_manager.set_groups_visible(False, GROUP_UPPER_BAR, GROUP_LOWER_BTS)
        self._handle_console_option(True)

        self.thread_uninstall.pkg = pkg
        self.thread_uninstall.root_pwd = pwd
        self.thread_uninstall.start()

    def _finish_uninstall(self, res: dict):
        self._finish_action(action_id=ACTION_UNINSTALL)

        if res['success']:
            src_pkg = res['pkg']
            if self._can_notify_user():
                util.notify_user('{} ({}) {}'.format(src_pkg.model.name, src_pkg.model.get_type(), self.i18n['uninstalled']))

            if res['removed']:
                for list_idx, pkg_list in enumerate((self.pkgs_available, self.pkgs, self.pkgs_installed)):
                    if pkg_list:
                        removed_idxs = []
                        for pkgv_idx, pkgv in enumerate(pkg_list):
                            if len(removed_idxs) == len(res['removed']):
                                break

                            for model in res['removed']:
                                if pkgv.model == model:
                                    if list_idx == 0:  # updates the model
                                        pkgv.update_model(model)

                                    if not self.search_performed or list_idx == 2:  # always from the installed packages
                                        removed_idxs.append(pkgv_idx)

                                    if self.search_performed and list_idx == 1:  # only for displayed
                                        self.table_apps.update_package(pkgv, change_update_col=True)

                                    break  # as the model has been found, stops the loop

                        if removed_idxs:
                            # updating the list
                            removed_idxs.sort()
                            for decrement, pkg_idx in enumerate(removed_idxs):
                                del pkg_list[pkg_idx - decrement]

                            if list_idx == 1:  # updates the rows if the current list reprents the displayed packages:
                                for decrement, idx in enumerate(removed_idxs):
                                    self.table_apps.removeRow(idx - decrement)

                                self._update_table_indexes()

                        self.update_bt_upgrade()

            self.update_custom_actions()
            self._show_console_checkbox_if_output()
            notify_tray()
        else:
            self._show_console_errors()

            if self._can_notify_user():
                util.notify_user('{}: {}'.format(res['pkg'].model.name, self.i18n['notification.uninstall.failed']))

    def _update_table_indexes(self):
        if self.pkgs:
            for new_idx, pkgv in enumerate(self.pkgs):  # updating the package indexes
                pkgv.table_index = new_idx

    def begin_launch_package(self, pkg: PackageView):
        self._begin_action(action_label=self.i18n['manage_window.status.running_app'].format(pkg.model.name),
                           action_id=ACTION_LAUNCH)
        self.comp_manager.disable_visible()
        self.thread_launch.pkg = pkg
        self.thread_launch.start()

    def _finish_launch_package(self, success: bool):
        self._finish_action(action_id=ACTION_LAUNCH)

    def _can_notify_user(self):
        return bool(self.config['system']['notifications']) and (self.isHidden() or self.isMinimized())

    def _change_label_status(self, status: str):
        self.label_status.setText(status)

    def _change_label_substatus(self, substatus: str):
        self.label_substatus.setText('<p>{}</p>'.format(substatus))
        if not substatus:
            self.toolbar_substatus.hide()
        elif not self.toolbar_substatus.isVisible() and self.progress_bar.isVisible():
            self.toolbar_substatus.show()

    def _reorganize(self):
        if not self._maximized:
            self.table_apps.change_headers_policy(QHeaderView.Stretch)
            self.table_apps.change_headers_policy()
            self._resize(accept_lower_width=len(self.pkgs) > 0)

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

        if not any([self.suggestions_requested, self.search_performed]) and (not pkgs_info or pkgs_info['not_installed'] == 0):
            for pkg in (pkgs_info['pkgs_displayed'] if pkgs_info else self.pkgs):
                if not pkg.model.is_update_ignored() and pkg.update_checked:
                    show_bt_upgrade = True
                    break

        self.comp_manager.set_component_visible(BT_UPGRADE, show_bt_upgrade)

        if show_bt_upgrade:
            self._reorganize()

    def change_update_state(self, pkgs_info: dict, trigger_filters: bool = True, keep_selected: bool = False):
        self.update_bt_upgrade(pkgs_info)

        if pkgs_info['updates'] > 0:
            if pkgs_info['not_installed'] == 0:
                if not self.comp_manager.is_visible(CHECK_UPDATES):
                    self.comp_manager.set_component_visible(CHECK_UPDATES, True)

                if not self.filter_updates and not keep_selected:
                    self._change_checkbox(self.check_updates, True, 'filter_updates', trigger_filters)

            if pkgs_info['napp_updates'] > 0 and self.filter_only_apps and not keep_selected:
                self._change_checkbox(self.check_apps, False, 'filter_only_apps', trigger_filters)
        else:
            if not keep_selected:
                self._change_checkbox(self.check_updates, False, 'filter_updates', trigger_filters)

            self.comp_manager.set_component_visible(CHECK_UPDATES, False)

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
            'name': self.input_name.get_text().lower() if self.input_name.get_text() else None,
            'display_limit': None if self.filter_updates else self.display_limit
        }

    def update_pkgs(self, new_pkgs: List[SoftwarePackage], as_installed: bool, types: Set[type] = None, ignore_updates: bool = False, keep_filters: bool = False) -> bool:
        self.input_name.setText('')
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
                if as_installed:
                    self.pkgs_installed = pkgs_info['pkgs']

                self._begin_load_suggestions(filter_installed=False)
                self.load_suggestions = False
                return False
            else:
                if not keep_filters:
                    self._change_checkbox(self.check_apps, False, 'filter_only_apps', trigger=False)
                    self.check_apps.setCheckable(False)
        else:
            if not keep_filters:
                self.check_apps.setCheckable(True)
                self._change_checkbox(self.check_apps, True, 'filter_only_apps', trigger=False)

        self.change_update_state(pkgs_info=pkgs_info, trigger_filters=False, keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._update_categories(pkgs_info['categories'], keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._update_type_filters(pkgs_info['available_types'], keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))
        self._apply_filters(pkgs_info, ignore_updates=ignore_updates)
        self.change_update_state(pkgs_info=pkgs_info, trigger_filters=False, keep_selected=keep_filters and bool(pkgs_info['pkgs_displayed']))

        self.pkgs_available = pkgs_info['pkgs']

        if as_installed:
            self.pkgs_installed = pkgs_info['pkgs']

        self.pkgs = pkgs_info['pkgs_displayed']
        self._update_table(pkgs_info=pkgs_info)

        if new_pkgs:
            self.stop_notifying_package_states()
            self.thread_notify_pkgs_ready.work = True
            self.thread_notify_pkgs_ready.pkgs = self.pkgs
            self.thread_notify_pkgs_ready.start()

        self._resize(accept_lower_width=bool(self.pkgs_installed))

        if self.first_refresh:
            qt_utils.centralize(self)
            self.first_refresh = False

        return True

    def _apply_filters(self, pkgs_info: dict, ignore_updates: bool):
        pkgs_info['pkgs_displayed'] = []
        filters = self._gen_filters(ignore_updates=ignore_updates)
        for pkgv in pkgs_info['pkgs']:
            commons.apply_filters(pkgv, filters, pkgs_info)

    def _clean_combo_types(self):
        if self.combo_filter_type.count() > 1:
            for _ in range(self.combo_filter_type.count() - 1):
                self.combo_filter_type.removeItem(1)

    def _update_type_filters(self, available_types: dict = None, keep_selected: bool = False):
        if available_types is None:
            self.comp_manager.set_component_visible(COMBO_TYPES, self.combo_filter_type.count() > 2)
        else:
            keeping_selected = keep_selected and available_types and self.type_filter in available_types

            if not keeping_selected:
                self.type_filter = self.any_type_filter
                if not available_types:
                    self._clean_combo_types()

            if available_types:
                self._clean_combo_types()

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
                self.comp_manager.set_component_visible(COMBO_TYPES, len(available_types) > 1)
            else:
                self.comp_manager.set_component_visible(COMBO_TYPES, False)

    def _update_categories(self, categories: Set[str] = None, keep_selected: bool = False):
        if categories is None:
            self.comp_manager.set_component_visible(COMBO_CATEGORIES, self.combo_categories.count() > 1)
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
                    self.__add_category(c)

                    if keeping_selected and c == self.category_filter:
                        selected_cat = idx + 1

                self.combo_categories.blockSignals(True)
                self.combo_categories.setCurrentIndex(selected_cat if selected_cat > -1 else 0)
                self.combo_categories.blockSignals(False)
                self.comp_manager.set_component_visible(COMBO_CATEGORIES, True)

            else:
                self.comp_manager.set_component_visible(COMBO_CATEGORIES, False)

    def __add_category(self, category: str):
        i18n_cat = self.i18n.get('category.{}'.format(category), self.i18n.get(category, category))
        self.combo_categories.addItem(i18n_cat.capitalize(), category)

    def _get_current_categories(self) -> Set[str]:
        if self.combo_categories.count() > 1:
            return {self.combo_categories.itemData(idx) for idx in range(self.combo_categories.count()) if idx > 0}

    def _resize(self, accept_lower_width: bool = True):
        table_width = self.table_apps.get_width()
        toolbar_width = self.toolbar.sizeHint().width()
        topbar_width = self.toolbar_top.sizeHint().width()

        new_width = max(table_width, toolbar_width, topbar_width)
        new_width *= 1.05  # this extra size is not because of the toolbar button, but the table upgrade buttons

        if (self.pkgs and accept_lower_width) or new_width > self.width():
            self.resize(new_width, self.height())

    def set_progress_controll(self, enabled: bool):
        self.progress_controll_enabled = enabled

    def upgrade_selected(self):
        if dialog.ask_confirmation(title=self.i18n['manage_window.upgrade_all.popup.title'],
                                   body=self.i18n['manage_window.upgrade_all.popup.body'],
                                   i18n=self.i18n,
                                   widgets=[UpdateToggleButton(pkg=None,
                                                               root=self,
                                                               i18n=self.i18n,
                                                               clickable=False)]):

            self._begin_action(action_label=self.i18n['manage_window.status.upgrading'],
                               action_id=ACTION_UPGRADE)
            self.comp_manager.set_components_visible(False)
            self._handle_console_option(True)
            self.thread_update.pkgs = self.pkgs
            self.thread_update.start()

    def _finish_upgrade_selected(self, res: dict):
        self._finish_action()

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
            self.comp_manager.remove_saved_state(ACTION_UPGRADE)
            self.begin_refresh_packages(pkg_types=res['types'])
            self._show_console_checkbox_if_output()

            if self._can_notify_user():
                util.notify_user('{} {}'.format(res['updated'], self.i18n['notification.update_selected.success']))

            notify_tray()
        else:
            self.comp_manager.restore_state(ACTION_UPGRADE)
            self._show_console_errors()

            if self._can_notify_user():
                util.notify_user(self.i18n['notification.update_selected.failed'])

        self.update_custom_actions()

    def _show_console_errors(self):
        if self.textarea_output.toPlainText():
            self.check_console.setChecked(True)
        else:
            self._handle_console_option(False)
            self.comp_manager.set_component_visible(CHECK_CONSOLE, False)

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str, action_id: int = None):
        self.thread_animate_progress.stop = False
        self.thread_animate_progress.start()
        self.ref_progress_bar.setVisible(True)

        if action_id is not None:
            self.comp_manager.save_states(action_id, only_visible=True)

        self._set_table_enabled(False)
        self.comp_manager.set_component_visible(SEARCH_BAR, False)
        self._change_status(action_label)

    def _set_lower_buttons_visible(self, visible: bool):
        self.comp_manager.set_group_visible(GROUP_LOWER_BTS, visible)

        if visible:
            self.comp_manager.set_component_visible(BT_CUSTOM_ACTIONS, bool(self.custom_actions))

    def _finish_action(self, action_id: int = None):
        self.thread_animate_progress.stop = True
        self.thread_animate_progress.wait(msecs=1000)

        self.ref_progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        if action_id is not None:
            self.comp_manager.restore_state(action_id)

        self.comp_manager.set_component_visible(SEARCH_BAR, True)
        self._change_status()
        self._change_label_substatus('')
        self._set_table_enabled(True)
        self.progress_controll_enabled = True

    def begin_downgrade(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password('downgrade', pkg)

        if not proceed:
            return

        self._begin_action(action_label='{} {}'.format(self.i18n['manage_window.status.downgrading'], pkg.model.name),
                           action_id=ACTION_DOWNGRADE)
        self.comp_manager.set_components_visible(False)
        self._handle_console_option(True)

        self.thread_downgrade.pkg = pkg
        self.thread_downgrade.root_pwd = pwd
        self.thread_downgrade.start()

    def _finish_downgrade(self, res: dict):
        self._finish_action()

        if res['success']:
            self.comp_manager.remove_saved_state(ACTION_DOWNGRADE)

            if self._can_notify_user():
                util.notify_user('{} {}'.format(res['app'], self.i18n['downgraded']))

            self.begin_refresh_packages(pkg_types={res['app'].model.__class__} if len(self.pkgs) > 1 else None)
            self._show_console_checkbox_if_output()
            self.update_custom_actions()
            notify_tray()
        else:
            self.comp_manager.restore_state(ACTION_DOWNGRADE)
            self._show_console_errors()

            if self._can_notify_user():
                util.notify_user(self.i18n['notification.downgrade.failed'])

    def begin_show_info(self, pkg: dict):
        self._begin_action(self.i18n['manage_window.status.info'], action_id=ACTION_INFO)
        self.comp_manager.disable_visible()

        self.thread_show_info.pkg = pkg
        self.thread_show_info.start()

    def _finish_show_info(self, pkg_info: dict):
        self._finish_action(action_id=ACTION_INFO)
        dialog_info = InfoDialog(pkg_info=pkg_info, icon_cache=self.icon_cache,
                                 i18n=self.i18n, screen_size=self.screen_size)
        dialog_info.exec_()

    def begin_show_screenshots(self, pkg: PackageView):
        self._begin_action(action_label=self.i18n['manage_window.status.screenshots'].format(bold(pkg.model.name)),
                           action_id=ACTION_SCREENSHOTS)
        self.comp_manager.disable_visible()

        self.thread_screenshots.pkg = pkg
        self.thread_screenshots.start()

    def _finish_show_screenshots(self, res: dict):
        self._finish_action(ACTION_SCREENSHOTS)

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

    def begin_show_history(self, pkg: PackageView):
        self._begin_action(self.i18n['manage_window.status.history'], action_id=ACTION_HISTORY)
        self.comp_manager.disable_visible()

        self.thread_show_history.pkg = pkg
        self.thread_show_history.start()

    def _finish_show_history(self, res: dict):
        self._finish_action(ACTION_HISTORY)

        if res.get('error'):
            self._handle_console_option(True)
            self.textarea_output.appendPlainText(res['error'])
            self.check_console.setChecked(True)
        elif not res['history'].history:
            dialog.show_message(title=self.i18n['action.history.no_history.title'],
                                body=self.i18n['action.history.no_history.body'].format(bold(res['history'].pkg.name)),
                                type_=MessageType.WARNING)
        else:
            dialog_history = HistoryDialog(res['history'], self.icon_cache, self.i18n)
            dialog_history.exec_()

    def _begin_search(self, word, action_id: int = None):
        self.filter_updates = False
        self._begin_action('{} {}'.format(self.i18n['manage_window.status.searching'], word if word else ''), action_id=action_id)

    def search(self):
        word = self.inp_search.text().strip()
        if word:
            self._handle_console(False)
            self._begin_search(word, action_id=ACTION_SEARCH)
            self.comp_manager.set_components_visible(False)
            self.thread_search.word = word
            self.thread_search.start()

    def _finish_search(self, res: dict):
        self._finish_action()
        self.search_performed = True

        if not res['error']:
            self.comp_manager.set_group_visible(GROUP_VIEW_SEARCH, True)
            self.update_pkgs(res['pkgs_found'], as_installed=False, ignore_updates=True)
            self._set_lower_buttons_visible(True)
            self._update_bts_installed_and_suggestions()
            self._hide_filters_no_packages()
            self._reorganize()
        else:
            self.comp_manager.restore_state(ACTION_SEARCH)
            dialog.show_message(title=self.i18n['warning'].capitalize(), body=self.i18n[res['error']], type_=MessageType.WARNING)

    def _ask_root_password(self, action: str, pkg: PackageView) -> Tuple[str, bool]:
        pwd = None
        requires_root = self.manager.requires_root(action, pkg.model)

        if not user.is_root() and requires_root:
            pwd, ok = ask_root_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)
            if not ok:
                return pwd, False

        return pwd, True

    def install(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password('install', pkg)

        if not proceed:
            return

        self._begin_action('{} {}'.format(self.i18n['manage_window.status.installing'], pkg.model.name), action_id=ACTION_INSTALL)
        self.comp_manager.set_groups_visible(False, GROUP_UPPER_BAR, GROUP_LOWER_BTS)
        self._handle_console_option(True)

        self.thread_install.pkg = pkg
        self.thread_install.root_pwd = pwd
        self.thread_install.start()

    def _finish_install(self, res: dict):
        self._finish_action(action_id=ACTION_INSTALL)

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
            if self._can_notify_user():
                util.notify_user(msg='{} ({}) {}'.format(res['pkg'].model.name, res['pkg'].model.get_type(), self.i18n['installed']))

            models_updated = []

            for key in ('installed', 'removed'):
                if res.get(key):
                    models_updated.extend(res[key])

            if models_updated:
                installed_available_idxs = []
                for idx, available in enumerate(self.pkgs_available):
                    for pidx, model in enumerate(models_updated):
                        if available.model == model:
                            available.update_model(model)
                            if model.installed:
                                installed_available_idxs.append((idx, pidx, available))

                # re-indexing all installed so they always will be be displayed when no filters are applied
                if installed_available_idxs:
                    # removing from available
                    installed_available_idxs.sort(key=operator.itemgetter(0))
                    for decrement, data in enumerate(installed_available_idxs):
                        del self.pkgs_available[data[0] - decrement]

                    # re-inserting into the available
                    installed_available_idxs.sort(key=operator.itemgetter(1))
                    for new_idx, data in enumerate(installed_available_idxs):
                        self.pkgs_available.insert(new_idx, data[2])

                # updating the respective table rows:
                for displayed in self.pkgs:
                    for model in models_updated:
                        if displayed.model == model:
                            self.table_apps.update_package(displayed, change_update_col=True)

                self.update_bt_upgrade()

            # updating installed packages
            if res['removed'] and self.pkgs_installed:
                to_remove = []
                for idx, installed in enumerate(self.pkgs_installed):
                    for removed in res['removed']:
                        if installed.model == removed:
                            to_remove.append(idx)

                if to_remove:
                    to_remove.sort()

                    for decrement, idx in enumerate(to_remove):
                        del self.pkgs_installed[idx - decrement]

            if res['installed']:
                for idx, model in enumerate(res['installed']):
                    self.pkgs_installed.insert(idx, PackageView(model, self.i18n))

            self.update_custom_actions()
        else:
            self._show_console_errors()
            if self._can_notify_user():
                util.notify_user('{}: {}'.format(res['pkg'].model.name, self.i18n['notification.install.failed']))

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def begin_execute_custom_action(self, pkg: PackageView, action: CustomSoftwareAction):
        if pkg is None and not dialog.ask_confirmation(title=self.i18n['confirmation'].capitalize(),
                                                       body=self.i18n['custom_action.proceed_with'].capitalize().format('"{}"'.format(self.i18n[action.i18n_label_key])),
                                                       icon=QIcon(action.icon_path) if action.icon_path else QIcon(resource.get_path('img/logo.svg')),
                                                       i18n=self.i18n):
            return False

        pwd = None

        if not user.is_root() and action.requires_root:
            pwd, ok = ask_root_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)

            if not ok:
                return

        self._begin_action(action_label='{}{}'.format(self.i18n[action.i18n_status_key], ' {}'.format(pkg.model.name) if pkg else ''),
                           action_id=ACTION_CUSTOM_ACTION)
        self.comp_manager.set_components_visible(False)
        self._handle_console_option(True)

        self.thread_custom_action.pkg = pkg
        self.thread_custom_action.root_pwd = pwd
        self.thread_custom_action.custom_action = action
        self.thread_custom_action.start()

    def _finish_execute_custom_action(self, res: dict):
        self._finish_action()

        if res['success']:
            if res['action'].refresh:
                self.comp_manager.remove_saved_state(ACTION_CUSTOM_ACTION)
                self.begin_refresh_packages(pkg_types={res['pkg'].model.__class__} if res['pkg'] else None)
            else:
                self.comp_manager.restore_state(ACTION_CUSTOM_ACTION)

            self._show_console_checkbox_if_output()
        else:
            self.comp_manager.restore_state(ACTION_CUSTOM_ACTION)
            self._show_console_errors()

    def _show_console_checkbox_if_output(self):
        if self.textarea_output.toPlainText():
            self.comp_manager.set_component_visible(CHECK_CONSOLE, True)
        else:
            self.comp_manager.set_component_visible(CHECK_CONSOLE, False)

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
        custom_action = QAction(self.i18n[action.i18n_label_key])

        if action.icon_path:
            try:
                if action.icon_path.startswith('/'):
                    icon = QIcon(action.icon_path)
                else:
                    icon = QIcon.fromTheme(action.icon_path)

                custom_action.setIcon(icon)

            except:
                pass

        custom_action.triggered.connect(lambda: self.begin_execute_custom_action(None, action))
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

    def begin_ignore_updates(self, pkg: PackageView):
        status_key = 'ignore_updates' if not pkg.model.is_update_ignored() else 'ignore_updates_reverse'
        self._begin_action(action_label=self.i18n['manage_window.status.{}'.format(status_key)].format(pkg.model.name),
                           action_id=ACTION_IGNORE_UPDATES)
        self.comp_manager.disable_visible()
        self.thread_ignore_updates.pkg = pkg
        self.thread_ignore_updates.start()

    def finish_ignore_updates(self, res: dict):
        self._finish_action(action_id=ACTION_IGNORE_UPDATES)

        if res['success']:
            hide_package = commons.is_package_hidden(res['pkg'], self._gen_filters())

            if hide_package:
                idx_to_remove = None
                for pkg in self.pkgs:
                    if pkg == res['pkg']:
                        idx_to_remove = pkg.table_index
                        break

                if idx_to_remove is not None:
                    del self.pkgs[idx_to_remove]
                    self.table_apps.removeRow(idx_to_remove)
                    self._update_table_indexes()
                    self.update_bt_upgrade()
            else:
                for pkg in self.pkgs:
                    if pkg == res['pkg']:
                        pkg.update_model(res['pkg'].model)
                        self.table_apps.update_package(pkg, change_update_col=not any([self.search_performed, self.suggestions_requested]))
                        self.update_bt_upgrade()
                        break

            for pkg_list in (self.pkgs_available, self.pkgs_installed):
                if pkg_list:
                    for pkg in pkg_list:
                        if pkg == res['pkg']:
                            pkg.update_model(res['pkg'].model)
                            break

            self._add_pkg_categories(res['pkg'])

            dialog.show_message(title=self.i18n['success'].capitalize(),
                                body=self.i18n['action.{}.success'.format(res['action'])].format(bold(res['pkg'].model.name)),
                                type_=MessageType.INFO)
        else:
            dialog.show_message(title=self.i18n['fail'].capitalize(),
                                body=self.i18n['action.{}.fail'.format(res['action'])].format(bold(res['pkg'].model.name)),
                                type_=MessageType.ERROR)

    def _add_pkg_categories(self, pkg: PackageView):
        if pkg.model.categories:
            pkg_categories = {c.strip().lower() for c in pkg.model.categories if c and c.strip()}

            if pkg_categories:
                current_categories = self._get_current_categories()

                if current_categories:
                    pkg_categories = {c.strip().lower() for c in pkg.model.categories if c}

                    if pkg_categories:
                        categories_to_add = {c for c in pkg_categories if c and c not in current_categories}

                        if categories_to_add:
                            for cat in categories_to_add:
                                self.__add_category(cat)
                else:
                    self._update_categories(pkg_categories)
