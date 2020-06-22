from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QPushButton

from bauh import ROOT_DIR
from bauh.api.abstract.view import MultipleSelectComponent, InputOption
from bauh.view.core.config import save
from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.util import resource
from bauh.view.qt import qt_utils, css
from bauh.view.qt.components import MultipleSelectQt, CheckboxQt, new_spacer
from bauh.view.util.translation import I18n


class GemSelectorPanel(QWidget):

    def __init__(self, window: QWidget, manager: GenericSoftwareManager, i18n: I18n, config: dict, show_panel_after_restart: bool = False):
        super(GemSelectorPanel, self).__init__()
        self.window = window
        self.manager = manager
        self.config = config
        self.setLayout(QGridLayout())
        self.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))
        self.setWindowTitle(i18n['gem_selector.title'])
        self.resize(400, 400)
        self.show_panel_after_restart = show_panel_after_restart

        self.label_question = QLabel(i18n['gem_selector.question'])
        self.label_question.setStyleSheet('QLabel { font-weight: bold}')
        self.layout().addWidget(self.label_question, 0, 1, Qt.AlignHCenter)

        self.bt_proceed = QPushButton(i18n['change'].capitalize())
        self.bt_proceed.setStyleSheet(css.OK_BUTTON)
        self.bt_proceed.clicked.connect(self.save)

        self.bt_exit = QPushButton(i18n['close'].capitalize())
        self.bt_exit.clicked.connect(self.exit)

        self.gem_map = {}
        gem_options = []
        default = set()

        managers = [*manager.managers]
        managers.sort(key=lambda c: c.__class__.__name__)

        for m in managers:
            if m.can_work():
                modname = m.__module__.split('.')[-2]
                op = InputOption(label=i18n.get('gem.{}.label'.format(modname), modname.capitalize()),
                                 tooltip=i18n.get('gem.{}.info'.format(modname)),
                                 value=modname,
                                 icon_path='{r}/gems/{n}/resources/img/{n}.svg'.format(r=ROOT_DIR, n=modname))

                gem_options.append(op)
                self.gem_map[modname] = m

                if m.is_enabled() and m in manager.working_managers:
                    default.add(op)

        if self.config['gems']:
            default_ops = {o for o in gem_options if o.value in self.config['gems']}
        else:
            default_ops = default

        self.bt_proceed.setEnabled(bool(default_ops))

        self.gem_select_model = MultipleSelectComponent(label='', options=gem_options, default_options=default_ops, max_per_line=1)

        self.gem_select = MultipleSelectQt(self.gem_select_model, self.check_state)
        self.layout().addWidget(self.gem_select, 1, 1)

        self.layout().addWidget(new_spacer(), 2, 1)

        self.layout().addWidget(self.bt_proceed, 3, 1, Qt.AlignRight)
        self.layout().addWidget(self.bt_exit, 3, 1, Qt.AlignLeft)

        self.adjustSize()
        self.setFixedSize(self.size())
        qt_utils.centralize(self)

    def check_state(self, model: CheckboxQt, checked: bool):
        if self.isVisible():
            self.bt_proceed.setEnabled(bool(self.gem_select_model.values))

    def save(self):
        enabled_gems = [op.value for op in self.gem_select_model.values]

        for module, man in self.gem_map.items():
            enabled = module in enabled_gems
            man.set_enabled(enabled)

        self.config['gems'] = enabled_gems
        save(self.config)

        self.manager.reset_cache()
        self.manager.prepare()
        self.window.verify_warnings()
        self.window.types_changed = True
        self.window.begin_refresh_packages()
        self.close()

    def exit(self):
        self.close()
