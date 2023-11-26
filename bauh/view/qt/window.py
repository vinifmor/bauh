import logging
import operator
import os.path
import time
from pathlib import Path
from typing import List, Type, Set, Tuple, Optional, Dict, Any

from PyQt5.QtCore import QEvent, Qt, pyqtSignal, QRect
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent, QCursor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHeaderView, QToolBar, \
    QLabel, QPlainTextEdit, QProgressBar, QPushButton, QComboBox, QApplication, QListView, QSizePolicy, \
    QMenu, QHBoxLayout

from bauh.api import user
from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SoftwareAction
from bauh.api.abstract.model import SoftwarePackage
from bauh.api.abstract.view import MessageType
from bauh.api.http import HttpClient
from bauh.api.paths import LOGS_DIR
from bauh.commons.html import bold
from bauh.context import set_theme
from bauh.stylesheet import read_all_themes_metadata, ThemeMetadata
from bauh.view.core.config import CoreConfigManager
from bauh.view.core.tray_client import notify_tray
from bauh.view.qt import dialog, commons, qt_utils
from bauh.view.qt.about import AboutDialog
from bauh.view.qt.apps_table import PackagesTable, UpgradeToggleButton
from bauh.view.qt.commons import sum_updates_displayed
from bauh.view.qt.components import new_spacer, IconButton, QtComponentsManager, to_widget, QSearchBar, \
    QCustomMenuAction, QCustomToolbar
from bauh.view.qt.dialog import ConfirmationDialog
from bauh.view.qt.history import HistoryDialog
from bauh.view.qt.info import InfoDialog
from bauh.view.qt.qt_utils import get_current_screen_geometry
from bauh.view.qt.root import RootDialog
from bauh.view.qt.screenshots import ScreenshotsDialog
from bauh.view.qt.settings import SettingsWindow
from bauh.view.qt.thread import UpgradeSelected, RefreshApps, UninstallPackage, DowngradePackage, ShowPackageInfo, \
    ShowPackageHistory, SearchPackages, InstallPackage, AnimateProgress, NotifyPackagesReady, FindSuggestions, \
    ListWarnings, \
    AsyncAction, LaunchPackage, ApplyFilters, CustomSoftwareAction, ShowScreenshots, CustomAction, \
    NotifyInstalledLoaded, \
    IgnorePackageUpdates, SaveTheme, StartAsyncAction
from bauh.view.qt.view_model import PackageView, PackageViewStatus
from bauh.view.util import util, resource
from bauh.view.util.translation import I18n

DARK_ORANGE = '#FF4500'


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
CHECK_INSTALLED = 6
CHECK_UPDATES = 7
CHECK_APPS = 8
COMBO_TYPES = 9
COMBO_CATEGORIES = 10
INP_NAME = 11
CHECK_DETAILS = 12
BT_SETTINGS = 13
BT_CUSTOM_ACTIONS = 14
BT_ABOUT = 15
BT_THEMES = 16

# component groups ids
GROUP_FILTERS = 1
GROUP_VIEW_INSTALLED = 2
GROUP_VIEW_SEARCH = 3
GROUP_UPPER_BAR = 4
GROUP_LOWER_BTS = 5


