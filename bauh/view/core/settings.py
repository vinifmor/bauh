import os
import time
import traceback
from math import floor
from threading import Thread
from typing import List, Tuple, Optional, Dict, Type, Iterable

from PyQt5.QtWidgets import QApplication, QStyleFactory

from bauh import ROOT_DIR, __app_name__
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SettingsController, SettingsView
from bauh.api.abstract.view import TabComponent, InputOption, TextComponent, MultipleSelectComponent, \
    PanelComponent, FormComponent, TabGroupComponent, SingleSelectComponent, SelectViewType, TextInputComponent, \
    FileChooserComponent, RangeInputComponent, ViewComponentAlignment
from bauh.commons.view_utils import new_select
from bauh.view.core import timeshift
from bauh.view.core.config import CoreConfigManager, BACKUP_REMOVE_METHODS, BACKUP_DEFAULT_REMOVE_METHOD
from bauh.view.core.downloader import AdaptableFileDownloader
from bauh.view.util import translation


class GenericSettingsManager(SettingsController):

    def __init__(self, context: ApplicationContext, managers: List[SoftwareManager],
                 working_managers: List[SoftwareManager], configman: CoreConfigManager):
        self.context = context
        self.i18n = context.i18n
        self.managers = managers
        self.working_managers = working_managers
        self.logger = context.logger
        self.file_downloader = self.context.file_downloader
        self.configman = configman
        self._settings_views: Optional[Dict[Type, List[SettingsView]]] = None

    def get_settings(self) -> TabGroupComponent:
        tabs = list()

        gem_opts, def_gem_opts, gem_tabs = [], set(), []

        self._settings_views = dict()

        for man in self.managers:
            can_work, reason_not_work = man.can_work()
            modname = man.__module__.split('.')[-2]

            man_settings = man.get_settings() if can_work else None
            if man_settings:
                for view in man_settings:
                    icon_path = view.icon_path

                    if not icon_path:
                        icon_path = f"{ROOT_DIR}/gems/{modname}/resources/img/{modname}.svg"

                    tab_name = view.label if view.label else self.i18n.get(f'gem.{modname}.label', modname.capitalize())
                    gem_tabs.append(TabComponent(label=tab_name, content=view.component, icon_path=icon_path))

                    views = self._settings_views.get(man.__class__, list())
                    self._settings_views[man.__class__] = views
                    views.append(view)

            help_tip = reason_not_work if not can_work and reason_not_work else self.i18n.get(f'gem.{modname}.info')
            opt = InputOption(label=self.i18n.get(f'gem.{modname}.label', modname.capitalize()),
                              tooltip=help_tip,
                              value=modname,
                              icon_path=f'{ROOT_DIR}/gems/{modname}/resources/img/{modname}.svg',
                              read_only=not can_work,
                              extra_properties={'warning': 'true'} if not can_work else None)
            gem_opts.append(opt)

            if man.is_enabled() and man in self.working_managers:
                def_gem_opts.add(opt)

        core_config = self.configman.get_config()

        if gem_opts:
            type_help = TextComponent(html=self.i18n['core.config.types.tip'])
            gem_opts.sort(key=lambda o: o.value)
            gem_selector = MultipleSelectComponent(label=None,
                                                   tooltip=None,
                                                   options=gem_opts,
                                                   max_width=floor(self.context.screen_width * 0.22),
                                                   default_options=def_gem_opts,
                                                   id_="gems")
            tabs.append(TabComponent(label=self.i18n['core.config.tab.types'],
                                     content=PanelComponent([type_help, FormComponent([gem_selector], spaces=False)]),
                                     id_='core.types'))

        tabs.append(self._gen_general_settings(core_config))
        tabs.append(self._gen_interface_settings(core_config))
        tabs.append(self._gen_tray_settings(core_config))
        tabs.append(self._gen_adv_settings(core_config))

        bkp_settings = self._gen_backup_settings(core_config)

        if bkp_settings:
            tabs.append(bkp_settings)

        for tab in gem_tabs:
            tabs.append(tab)

        return TabGroupComponent(tabs)

    def _gen_adv_settings(self, core_config: dict) -> TabComponent:

        input_data_exp = TextInputComponent(label=self.i18n['core.config.mem_cache.data_exp'],
                                            tooltip=self.i18n['core.config.mem_cache.data_exp.tip'],
                                            value=str(core_config['memory_cache']['data_expiration']),
                                            only_int=True,
                                            id_="data_exp")

        input_icon_exp = TextInputComponent(label=self.i18n['core.config.mem_cache.icon_exp'],
                                            tooltip=self.i18n['core.config.mem_cache.icon_exp.tip'],
                                            value=str(core_config['memory_cache']['icon_expiration']),
                                            only_int=True,
                                            id_="icon_exp")

        select_trim = new_select(label=self.i18n['core.config.trim.after_upgrade'],
                                 tip=self.i18n['core.config.trim.after_upgrade.tip'],
                                 value=core_config['disk']['trim']['after_upgrade'],
                                 opts=[(self.i18n['yes'].capitalize(), True, None),
                                       (self.i18n['no'].capitalize(), False, None),
                                       (self.i18n['ask'].capitalize(), None, None)],
                                 id_='trim_after_upgrade')

        select_dep_check = self._gen_bool_component(label=self.i18n['core.config.system.dep_checking'],
                                                    tooltip=self.i18n['core.config.system.dep_checking.tip'],
                                                    value=core_config['system']['single_dependency_checking'],
                                                    id_='dep_check')

        select_check_ssl = self._gen_bool_component(label=self.i18n['core.config.download.check_ssl'],
                                                    tooltip=self.i18n['core.config.download.check_ssl.tip'],
                                                    value=core_config['download']['check_ssl'],
                                                    id_='download.check_ssl')

        select_dmthread = self._gen_bool_component(label=self.i18n['core.config.download.multithreaded'],
                                                   tooltip=self.i18n['core.config.download.multithreaded.tip'],
                                                   id_="down_mthread",
                                                   value=core_config['download']['multithreaded'])

        select_mthread_client = self._gen_multithread_client_select(core_config)

        inputs = [select_dmthread, select_mthread_client, select_check_ssl, select_trim, select_dep_check,
                  input_data_exp, input_icon_exp]
        panel = PanelComponent([FormComponent(inputs, spaces=False)], id_='advanced')
        return TabComponent(self.i18n['core.config.tab.advanced'].capitalize(), panel, None, 'core.adv')

    def _gen_multithread_client_select(self, core_config: dict) -> SingleSelectComponent:
        available_mthread_clients = self.file_downloader.list_available_multithreaded_clients()
        available_mthread_clients.sort()

        default_i18n_key = 'default' if available_mthread_clients else 'core.config.download.multithreaded_client.none'
        mthread_client_opts = [(self.i18n[default_i18n_key].capitalize(), None, None)]

        for client in available_mthread_clients:
            mthread_client_opts.append((client, client, None))

        current_mthread_client = core_config['download']['multithreaded_client']

        if current_mthread_client not in available_mthread_clients:
            current_mthread_client = None

        return new_select(label=self.i18n['core.config.download.multithreaded_client'],
                          tip=self.i18n['core.config.download.multithreaded_client.tip'],
                          id_="mthread_client",
                          opts=mthread_client_opts,
                          value=current_mthread_client)

    def _gen_tray_settings(self, core_config: dict) -> TabComponent:
        input_update_interval = TextInputComponent(label=self.i18n['core.config.updates.interval'].capitalize(),
                                                   tooltip=self.i18n['core.config.updates.interval.tip'],
                                                   only_int=True,
                                                   value=str(core_config['updates']['check_interval']),
                                                   id_="updates_interval")

        allowed_exts = {'png', 'svg', 'jpg', 'jpeg', 'ico', 'xpm'}
        de_path = str(core_config['ui']['tray']['default_icon']) if core_config['ui']['tray']['default_icon'] else None
        select_def_icon = FileChooserComponent(id_='def_icon',
                                               label=self.i18n["core.config.ui.tray.default_icon"],
                                               tooltip=self.i18n["core.config.ui.tray.default_icon.tip"],
                                               file_path=de_path,
                                               allowed_extensions=allowed_exts)

        up_path = str(core_config['ui']['tray']['updates_icon']) if core_config['ui']['tray']['updates_icon'] else None
        select_up_icon = FileChooserComponent(id_='up_icon',
                                              label=self.i18n["core.config.ui.tray.updates_icon"].capitalize(),
                                              tooltip=self.i18n["core.config.ui.tray.updates_icon.tip"].capitalize(),
                                              file_path=up_path,
                                              allowed_extensions=allowed_exts)

        sub_comps = [FormComponent([select_def_icon, select_up_icon, input_update_interval], spaces=False)]
        return TabComponent(self.i18n['core.config.tab.tray'].capitalize(),
                            PanelComponent(sub_comps, id_='tray'), None, 'core.tray')

    def _gen_interface_settings(self, core_config: dict) -> TabComponent:
        select_hdpi = self._gen_bool_component(label=self.i18n['core.config.ui.hdpi'],
                                               tooltip=self.i18n['core.config.ui.hdpi.tip'],
                                               value=bool(core_config['ui']['hdpi']),
                                               id_='hdpi')

        scale_tip = self.i18n['core.config.ui.auto_scale.tip'].format('QT_AUTO_SCREEN_SCALE_FACTOR')
        select_ascale = self._gen_bool_component(label=self.i18n['core.config.ui.auto_scale'],
                                                 tooltip=scale_tip,
                                                 value=bool(core_config['ui']['auto_scale']),
                                                 id_='auto_scale')

        try:
            scale = float(core_config['ui']['scale_factor'])

            if scale < 1.0:
                scale = 1.0
        except ValueError:
            scale = 1.0

        select_scale = RangeInputComponent(id_="scalef", label=self.i18n['core.config.ui.scale_factor'] + ' (%)',
                                           tooltip=self.i18n['core.config.ui.scale_factor.tip'],
                                           min_value=100, max_value=400, step_value=5, value=int(scale * 100))

        if not core_config['ui']['qt_style']:
            cur_style = QApplication.instance().property('qt_style')
        else:
            cur_style = core_config['ui']['qt_style']

        style_opts = [InputOption(label=s.capitalize(), value=s.lower()) for s in QStyleFactory.keys()]

        default_style = [o for o in style_opts if o.value == cur_style]

        if not default_style:
            if cur_style:
                default_style = InputOption(label=cur_style, value=cur_style)
                style_opts.append(default_style)
            else:
                default_style = style_opts[0]
        else:
            default_style = default_style[0]

        select_style = SingleSelectComponent(label=self.i18n['style'].capitalize(),
                                             tooltip=self.i18n['core.config.ui.qt_style.tooltip'],
                                             options=style_opts,
                                             default_option=default_style,
                                             type_=SelectViewType.COMBO,
                                             alignment=ViewComponentAlignment.CENTER,
                                             id_="style")

        systheme_tip = self.i18n['core.config.ui.system_theme.tip'].format(app=__app_name__)
        select_system_theme = self._gen_bool_component(label=self.i18n['core.config.ui.system_theme'],
                                                       tooltip=systheme_tip,
                                                       value=bool(core_config['ui']['system_theme']),
                                                       id_='system_theme')

        input_maxd = TextInputComponent(label=self.i18n['core.config.ui.max_displayed'],
                                        tooltip=self.i18n['core.config.ui.max_displayed.tip'],
                                        only_int=True,
                                        id_="table_max",
                                        value=str(core_config['ui']['table']['max_displayed']))

        select_dicons = self._gen_bool_component(label=self.i18n['core.config.download.icons'],
                                                 tooltip=self.i18n['core.config.download.icons.tip'],
                                                 id_="down_icons",
                                                 value=core_config['download']['icons'])

        sub_comps = [FormComponent([select_hdpi, select_ascale, select_scale,
                                    select_dicons, select_system_theme,
                                    select_style, input_maxd], spaces=False)]

        return TabComponent(self.i18n['core.config.tab.ui'].capitalize(),
                            PanelComponent(sub_comps, id_='interface'), None, 'core.ui')

    def _gen_general_settings(self, core_config: dict) -> TabComponent:
        locale_keys = translation.get_available_keys()
        locale_opts = [InputOption(label=self.i18n[f'locale.{k}'].capitalize(), value=k) for k in locale_keys]

        current_locale = None

        if core_config['locale']:
            current_locale = [loc for loc in locale_opts if loc.value == core_config['locale']]

        if not current_locale:
            if self.i18n.current_key:
                current_locale = [loc for loc in locale_opts if loc.value == self.i18n.current_key]

            if not current_locale:
                current_locale = [loc for loc in locale_opts if loc.value == self.i18n.default_key]

        current_locale = current_locale[0] if current_locale else None

        sel_locale = SingleSelectComponent(label=self.i18n['core.config.locale.label'],
                                           options=locale_opts,
                                           default_option=current_locale,
                                           type_=SelectViewType.COMBO,
                                           alignment=ViewComponentAlignment.CENTER,
                                           id_='locale')

        sel_store_pwd = self._gen_bool_component(label=self.i18n['core.config.store_password'].capitalize(),
                                                 tooltip=self.i18n['core.config.store_password.tip'].capitalize(),
                                                 id_="store_pwd",
                                                 value=bool(core_config['store_root_password']))

        notify_tip = self.i18n['core.config.system.notifications.tip'].capitalize()
        sel_sys_notify = self._gen_bool_component(label=self.i18n['core.config.system.notifications'].capitalize(),
                                                  tooltip=notify_tip,
                                                  value=bool(core_config['system']['notifications']),
                                                  id_="sys_notify")

        sel_load_apps = self._gen_bool_component(label=self.i18n['core.config.boot.load_apps'],
                                                 tooltip=self.i18n['core.config.boot.load_apps.tip'],
                                                 value=bool(core_config['boot']['load_apps']),
                                                 id_='boot.load_apps')

        sel_sugs = self._gen_bool_component(label=self.i18n['core.config.suggestions.activated'].capitalize(),
                                            tooltip=self.i18n['core.config.suggestions.activated.tip'].capitalize(),
                                            id_="sugs_enabled",
                                            value=bool(core_config['suggestions']['enabled']))

        inp_sugs = TextInputComponent(label=self.i18n['core.config.suggestions.by_type'],
                                      tooltip=self.i18n['core.config.suggestions.by_type.tip'],
                                      value=str(core_config['suggestions']['by_type']),
                                      only_int=True,
                                      id_="sugs_by_type")

        inp_reboot = new_select(label=self.i18n['core.config.updates.reboot'],
                                tip=self.i18n['core.config.updates.reboot.tip'],
                                id_='ask_for_reboot',
                                max_width=None,
                                value=bool(core_config['updates']['ask_for_reboot']),
                                opts=[(self.i18n['ask'].capitalize(), True, None),
                                      (self.i18n['no'].capitalize(), False, None)])

        inputs = [sel_locale, sel_store_pwd, sel_sys_notify, sel_load_apps, inp_reboot, sel_sugs, inp_sugs]
        panel = PanelComponent([FormComponent(inputs, spaces=False)], id_='general')
        return TabComponent(self.i18n['core.config.tab.general'].capitalize(), panel, None, 'core.gen')

    def _gen_bool_component(self, label: str, tooltip: Optional[str], value: bool, id_: str) -> SingleSelectComponent:

        opts = [InputOption(label=self.i18n['yes'].capitalize(), value=True),
                InputOption(label=self.i18n['no'].capitalize(), value=False)]

        return SingleSelectComponent(label=label,
                                     options=opts,
                                     default_option=[o for o in opts if o.value == value][0],
                                     type_=SelectViewType.RADIO,
                                     tooltip=tooltip,
                                     max_per_line=len(opts),
                                     id_=id_)

    def _save_settings(self, general: PanelComponent,
                       advanced: PanelComponent,
                       backup: PanelComponent,
                       ui: PanelComponent,
                       tray: PanelComponent,
                       gems_panel: PanelComponent) -> Tuple[bool, Optional[List[str]]]:
        core_config = self.configman.get_config()

        # general
        gen_form = general.get_component_by_idx(0, FormComponent)

        locale = gen_form.get_component('locale', SingleSelectComponent).get_selected()

        if locale != self.i18n.current_key:
            core_config['locale'] = locale

        notifications = gen_form.get_component('sys_notify', SingleSelectComponent).get_selected()
        core_config['system']['notifications'] = notifications

        suggestions = gen_form.get_component('sugs_enabled', SingleSelectComponent).get_selected()
        core_config['suggestions']['enabled'] = suggestions

        store_root_pwd = gen_form.get_component('store_pwd', SingleSelectComponent).get_selected()
        core_config['store_root_password'] = store_root_pwd

        sugs_by_type = gen_form.get_component('sugs_by_type', TextInputComponent).get_int_value()
        core_config['suggestions']['by_type'] = sugs_by_type

        ask_reboot = gen_form.get_component('ask_for_reboot', SingleSelectComponent).get_selected()
        core_config['updates']['ask_for_reboot'] = ask_reboot

        load_apps = gen_form.get_component('boot.load_apps', SingleSelectComponent).get_selected()
        core_config['boot']['load_apps'] = load_apps

        # advanced
        adv_form = advanced.get_component_by_idx(0, FormComponent)

        download_mthreaded = adv_form.get_component('down_mthread', SingleSelectComponent).get_selected()
        core_config['download']['multithreaded'] = download_mthreaded

        mthread_client = adv_form.get_component('mthread_client', SingleSelectComponent).get_selected()
        core_config['download']['multithreaded_client'] = mthread_client

        check_ssl = adv_form.get_component('download.check_ssl', SingleSelectComponent).get_selected()
        core_config['download']['check_ssl'] = check_ssl

        if isinstance(self.file_downloader, AdaptableFileDownloader):
            self.file_downloader.multithread_client = mthread_client
            self.file_downloader.multithread_enabled = download_mthreaded
            self.file_downloader.check_ssl = check_ssl

        single_dep_check = adv_form.get_component('dep_check', SingleSelectComponent).get_selected()
        core_config['system']['single_dependency_checking'] = single_dep_check

        data_exp = adv_form.get_component('data_exp', TextInputComponent).get_int_value()
        core_config['memory_cache']['data_expiration'] = data_exp

        icon_exp = adv_form.get_component('icon_exp', TextInputComponent).get_int_value()
        core_config['memory_cache']['icon_expiration'] = icon_exp

        trim_after_upgrade = adv_form.get_component('trim_after_upgrade', SingleSelectComponent).get_selected()
        core_config['disk']['trim']['after_upgrade'] = trim_after_upgrade

        # backup
        if backup:
            bkp_form = backup.get_component_by_idx(0, FormComponent)

            core_config['backup']['enabled'] = bkp_form.get_component('enabled', SingleSelectComponent).get_selected()
            core_config['backup']['mode'] = bkp_form.get_component('mode', SingleSelectComponent).get_selected()
            core_config['backup']['type'] = bkp_form.get_component('type', SingleSelectComponent).get_selected()
            core_config['backup']['install'] = bkp_form.get_component('install', SingleSelectComponent).get_selected()
            core_config['backup']['upgrade'] = bkp_form.get_component('upgrade', SingleSelectComponent).get_selected()

            bkp_remove_method = bkp_form.get_component('remove_method', SingleSelectComponent).get_selected()
            core_config['backup']['remove_method'] = bkp_remove_method

            bkp_uninstall = bkp_form.get_component('uninstall', SingleSelectComponent).get_selected()
            core_config['backup']['uninstall'] = bkp_uninstall

            bkp_downgrade = bkp_form.get_component('downgrade', SingleSelectComponent).get_selected()
            core_config['backup']['downgrade'] = bkp_downgrade

        # tray
        tray_form = tray.get_component_by_idx(0, FormComponent)

        updates_interval = tray_form.get_component('updates_interval', TextInputComponent).get_int_value()
        core_config['updates']['check_interval'] = updates_interval

        def_icon_path = tray_form.get_component('def_icon', FileChooserComponent).file_path
        core_config['ui']['tray']['default_icon'] = def_icon_path if def_icon_path else None

        up_icon_path = tray_form.get_component('up_icon', FileChooserComponent).file_path
        core_config['ui']['tray']['updates_icon'] = up_icon_path if up_icon_path else None

        # ui
        ui_form = ui.get_component_by_idx(0, FormComponent)

        core_config['download']['icons'] = ui_form.get_component('down_icons', SingleSelectComponent).get_selected()
        core_config['ui']['hdpi'] = ui_form.get_component('hdpi', SingleSelectComponent).get_selected()

        previous_autoscale = core_config['ui']['auto_scale']

        core_config['ui']['auto_scale'] = ui_form.get_component('auto_scale', SingleSelectComponent).get_selected()

        if previous_autoscale and not core_config['ui']['auto_scale']:
            self.logger.info("Deleting environment variable QT_AUTO_SCREEN_SCALE_FACTOR")
            del os.environ['QT_AUTO_SCREEN_SCALE_FACTOR']

        core_config['ui']['scale_factor'] = ui_form.get_component('scalef').value / 100

        table_max = ui_form.get_component('table_max', TextInputComponent).get_int_value()
        core_config['ui']['table']['max_displayed'] = table_max

        style = ui_form.get_component('style', SingleSelectComponent).get_selected()

        if core_config['ui']['qt_style']:
            cur_style = core_config['ui']['qt_style']
        else:
            cur_style = QApplication.instance().property('qt_style')

        if style != cur_style:
            core_config['ui']['qt_style'] = style
            QApplication.instance().setProperty('qt_style', style)

        core_config['ui']['system_theme'] = ui_form.get_component('system_theme', SingleSelectComponent).get_selected()

        # gems
        checked_gems = gems_panel.components[1].get_component('gems', MultipleSelectComponent).get_selected_values()

        for man in self.managers:
            modname = man.__module__.split('.')[-2]
            enabled = modname in checked_gems
            man.set_enabled(enabled)

        if core_config['gems'] is None and len(checked_gems) == len(self.managers):
            sel_gems = None
        else:
            sel_gems = checked_gems

        core_config['gems'] = sel_gems

        try:
            self.configman.save_config(core_config)
            return True, None
        except Exception:
            return False, [traceback.format_exc()]

    def _save_views(self, views: Iterable[SettingsView], success_list: List[bool], warnings: List[str]):
        success = False

        for view in views:
            try:
                res = view.save()

                if res:
                    success, errors = res[0], res[1]

                    if errors:
                        warnings.extend(errors)
            except Exception:
                self.logger.error(f"An exception happened while {view.controller.__class__.__name__}"
                                  f" was trying to save settings")
                traceback.print_exc()
            finally:
                success_list.append(success)

    def _save_core_settings(self, tabs: TabGroupComponent, success_list: List[bool], warnings: List[str]):
        success = False

        try:
            bkp = tabs.get_tab('core.bkp')
            success, errors = self._save_settings(general=tabs.get_tab('core.gen').get_content(PanelComponent),
                                                  advanced=tabs.get_tab('core.adv').get_content(PanelComponent),
                                                  tray=tabs.get_tab('core.tray').get_content(PanelComponent),
                                                  backup=bkp.get_content(PanelComponent) if bkp else None,
                                                  ui=tabs.get_tab('core.ui').get_content(PanelComponent),
                                                  gems_panel=tabs.get_tab('core.types').get_content(PanelComponent))
            if errors:
                warnings.extend(errors)

        except Exception:
            self.logger.error("An exception happened while saving the core settings")
            traceback.print_exc()
        finally:
            success_list.append(success)

    def save_settings(self, component: TabGroupComponent) -> Tuple[bool, Optional[List[str]]]:
        ti = time.time()
        save_threads, warnings, success_list = [], [], []

        save_core = Thread(target=self._save_core_settings, args=(component, success_list, warnings))
        save_core.start()
        save_threads.append(save_core)

        if self._settings_views:

            for views in self._settings_views.values():
                save_view = Thread(target=self._save_views, args=(views, success_list, warnings))
                save_view.start()
                save_threads.append(save_view)

        for t in save_threads:
            t.join()

        success = all(success_list)
        tf = time.time()
        self.logger.info(f"Saving all settings took {tf - ti:.8f} seconds")
        return success, warnings

    def _gen_backup_settings(self, core_config: dict) -> Optional[TabComponent]:
        if timeshift.is_available():
            enabled_opt = self._gen_bool_component(label=self.i18n['core.config.backup'],
                                                   tooltip=None,
                                                   value=bool(core_config['backup']['enabled']),
                                                   id_='enabled')

            ops_opts = [(self.i18n['yes'].capitalize(), True, None),
                        (self.i18n['no'].capitalize(), False, None),
                        (self.i18n['ask'].capitalize(), None, None)]

            install_mode = new_select(label=self.i18n['core.config.backup.install'],
                                      tip=None,
                                      value=core_config['backup']['install'],
                                      opts=ops_opts,
                                      id_='install')

            uninstall_mode = new_select(label=self.i18n['core.config.backup.uninstall'],
                                        tip=None,
                                        value=core_config['backup']['uninstall'],
                                        opts=ops_opts,
                                        id_='uninstall')

            upgrade_mode = new_select(label=self.i18n['core.config.backup.upgrade'],
                                      tip=None,
                                      value=core_config['backup']['upgrade'],
                                      opts=ops_opts,
                                      id_='upgrade')

            downgrade_mode = new_select(label=self.i18n['core.config.backup.downgrade'],
                                        tip=None,
                                        value=core_config['backup']['downgrade'],
                                        opts=ops_opts,
                                        id_='downgrade')

            mode = new_select(label=self.i18n['core.config.backup.mode'],
                              tip=None,
                              value=core_config['backup']['mode'],
                              opts=[
                                  (self.i18n['core.config.backup.mode.incremental'], 'incremental',
                                   self.i18n['core.config.backup.mode.incremental.tip']),
                                  (self.i18n['core.config.backup.mode.only_one'], 'only_one',
                                   self.i18n['core.config.backup.mode.only_one.tip'])
                              ],
                              id_='mode')
            type_ = new_select(label=self.i18n['type'].capitalize(),
                               tip=None,
                               value=core_config['backup']['type'],
                               opts=[('rsync', 'rsync', None), ('btrfs', 'btrfs', None)],
                               id_='type')

            remove_method = core_config['backup']['remove_method']

            if not remove_method or remove_method not in BACKUP_REMOVE_METHODS:
                remove_method = BACKUP_DEFAULT_REMOVE_METHOD

            remove_i18n = 'core.config.backup.remove_method'
            remove_opts = ((self.i18n[f'{remove_i18n}.{m}'], m, self.i18n[f'{remove_i18n}.{m}.tip'])
                           for m in sorted(BACKUP_REMOVE_METHODS))

            remove_label = f'{self.i18n[remove_i18n]} ({self.i18n["core.config.backup.mode"]} ' \
                           f'"{self.i18n["core.config.backup.mode.only_one"].capitalize()}")'

            sel_remove = new_select(label=remove_label,
                                    tip=None,
                                    value=remove_method,
                                    opts=remove_opts,
                                    capitalize_label=False,
                                    id_='remove_method')

            inputs = [enabled_opt, type_, mode, sel_remove, install_mode, uninstall_mode, upgrade_mode, downgrade_mode]
            panel = PanelComponent([FormComponent(inputs, spaces=False)], id_='backup')
            return TabComponent(self.i18n['core.config.tab.backup'].capitalize(), panel, None, 'core.bkp')