class ManageWindow(QWidget):
    signal_user_res = pyqtSignal(bool)
    signal_root_password = pyqtSignal(bool, str)
    signal_table_update = pyqtSignal()
    signal_stop_notifying = pyqtSignal()

    def __init__(self, i18n: I18n, icon_cache: MemoryCache, manager: SoftwareManager, config: dict,
                 context: ApplicationContext, http_client: HttpClient, logger: logging.Logger, icon: QIcon,
                 force_suggestions: bool = False):
        super(ManageWindow, self).__init__()
        self.setObjectName('manage_window')
        self.comp_manager = QtComponentsManager()
        self.i18n = i18n
        self.logger = logger
        self.manager = manager
        self.working = False  # restrict the number of threaded actions
        self.installed_loaded = False  # used to control the state when the interface is set to not load the apps on startup
        self.pkgs = []  # packages current loaded in the table
        self.pkgs_available = []  # all packages loaded in memory
        self.pkgs_installed = []  # cached installed packages
        self.pkg_idx: Optional[Dict[str, Any]] = None  # all packages available indexed by the available filters
        self.display_limit = config['ui']['table']['max_displayed']
        self.icon_cache = icon_cache
        self.config = config
        self.context = context
        self.http_client = http_client

        self.icon_app = icon
        self.setWindowIcon(self.icon_app)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.toolbar_status = QToolBar()
        self.toolbar_status.setObjectName('toolbar_status')
        self.toolbar_status.addWidget(new_spacer())

        self.label_status = QLabel()
        self.label_status.setObjectName('label_status')
        self.label_status.setText('')
        self.toolbar_status.addWidget(self.label_status)

        self.search_bar = QSearchBar(search_callback=self.search)
        self.search_bar.set_placeholder(i18n['window_manage.search_bar.placeholder'] + "...")
        self.search_bar.set_tooltip(i18n['window_manage.search_bar.tooltip'])
        self.search_bar.set_button_tooltip(i18n['window_manage.search_bar.button_tooltip'])
        self.comp_manager.register_component(SEARCH_BAR, self.search_bar, self.toolbar_status.addWidget(self.search_bar))

        self.toolbar_status.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_status)

        self.toolbar_filters = QWidget()
        self.toolbar_filters.setObjectName('table_filters')
        self.toolbar_filters.setLayout(QHBoxLayout())
        self.toolbar_filters.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.toolbar_filters.setContentsMargins(0, 0, 0, 0)

        self.check_updates = QCheckBox()
        self.check_updates.setObjectName('check_updates')
        self.check_updates.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_updates.setText(self.i18n['updates'].capitalize())
        self.check_updates.stateChanged.connect(self._handle_updates_filter)
        self.check_updates.sizePolicy().setRetainSizeWhenHidden(True)
        self.toolbar_filters.layout().addWidget(self.check_updates)
        self.comp_manager.register_component(CHECK_UPDATES, self.check_updates)

        self.check_installed = QCheckBox()
        self.check_installed.setObjectName('check_installed')
        self.check_installed.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_installed.setText(self.i18n['manage_window.checkbox.only_installed'])
        self.check_installed.setChecked(False)
        self.check_installed.stateChanged.connect(self._handle_filter_only_installed)
        self.check_installed.sizePolicy().setRetainSizeWhenHidden(True)
        self.toolbar_filters.layout().addWidget(self.check_installed)
        self.comp_manager.register_component(CHECK_INSTALLED, self.check_installed)

        self.check_apps = QCheckBox()
        self.check_apps.setObjectName('check_apps')
        self.check_apps.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_apps.setText(self.i18n['manage_window.checkbox.only_apps'])
        self.check_apps.setChecked(True)
        self.check_apps.stateChanged.connect(self._handle_filter_only_apps)
        self.check_apps.sizePolicy().setRetainSizeWhenHidden(True)
        self.toolbar_filters.layout().addWidget(self.check_apps)
        self.comp_manager.register_component(CHECK_APPS, self.check_apps)

        self.any_type_filter = 'any'
        self.cache_type_filter_icons = {}
        self.combo_filter_type = QComboBox()
        self.combo_filter_type.setObjectName('combo_types')
        self.combo_filter_type.setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_filter_type.setView(QListView())
        self.combo_filter_type.view().setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_filter_type.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_filter_type.setEditable(True)
        self.combo_filter_type.lineEdit().setReadOnly(True)
        self.combo_filter_type.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_filter_type.activated.connect(self._handle_type_filter)
        self.combo_filter_type.addItem('--- {} ---'.format(self.i18n['type'].capitalize()), self.any_type_filter)
        self.combo_filter_type.sizePolicy().setRetainSizeWhenHidden(True)
        self.toolbar_filters.layout().addWidget(self.combo_filter_type)
        self.comp_manager.register_component(COMBO_TYPES, self.combo_filter_type)

        self.any_category_filter = 'any'
        self.combo_categories = QComboBox()
        self.combo_categories.setObjectName('combo_categories')
        self.combo_categories.setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_categories.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_categories.view().setCursor(QCursor(Qt.PointingHandCursor))
        self.combo_categories.setEditable(True)
        self.combo_categories.lineEdit().setReadOnly(True)
        self.combo_categories.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_categories.activated.connect(self._handle_category_filter)
        self.combo_categories.sizePolicy().setRetainSizeWhenHidden(True)
        self.combo_categories.addItem('--- {} ---'.format(self.i18n['category'].capitalize()), self.any_category_filter)
        self.toolbar_filters.layout().addWidget(self.combo_categories)
        self.comp_manager.register_component(COMBO_CATEGORIES, self.combo_categories)

        self.input_name = QSearchBar(search_callback=self.begin_apply_filters)
        self.input_name.palette().swap(self.combo_categories.palette())
        self.input_name.setObjectName('name_filter')
        self.input_name.set_placeholder(self.i18n['manage_window.name_filter.placeholder'] + '...')
        self.input_name.set_tooltip(self.i18n['manage_window.name_filter.tooltip'])
        self.input_name.set_button_tooltip(self.i18n['manage_window.name_filter.button_tooltip'])
        self.input_name.sizePolicy().setRetainSizeWhenHidden(True)
        self.toolbar_filters.layout().addWidget(self.input_name)
        self.comp_manager.register_component(INP_NAME, self.input_name)

        self.toolbar_filters.layout().addWidget(new_spacer())

        toolbar_bts = []

        bt_inst = QPushButton()
        bt_inst.setObjectName('bt_installed')
        bt_inst.setProperty('root', 'true')
        bt_inst.setCursor(QCursor(Qt.PointingHandCursor))
        bt_inst.setToolTip(self.i18n['manage_window.bt.installed.tooltip'])
        bt_inst.setText(self.i18n['manage_window.bt.installed.text'].capitalize())
        bt_inst.clicked.connect(self._begin_loading_installed)
        bt_inst.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(bt_inst)
        self.toolbar_filters.layout().addWidget(bt_inst)
        self.comp_manager.register_component(BT_INSTALLED, bt_inst)

        bt_ref = QPushButton()
        bt_ref.setObjectName('bt_refresh')
        bt_ref.setProperty('root', 'true')
        bt_ref.setCursor(QCursor(Qt.PointingHandCursor))
        bt_ref.setToolTip(i18n['manage_window.bt.refresh.tooltip'])
        bt_ref.setText(self.i18n['manage_window.bt.refresh.text'])
        bt_ref.clicked.connect(self.begin_refresh_packages)
        bt_ref.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(bt_ref)
        self.toolbar_filters.layout().addWidget(bt_ref)
        self.comp_manager.register_component(BT_REFRESH, bt_ref)

        self.bt_upgrade = QPushButton()
        self.bt_upgrade.setProperty('root', 'true')
        self.bt_upgrade.setObjectName('bt_upgrade')
        self.bt_upgrade.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_upgrade.setToolTip(i18n['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setText(i18n['manage_window.bt.upgrade.text'])
        self.bt_upgrade.clicked.connect(self.upgrade_selected)
        self.bt_upgrade.sizePolicy().setRetainSizeWhenHidden(True)
        toolbar_bts.append(self.bt_upgrade)
        self.toolbar_filters.layout().addWidget(self.bt_upgrade)
        self.comp_manager.register_component(BT_UPGRADE, self.bt_upgrade)

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

        self.layout.addWidget(self.toolbar_filters)

        self.table_container = QWidget()
        self.table_container.setObjectName('table_container')
        self.table_container.setContentsMargins(0, 0, 0, 0)
        self.table_container.setLayout(QVBoxLayout())
        self.table_container.layout().setContentsMargins(0, 0, 0, 0)

        self.table_apps = PackagesTable(self, self.icon_cache,
                                        download_icons=bool(self.config['download']['icons']))
        self.table_apps.change_headers_policy()
        self.table_container.layout().addWidget(self.table_apps)

        self.layout.addWidget(self.table_container)

        self.toolbar_console = QWidget()
        self.toolbar_console.setObjectName('console_toolbar')
        self.toolbar_console.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.toolbar_console.setLayout(QHBoxLayout())
        self.toolbar_console.setContentsMargins(0, 0, 0, 0)

        self.check_details = QCheckBox()
        self.check_details.setObjectName('check_details')
        self.check_details.setCursor(QCursor(Qt.PointingHandCursor))
        self.check_details.setText(self.i18n['manage_window.checkbox.show_details'])
        self.check_details.stateChanged.connect(self._handle_console)
        self.toolbar_console.layout().addWidget(self.check_details)
        self.comp_manager.register_component(CHECK_DETAILS, self.check_details)

        self.toolbar_console.layout().addWidget(new_spacer())

        self.label_displayed = QLabel()
        self.label_displayed.setObjectName('apps_displayed')
        self.label_displayed.setCursor(QCursor(Qt.WhatsThisCursor))
        self.label_displayed.setToolTip(self.i18n['manage_window.label.apps_displayed.tip'])
        self.toolbar_console.layout().addWidget(self.label_displayed)
        self.label_displayed.hide()

        self.layout.addWidget(self.toolbar_console)

        self.textarea_details = QPlainTextEdit(self)
        self.textarea_details.setObjectName('textarea_details')
        self.textarea_details.setProperty('console', 'true')
        self.textarea_details.resize(self.table_apps.size())
        self.layout.addWidget(self.textarea_details)
        self.textarea_details.setVisible(False)
        self.textarea_details.setReadOnly(True)

        self.toolbar_substatus = QToolBar()
        self.toolbar_substatus.setObjectName('toolbar_substatus')
        self.toolbar_substatus.addWidget(new_spacer())

        self.label_substatus = QLabel()
        self.label_substatus.setObjectName('label_substatus')
        self.label_substatus.setCursor(QCursor(Qt.WaitCursor))
        self.toolbar_substatus.addWidget(self.label_substatus)
        self.toolbar_substatus.addWidget(new_spacer())
        self.layout.addWidget(self.toolbar_substatus)
        self._change_label_substatus('')

        self.thread_update = self._bind_async_action(UpgradeSelected(manager=self.manager, i18n=self.i18n,
                                                                     internet_checker=context.internet_checker,
                                                                     parent_widget=self),
                                                     finished_call=self._finish_upgrade_selected)
        self.thread_refresh = self._bind_async_action(RefreshApps(i18n, self.manager), finished_call=self._finish_refresh_packages, only_finished=True)
        self.thread_uninstall = self._bind_async_action(UninstallPackage(self.manager, self.icon_cache, self.i18n), finished_call=self._finish_uninstall)
        self.thread_show_info = self._bind_async_action(ShowPackageInfo(i18n, self.manager), finished_call=self._finish_show_info)
        self.thread_show_history = self._bind_async_action(ShowPackageHistory(self.manager, self.i18n), finished_call=self._finish_show_history)
        self.thread_search = self._bind_async_action(SearchPackages(i18n, self.manager), finished_call=self._finish_search, only_finished=True)
        self.thread_downgrade = self._bind_async_action(DowngradePackage(self.manager, self.i18n), finished_call=self._finish_downgrade)
        self.thread_suggestions = self._bind_async_action(FindSuggestions(i18n=i18n, man=self.manager), finished_call=self._finish_load_suggestions, only_finished=True)
        self.thread_launch = self._bind_async_action(LaunchPackage(i18n, self.manager), finished_call=self._finish_launch_package, only_finished=False)
        self.thread_custom_action = self._bind_async_action(CustomAction(manager=self.manager, i18n=self.i18n), finished_call=self._finish_execute_custom_action)
        self.thread_screenshots = self._bind_async_action(ShowScreenshots(i18n, self.manager), finished_call=self._finish_show_screenshots)

        self.thread_apply_filters = ApplyFilters(i18n=i18n, logger=logger)
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

        self.thread_ignore_updates = IgnorePackageUpdates(i18n=i18n, manager=self.manager)
        self._bind_async_action(self.thread_ignore_updates, finished_call=self.finish_ignore_updates)

        self.thread_reload = StartAsyncAction(delay_in_milis=5)
        self.thread_reload.signal_start.connect(self._reload)

        self.container_bottom = QWidget()
        self.container_bottom.setObjectName('container_bottom')
        self.container_bottom.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.container_bottom.setLayout(QHBoxLayout())
        self.container_bottom.layout().setContentsMargins(0, 0, 0, 0)

        self.container_bottom.layout().addWidget(new_spacer())

        self.load_suggestions = force_suggestions or bool(config['suggestions']['enabled'])
        self.suggestions_requested = False

        if self.load_suggestions:
            bt_sugs = IconButton(action=lambda: self.begin_load_suggestions(filter_installed=True),
                                 i18n=i18n,
                                 tooltip=self.i18n['manage_window.bt.suggestions.tooltip'])
            bt_sugs.setObjectName('suggestions')
            self.container_bottom.layout().addWidget(bt_sugs)
            self.comp_manager.register_component(BT_SUGGESTIONS, bt_sugs)

        bt_themes = IconButton(self.show_themes,
                               i18n=self.i18n,
                               tooltip=self.i18n['manage_window.bt_themes.tip'])
        bt_themes.setObjectName('themes')
        self.container_bottom.layout().addWidget(bt_themes)
        self.comp_manager.register_component(BT_THEMES, bt_themes)

        self.custom_actions = [a for a in manager.gen_custom_actions()]
        bt_custom_actions = IconButton(action=self.show_custom_actions,
                                       i18n=self.i18n,
                                       tooltip=self.i18n['manage_window.bt_custom_actions.tip'])
        bt_custom_actions.setObjectName('custom_actions')

        bt_custom_actions.setVisible(bool(self.custom_actions))
        self.container_bottom.layout().addWidget(bt_custom_actions)
        self.comp_manager.register_component(BT_CUSTOM_ACTIONS, bt_custom_actions)

        bt_settings = IconButton(action=self.show_settings,
                                 i18n=self.i18n,
                                 tooltip=self.i18n['manage_window.bt_settings.tooltip'])
        bt_settings.setObjectName('settings')
        self.container_bottom.layout().addWidget(bt_settings)
        self.comp_manager.register_component(BT_SETTINGS, bt_settings)

        bt_about = IconButton(action=self._show_about,
                              i18n=self.i18n,
                              tooltip=self.i18n['manage_window.settings.about'])
        bt_about.setObjectName('about')
        self.container_bottom.layout().addWidget(bt_about)
        self.comp_manager.register_component(BT_ABOUT, bt_about)

        self.layout.addWidget(self.container_bottom)

        self.container_progress = QCustomToolbar(spacing=0, policy_height=QSizePolicy.Fixed)
        self.container_progress.setObjectName('container_progress')
        self.container_progress.add_space()

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('progress_manage')
        self.progress_bar.setCursor(QCursor(Qt.WaitCursor))

        self.progress_bar.setTextVisible(False)
        self.container_progress.add_widget(self.progress_bar)
        self.container_progress.add_space()
        self.layout.addWidget(self.container_progress)

        self.filter_only_apps = True
        self.type_filter = self.any_type_filter
        self.category_filter = self.any_category_filter
        self.filter_updates = False
        self.filter_installed = False
        self._maximized = False
        self.progress_controll_enabled = True
        self.recent_uninstall = False
        self.types_changed = False

        self.dialog_about = None
        self.first_refresh = True

        self.thread_warnings = ListWarnings(man=manager, i18n=i18n)
        self.thread_warnings.signal_warnings.connect(self._show_warnings)
        self.settings_window = None
        self.search_performed = False

        self.thread_save_theme = SaveTheme(theme_key='')

        self.thread_load_installed = NotifyInstalledLoaded()
        self.thread_load_installed.signal_loaded.connect(self._finish_loading_installed)
        self._register_groups()
        self._screen_geometry: Optional[QRect] = None

    def _register_groups(self):
        common_filters = (CHECK_APPS, CHECK_UPDATES, COMBO_CATEGORIES, COMBO_TYPES, INP_NAME)
        self.comp_manager.register_group(GROUP_FILTERS, False, CHECK_INSTALLED, *common_filters)

        self.comp_manager.register_group(GROUP_VIEW_SEARCH, False,
                                         COMBO_CATEGORIES, COMBO_TYPES, INP_NAME,  # filters
                                         BT_INSTALLED, BT_SUGGESTIONS, CHECK_INSTALLED)  # buttons

        self.comp_manager.register_group(GROUP_VIEW_INSTALLED, False,
                                         BT_REFRESH, BT_UPGRADE,  # buttons
                                         *common_filters)

        self.comp_manager.register_group(GROUP_UPPER_BAR, False,
                                         CHECK_APPS, CHECK_UPDATES, CHECK_INSTALLED, COMBO_CATEGORIES, COMBO_TYPES, INP_NAME,
                                         BT_INSTALLED, BT_SUGGESTIONS, BT_REFRESH, BT_UPGRADE)

        self.comp_manager.register_group(GROUP_LOWER_BTS, False, BT_SUGGESTIONS, BT_THEMES, BT_CUSTOM_ACTIONS, BT_SETTINGS, BT_ABOUT)

    def update_custom_actions(self):
        self.custom_actions = [a for a in self.manager.gen_custom_actions()]

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
        self._resize()

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
        extra_widgets = [to_widget(comp=c, i18n=self.i18n) for c in msg['components']] if msg.get('components') else None
        diag = ConfirmationDialog(title=msg['title'],
                                  body=msg['body'],
                                  i18n=self.i18n,
                                  widgets=extra_widgets,
                                  confirmation_label=msg['confirmation_label'],
                                  deny_label=msg['deny_label'],
                                  deny_button=msg['deny_button'],
                                  window_cancel=msg['window_cancel'],
                                  confirmation_button=msg.get('confirmation_button', True),
                                  min_width=msg.get('min_width'),
                                  min_height=msg.get('min_height'),
                                  max_width=msg.get('max_width'))
        diag.ask()
        res = diag.confirmed
        self.thread_animate_progress.animate()
        self.signal_user_res.emit(res)

    def _pause_and_ask_root_password(self):
        self.thread_animate_progress.pause()
        valid, password = RootDialog.ask_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)

        self.thread_animate_progress.animate()
        self.signal_root_password.emit(valid, password)

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
        self._screen_geometry = get_current_screen_geometry()
        self._update_size_limits()

    def verify_warnings(self):
        self.thread_warnings.start()

    def _begin_loading_installed(self):
        if self.installed_loaded:
            self.table_apps.stop_file_downloader()
            self.search_bar.clear()
            self.input_name.set_text('')
            self._begin_action(self.i18n['manage_window.status.installed'])
            self._handle_console_option(False)
            self.comp_manager.set_components_visible(False)
            self.suggestions_requested = False
            self.search_performed = False
            self.thread_load_installed.start()
        else:
            self.load_suggestions = False
            self.begin_refresh_packages()

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

    def _handle_filter_only_installed(self, status: int):
        self.filter_installed = status == 2
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
        if self.table_apps.isEnabled() and self.pkgs is not None and 0 <= idx < len(self.pkgs):
            pkg = self.pkgs[idx]
            pkg.status = PackageViewStatus.READY
            screen_width = get_current_screen_geometry(self).width()
            self.table_apps.update_package(pkg, screen_width=screen_width)

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

    def _update_size_limits(self):
        self.setMinimumHeight(int(self._screen_geometry.height() * 0.5))
        self.setMinimumWidth(int(self._screen_geometry.width() * 0.5))
        self.setMaximumWidth(int(self._screen_geometry.width()))

    def changeEvent(self, e: QEvent):
        if isinstance(e, QWindowStateChangeEvent):
            self._maximized = self.isMaximized()
            self.table_apps.change_headers_policy(maximized=self._maximized)

            if not self._maximized:
                self._reorganize()
                self.adjustSize()

    def event(self, e: QEvent) -> bool:
        res = super(ManageWindow, self).event(e)

        if self.isVisible() and e.type() == 216:  # drop event
            current_geometry = get_current_screen_geometry()
            if current_geometry != self._screen_geometry:  # only if the display device has changed
                self._screen_geometry = current_geometry
                self._update_size_limits()
                self._reorganize()
                self.adjustSize()

        return res

    def _handle_console(self, checked: bool):
        if checked:
            self.textarea_details.show()
        else:
            self.textarea_details.hide()

    def _handle_console_option(self, enable: bool):
        if enable:
            self.textarea_details.clear()

        self.comp_manager.set_component_visible(CHECK_DETAILS, enable)
        self.check_details.setChecked(False)
        self.textarea_details.hide()

    def begin_refresh_packages(self, pkg_types: Optional[Set[Type[SoftwarePackage]]] = None):
        self.table_apps.stop_file_downloader()
        self.search_bar.clear()

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

    def load_without_packages(self):
        self.load_suggestions = False
        self._handle_console_option(False)
        self._finish_refresh_packages({'installed': None, 'types': None}, as_installed=False)

    def begin_load_suggestions(self, filter_installed: bool):
        self.table_apps.stop_file_downloader()
        self.search_bar.clear()
        self._begin_action(self.i18n['manage_window.status.suggestions'])
        self._handle_console_option(False)
        self.comp_manager.set_components_visible(False)
        self.suggestions_requested = True
        self.thread_suggestions.filter_installed = filter_installed
        self.thread_suggestions.start()

    def _finish_load_suggestions(self, res: dict):
        self._finish_search(res)

    def begin_uninstall(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password(SoftwareAction.UNINSTALL, pkg)

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

        self._write_operation_logs('uninstall', res['pkg'])

        if res['success']:
            src_pkg = res['pkg']
            if self._can_notify_user():
                util.notify_user('{} ({}) {}'.format(src_pkg.model.name, src_pkg.model.get_type(), self.i18n['uninstalled']))

            if res['removed']:
                screen_width = get_current_screen_geometry(self).width()
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
                                        self.table_apps.update_package(pkgv,
                                                                       screen_width=screen_width,
                                                                       change_update_col=True)

                                    break  # as the model has been found, stops the loop

                        if removed_idxs:
                            # updating the list
                            removed_idxs.sort()
                            for decrement, pkg_idx in enumerate(removed_idxs):
                                del pkg_list[pkg_idx - decrement]

                            if list_idx == 1:  # updates the rows if the current list represents the displayed packages:
                                for decrement, idx in enumerate(removed_idxs):
                                    self.table_apps.removeRow(idx - decrement)

                                self._update_table_indexes()

                        self.update_bt_upgrade()

            self.update_custom_actions()
            self._show_console_checkbox_if_output()
            self._update_installed_filter()
            self.begin_apply_filters()
            self.table_apps.change_headers_policy(policy=QHeaderView.Stretch, maximized=self._maximized)
            self.table_apps.change_headers_policy(policy=QHeaderView.ResizeToContents, maximized=self._maximized)
            self._resize(accept_lower_width=True)
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

        if pkgs_info['not_installed'] == 0:
            update_check = sum_updates_displayed(pkgs_info) > 0
        else:
            update_check = False

        self.table_apps.update_packages(self.pkgs, update_check_enabled=update_check)

        if not self._maximized:
            self.label_displayed.show()
            self.table_apps.change_headers_policy(QHeaderView.Stretch)
            self.table_apps.change_headers_policy()
            self._resize(accept_lower_width=len(self.pkgs) > 0)

            if len(self.pkgs) == 0 and len(self.pkgs_available) == 0:
                self.label_displayed.setText('')
            else:
                self.label_displayed.setText('{} / {}'.format(len(self.pkgs), len(self.pkgs_available)))
        else:
            self.label_displayed.hide()

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
            'name': self.input_name.text().lower() if self.input_name.text() else None,
            'display_limit': None if self.filter_updates else self.display_limit,
            'only_installed': self.filter_installed
        }

    def update_pkgs(self, new_pkgs: Optional[List[SoftwarePackage]], as_installed: bool, types: Optional[Set[type]] = None, ignore_updates: bool = False, keep_filters: bool = False) -> bool:
        self.input_name.set_text('')
        pkgs_info = commons.new_pkgs_info()
        pkg_idx = commons.new_package_index()
        filters = self._gen_filters(ignore_updates=ignore_updates)

        if new_pkgs is not None:
            old_installed = None

            if as_installed:
                old_installed = self.pkgs_installed
                self.pkgs_installed = []

            for pkg in new_pkgs:
                pkgv = PackageView(model=pkg, i18n=self.i18n)
                commons.update_info(pkgv, pkgs_info)
                commons.add_to_index(pkgv, pkg_idx)
                commons.apply_filters(pkgv, filters, pkgs_info)

            if old_installed and types:
                for pkgv in old_installed:
                    if pkgv.model.__class__ not in types:
                        commons.update_info(pkgv, pkgs_info)
                        commons.add_to_index(pkgv, pkg_idx)
                        commons.apply_filters(pkgv, filters, pkgs_info)

        else:  # use installed
            for pkgv in self.pkgs_installed:
                commons.update_info(pkgv, pkgs_info)
                commons.add_to_index(pkgv, pkg_idx)
                commons.apply_filters(pkgv, filters, pkgs_info)

        if pkgs_info['apps_count'] == 0 and not self.suggestions_requested:
            if self.load_suggestions or self.types_changed:
                if as_installed:
                    self.pkgs_installed = pkgs_info['pkgs']

                self.begin_load_suggestions(filter_installed=True)
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
        self.pkg_idx = pkg_idx

        if as_installed:
            self.pkgs_installed = pkgs_info['pkgs']

        self.pkgs = pkgs_info['pkgs_displayed']
        self._update_installed_filter(installed_available=pkgs_info['installed'] > 0,
                                      keep_state=keep_filters,
                                      hide=as_installed)
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

        if not self.installed_loaded and as_installed:
            self.installed_loaded = True

        return True

    def _update_installed_filter(self, keep_state: bool = True, hide: bool = False, installed_available: Optional[bool] = None):
        if installed_available is not None:
            has_installed = installed_available
        elif self.pkgs_available == self.pkgs_installed:  # it means the "installed" view is loaded
            has_installed = False
        else:
            has_installed = False
            if self.pkgs_available:
                for p in self.pkgs_available:
                    if p.model.installed:
                        has_installed = True
                        break

        if not keep_state or not has_installed:
            self._change_checkbox(self.check_installed, False, 'filter_installed', trigger=False)

        if hide:
            self.comp_manager.set_component_visible(CHECK_INSTALLED, False)
        else:
            self.comp_manager.set_component_visible(CHECK_INSTALLED, has_installed)

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
        toolbar_width = self.toolbar_filters.sizeHint().width()
        topbar_width = self.toolbar_status.sizeHint().width()

        new_width = max(table_width, toolbar_width, topbar_width)
        new_width *= 1.05  # this extra size is not because of the toolbar button, but the table upgrade buttons
        new_width = int(new_width)

        if new_width >= self.maximumWidth():
            new_width = self.maximumWidth()

        if (self.pkgs and accept_lower_width) or new_width > self.width():
            self.resize(new_width, self.height())
            self.setMinimumWidth(new_width)

    def set_progress_controll(self, enabled: bool):
        self.progress_controll_enabled = enabled

    def upgrade_selected(self):
        body = QWidget()
        body.setLayout(QHBoxLayout())
        body.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        body.layout().addWidget(QLabel(self.i18n['manage_window.upgrade_all.popup.body']))
        body.layout().addWidget(UpgradeToggleButton(pkg=None, root=self, i18n=self.i18n, clickable=False))
        if ConfirmationDialog(title=self.i18n['manage_window.upgrade_all.popup.title'],
                              i18n=self.i18n, body=None,
                              widgets=[body]).ask():

            self._begin_action(action_label=self.i18n['manage_window.status.upgrading'],
                               action_id=ACTION_UPGRADE)
            self.comp_manager.set_components_visible(False)
            self._handle_console_option(True)
            self.thread_update.pkgs = self.pkgs
            self.thread_update.start()

    def _finish_upgrade_selected(self, res: dict):
        self._finish_action()

        if res.get('id'):
            self._write_operation_logs('upgrade', custom_log_file=f"{UpgradeSelected.UPGRADE_LOGS_DIR}/{res['id']}.log")
            sum_log_file = UpgradeSelected.SUMMARY_FILE.format(res['id'])
            summ_msg = '* ' + self.i18n['console.upgrade_summary'].format(path=f'"{sum_log_file}"')
            self.textarea_details.appendPlainText(summ_msg)

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
        if self.textarea_details.toPlainText():
            self.check_details.setChecked(True)
        else:
            self._handle_console_option(False)
            self.comp_manager.set_component_visible(CHECK_DETAILS, False)

    def _update_action_output(self, output: str):
        self.textarea_details.appendPlainText(output)

    def _begin_action(self, action_label: str, action_id: int = None):
        self.thread_animate_progress.stop = False
        self.thread_animate_progress.start()
        self.progress_bar.setVisible(True)

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

        self.progress_bar.setVisible(False)
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
        pwd, proceed = self._ask_root_password(SoftwareAction.DOWNGRADE, pkg)

        if not proceed:
            return

        self.table_apps.stop_file_downloader()
        label = f"{self.i18n['manage_window.status.downgrading']} {pkg.model.name}"
        self._begin_action(action_label=label, action_id=ACTION_DOWNGRADE)
        self.comp_manager.set_components_visible(False)
        self._handle_console_option(True)

        self.thread_downgrade.pkg = pkg
        self.thread_downgrade.root_pwd = pwd
        self.thread_downgrade.start()

    def _finish_downgrade(self, res: dict):
        self._finish_action()
        self._write_operation_logs('downgrade', res['app'])

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

        if pkg_info:
            if len(pkg_info) > 1:
                dialog_info = InfoDialog(pkg_info=pkg_info, icon_cache=self.icon_cache, i18n=self.i18n)
                dialog_info.exec_()
            else:
                dialog.show_message(title=self.i18n['warning'].capitalize(),
                                    body=self.i18n['manage_window.info.no_info'].format(bold(pkg_info['__app__'].model.name)),
                                    type_=MessageType.WARNING)

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
            self.textarea_details.appendPlainText(res['error'])
            self.check_details.setChecked(True)
        elif not res['history'].history:
            dialog.show_message(title=self.i18n['action.history.no_history.title'],
                                body=self.i18n['action.history.no_history.body'].format(bold(res['history'].pkg.name)),
                                type_=MessageType.WARNING)
        else:
            dialog_history = HistoryDialog(res['history'], self.icon_cache, self.i18n)
            dialog_history.exec_()

    def search(self):
        word = self.search_bar.text().strip()
        if word:
            self.table_apps.stop_file_downloader()
            self._handle_console(False)
            self.filter_updates = False
            self.filter_installed = False
            label = f"{self.i18n['manage_window.status.searching']} {word if word else ''}"
            self._begin_action(action_label=label, action_id=ACTION_SEARCH)
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

    def _ask_root_password(self, action: SoftwareAction, pkg: PackageView) -> Tuple[Optional[str], bool]:
        pwd = None
        requires_root = self.manager.requires_root(action, pkg.model)

        if not user.is_root() and requires_root:
            valid, pwd = RootDialog.ask_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)
            if not valid:
                return pwd, False

        return pwd, True

    def install(self, pkg: PackageView):
        pwd, proceed = self._ask_root_password(SoftwareAction.INSTALL, pkg)

        if not proceed:
            return

        self._begin_action('{} {}'.format(self.i18n['manage_window.status.installing'], pkg.model.name), action_id=ACTION_INSTALL)
        self.comp_manager.set_groups_visible(False, GROUP_UPPER_BAR, GROUP_LOWER_BTS)
        self._handle_console_option(True)

        self.thread_install.pkg = pkg
        self.thread_install.root_pwd = pwd
        self.thread_install.start()

    def _write_operation_logs(self, type_: str, pkg: Optional[PackageView] = None,
                              custom_log_file: Optional[str] = None):

        console_output = self.textarea_details.toPlainText()

        if console_output:
            if custom_log_file:
                log_dir = os.path.dirname(custom_log_file)
                log_file = custom_log_file
            else:
                log_dir = f"{LOGS_DIR}/{type_}"
                if pkg:
                    log_dir = f"{log_dir}/{pkg.model.get_type()}/{pkg.model.name}"

                log_file = f'{log_dir}/{int(time.time())}.log'

            try:
                Path(log_dir).mkdir(parents=True, exist_ok=True)
            except OSError:
                self.logger.error(f"Could not create the operation log directory '{log_dir}'")
                return

            try:
                with open(log_file, 'w+') as f:
                    f.write(console_output)
            except OSError:
                self.logger.error(f"Could not write the operation log to file '{log_file}'")
                return

            log_msg = '\n* ' + self.i18n['console.operation_log'].format(path=f'"{log_file}"')
            self.textarea_details.appendPlainText(log_msg)

    def _finish_install(self, res: dict):
        self._finish_action(action_id=ACTION_INSTALL)
        self._write_operation_logs('install', res['pkg'])

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
                screen_width = get_current_screen_geometry(self).width()
                for displayed in self.pkgs:
                    for model in models_updated:
                        if displayed.model == model:
                            self.table_apps.update_package(displayed, screen_width=screen_width, change_update_col=True)

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
            self._update_installed_filter(installed_available=True, keep_state=True)
            self.table_apps.change_headers_policy(policy=QHeaderView.Stretch, maximized=self._maximized)
            self.table_apps.change_headers_policy(policy=QHeaderView.ResizeToContents, maximized=self._maximized)
            self._resize(accept_lower_width=False)
        else:
            self._show_console_errors()
            if self._can_notify_user():
                util.notify_user('{}: {}'.format(res['pkg'].model.name, self.i18n['notification.install.failed']))

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def begin_execute_custom_action(self, pkg: Optional[PackageView], action: CustomSoftwareAction):
        if pkg is None and action.requires_confirmation and \
                not ConfirmationDialog(title=self.i18n['confirmation'].capitalize(),
                                       body='<p>{}</p>'.format(self.i18n['custom_action.proceed_with'].capitalize().format(bold(self.i18n[action.i18n_label_key]))),
                                       icon=QIcon(action.icon_path) if action.icon_path else QIcon(resource.get_path('img/logo.svg')),
                                       i18n=self.i18n).ask():
            return False

        pwd = None

        if not user.is_root() and action.requires_root:
            valid, pwd = RootDialog.ask_password(self.context, i18n=self.i18n, comp_manager=self.comp_manager)

            if not valid:
                return

        action_label = self.i18n[action.i18n_status_key]

        if pkg:
            if '{}' in action_label:
                action_label = action_label.format(pkg.model.name)
            else:
                action_label += f' {pkg.model.name}'

        if action.refresh:
            self.table_apps.stop_file_downloader()

        self._begin_action(action_label=action_label, action_id=ACTION_CUSTOM_ACTION)
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
                self.update_custom_actions()
                self.begin_refresh_packages(pkg_types={res['pkg'].model.__class__} if res['pkg'] else None)
            else:
                self.comp_manager.restore_state(ACTION_CUSTOM_ACTION)

            self._show_console_checkbox_if_output()
        else:
            self.comp_manager.restore_state(ACTION_CUSTOM_ACTION)
            self._show_console_errors()

            if res['error']:
                dialog.show_message(title=self.i18n['warning' if res['error_type'] == MessageType.WARNING else 'error'].capitalize(),
                                    body=self.i18n[res['error']],
                                    type_=res['error_type'])

    def _show_console_checkbox_if_output(self):
        if self.textarea_details.toPlainText():
            self.comp_manager.set_component_visible(CHECK_DETAILS, True)
        else:
            self.comp_manager.set_component_visible(CHECK_DETAILS, False)

    def show_settings(self):
        if self.settings_window:
            self.settings_window.handle_display()
        else:
            self.settings_window = SettingsWindow(manager=self.manager, i18n=self.i18n, window=self)
            screen_width = get_current_screen_geometry(self).width()
            self.settings_window.setMinimumWidth(int(screen_width / 4))
            self.settings_window.resize(self.size())
            self.settings_window.adjustSize()
            qt_utils.centralize(self.settings_window)
            self.settings_window.show()

    def _map_custom_action(self, action: CustomSoftwareAction, parent: QWidget) -> QCustomMenuAction:

        if action.icon_path:
            try:
                if action.icon_path.startswith('/'):
                    icon = QIcon(action.icon_path)
                else:
                    icon = QIcon.fromTheme(action.icon_path)
            except Exception:
                icon = None
        else:
            icon = None

        tip = self.i18n[action.i18n_description_key] if action.i18n_description_key else None
        return QCustomMenuAction(parent=parent,
                                 label=self.i18n[action.i18n_label_key],
                                 action=lambda: self.begin_execute_custom_action(None, action),
                                 tooltip=tip,
                                 icon=icon)

    def show_custom_actions(self):
        if self.custom_actions:
            menu_row = QMenu()
            menu_row.setCursor(QCursor(Qt.PointingHandCursor))
            actions = [self._map_custom_action(a, menu_row) for a in self.custom_actions]
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
                screen_width = get_current_screen_geometry(self).width()
                for pkg in self.pkgs:
                    if pkg == res['pkg']:
                        pkg.update_model(res['pkg'].model)
                        self.table_apps.update_package(pkg, screen_width=screen_width, change_update_col=not any([self.search_performed, self.suggestions_requested]))
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

    def _map_theme_action(self, theme: ThemeMetadata, menu: QMenu) -> QCustomMenuAction:
        def _change_theme():
            set_theme(theme_key=theme.key, app=QApplication.instance(), logger=self.context.logger)
            self.thread_save_theme.theme_key = theme.key
            self.thread_save_theme.start()

        return QCustomMenuAction(label=theme.get_i18n_name(self.i18n),
                                 action=_change_theme,
                                 parent=menu,
                                 tooltip=theme.get_i18n_description(self.i18n))

    def show_themes(self):
        menu_row = QMenu()
        menu_row.setCursor(QCursor(Qt.PointingHandCursor))
        menu_row.addActions(self._map_theme_actions(menu_row))
        menu_row.adjustSize()
        menu_row.popup(QCursor.pos())
        menu_row.exec_()

    def _map_theme_actions(self, menu: QMenu) -> List[QCustomMenuAction]:
        core_config = CoreConfigManager().get_config()

        current_theme_key, current_action = core_config['ui']['theme'], None

        actions = []

        for t in read_all_themes_metadata():
            if not t.abstract:
                action = self._map_theme_action(t, menu)

                if current_action is None and current_theme_key is not None and current_theme_key == t.key:
                    action.button.setProperty('current', 'true')
                    current_action = action
                else:
                    actions.append(action)

        if not current_action:
            invalid_action = QCustomMenuAction(label=self.i18n['manage_window.bt_themes.option.invalid'], parent=menu)
            invalid_action.button.setProperty('current', 'true')
            current_action = invalid_action

        actions.sort(key=lambda a: a.get_label())
        actions.insert(0, current_action)
        return actions

    def reload(self):
        self.thread_reload.start()

    def _reload(self):
        self.update_custom_actions()
        self.verify_warnings()
        self.types_changed = True
        self.begin_refresh_packages()
