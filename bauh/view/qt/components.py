from pathlib import Path
from typing import Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QIntValidator
from PyQt5.QtWidgets import QRadioButton, QGroupBox, QCheckBox, QComboBox, QGridLayout, QWidget, \
    QLabel, QSizePolicy, QLineEdit, QToolButton, QHBoxLayout, QFormLayout, QFileDialog, QTabWidget, QVBoxLayout

from bauh.api.abstract.view import SingleSelectComponent, InputOption, MultipleSelectComponent, SelectViewType, \
    TextInputComponent, FormComponent, FileChooserComponent, ViewComponent, TabGroupComponent, PanelComponent
from bauh.view.qt import css
from bauh.view.util import resource
from bauh.view.util.translation import I18n


class RadioButtonQt(QRadioButton):

    def __init__(self, model: InputOption, model_parent: SingleSelectComponent):
        super(RadioButtonQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.toggled.connect(self._set_checked)

        if self.model.read_only:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.setFocusPolicy(Qt.NoFocus)

    def _set_checked(self, checked: bool):
        if checked:
            self.model_parent.value = self.model


class CheckboxQt(QCheckBox):

    def __init__(self, model: InputOption, model_parent: MultipleSelectComponent, callback):
        super(CheckboxQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.stateChanged.connect(self._set_checked)
        self.callback = callback
        self.setText(model.label)
        self.setToolTip(model.tooltip)

        if model.icon_path:
            self.setIcon(QIcon(model.icon_path))

        if model.read_only:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.setFocusPolicy(Qt.NoFocus)

    def _set_checked(self, state):
        checked = state == 2

        if checked:
            self.model_parent.values.add(self.model)
        else:
            if self.model in self.model_parent.values:
                self.model_parent.values.remove(self.model)

        if self.callback:
            self.callback(self.model, checked)


class ComboBoxQt(QComboBox):

    def __init__(self, model: SingleSelectComponent):
        super(ComboBoxQt, self).__init__()
        self.model = model
        for idx, op in enumerate(self.model.options):
            self.addItem(op.label, op.value)

            if op.tooltip:
                self.setItemData(idx, op.tooltip, Qt.ToolTipRole)

            if model.value and model.value == op:  # default
                self.setCurrentIndex(idx)
                self.setToolTip(model.value.tooltip)

        self.currentIndexChanged.connect(self._set_selected)

    def _set_selected(self, idx: int):
        self.model.value = self.model.options[idx]
        self.setToolTip(self.model.value.tooltip)


class RadioBoxQt(QWidget):

    def __init__(self, model: SingleSelectComponent, parent: QWidget = None):
        super(RadioBoxQt, self).__init__(parent=parent)
        self.model = model

        grid = QGridLayout()
        self.setLayout(grid)

        line, col = 0, 0
        for op in model.options:
            comp = RadioButtonQt(op, model)
            comp.setText(op.label)
            comp.setToolTip(op.tooltip)

            if model.value and model.value == op:
                self.value = comp
                comp.setChecked(True)

            grid.addWidget(comp, line, col)

            if col + 1 == self.model.max_per_line:
                line += 1
                col = 0
            else:
                col += 1


class RadioSelectQt(QGroupBox):

    def __init__(self, model: SingleSelectComponent):
        super(RadioSelectQt, self).__init__(model.label + ' :' if model.label else None)
        self.model = model
        self.setStyleSheet("QGroupBox { font-weight: bold }")

        grid = QGridLayout()
        self.setLayout(grid)

        line, col = 0, 0
        for op in model.options:
            comp = RadioButtonQt(op, model)
            comp.setText(op.label)
            comp.setToolTip(op.tooltip)

            if model.value and model.value == op:
                self.value = comp
                comp.setChecked(True)

            grid.addWidget(comp, line, col)

            if col + 1 == self.model.max_per_line:
                line += 1
                col = 0
            else:
                col += 1


class ComboSelectQt(QGroupBox):

    def __init__(self, model: SingleSelectComponent):
        super(ComboSelectQt, self).__init__()
        self.model = model
        self.setLayout(QGridLayout())
        self.setStyleSheet('QGridLayout {margin-left: 0} QLabel { font-weight: bold}')
        self.layout().addWidget(QLabel(model.label + ' :'), 0, 0)
        self.layout().addWidget(ComboBoxQt(model), 0, 1)


class TextInputQt(QGroupBox):

    def __init__(self, model: TextInputComponent):
        super(TextInputQt, self).__init__()
        self.model = model
        self.setLayout(QGridLayout())
        self.setStyleSheet('QGridLayout {margin-left: 0} QLabel { font-weight: bold}')
        self.layout().addWidget(QLabel(model.label.capitalize() + ' :' if model.label else ''), 0, 0)

        self.text_input = QLineEdit()

        if model.only_int:
            self.text_input.setValidator(QIntValidator())

        if model.placeholder:
            self.text_input.setPlaceholderText(model.placeholder)

        if model.tooltip:
            self.text_input.setToolTip(model.tooltip)

        if model.value:
            self.text_input.setText(model.value)
            self.text_input.setCursorPosition(0)

        self.text_input.textChanged.connect(self._update_model)

        self.layout().addWidget(self.text_input, 0, 1)

    def _update_model(self, text: str):
        self.model.value = text

# class ComboSelectQt(QGroupBox):
#
#     def __init__(self, model: SingleSelectComponent):
#         super(ComboSelectQt, self).__init__(model.label + ' :')
#         self.model = model
#         self.setLayout(QGridLayout())
#         self.setStyleSheet('QGridLayout {margin-left: 0} QLabel { font-weight: bold}')
#         self.layout().addWidget(ComboBoxQt(model), 0, 1)


class MultipleSelectQt(QGroupBox):

    def __init__(self, model: MultipleSelectComponent, callback):
        super(MultipleSelectQt, self).__init__(model.label if model.label else None)
        self.setStyleSheet(css.GROUP_BOX)
        self.model = model
        self._layout = QGridLayout()
        self.setLayout(self._layout)

        if model.label:
            line = 1
            self.layout().addWidget(QLabel(), 0, 1)
        else:
            line = 0

        col = 0

        pixmap_help = QPixmap()

        for op in model.options:  # loads the help icon if at least one option has a tooltip
            if op.tooltip:
                with open(resource.get_path('img/about.svg'), 'rb') as f:
                    pixmap_help.loadFromData(f.read())
                    pixmap_help = pixmap_help.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                break

        for op in model.options:
            comp = CheckboxQt(op, model, callback)

            if model.values and op in model.values:
                self.value = comp
                comp.setChecked(True)

            widget = QWidget()
            widget.setLayout(QHBoxLayout())
            widget.layout().addWidget(comp)

            if op.tooltip:
                help_icon = QLabel()
                help_icon.setPixmap(pixmap_help)
                help_icon.setToolTip(op.tooltip)
                widget.layout().addWidget(help_icon)

            self._layout.addWidget(widget, line, col)

            if col + 1 == self.model.max_per_line:
                line += 1
                col = 0
            else:
                col += 1

        if model.label:
            self.layout().addWidget(QLabel(), line + 1, 1)


class InputFilter(QLineEdit):

    def __init__(self, on_key_press):
        super(InputFilter, self).__init__()
        self.on_key_press = on_key_press
        self.last_text = ''

    def keyPressEvent(self, event):
        super(InputFilter, self).keyPressEvent(event)
        text = self.text().strip()

        if text != self.last_text:
            self.last_text = text
            self.on_key_press()

    def get_text(self):
        return self.last_text

    def setText(self, p_str):
        super(InputFilter, self).setText(p_str)
        self.last_text = p_str


class IconButton(QWidget):

    def __init__(self, icon: QIcon, action, i18n: I18n, background: str = None, align: int = Qt.AlignCenter, tooltip: str = None):
        super(IconButton, self).__init__()
        self.bt = QToolButton()
        self.bt.setIcon(icon)
        self.bt.clicked.connect(action)
        self.i18n = i18n
        self.default_tootip = tooltip
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.bt.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        if background:
            style = 'QToolButton { color: white; background: ' + background + '} '
            style += 'QToolButton:disabled { color: white; background: grey }'
            self.bt.setStyleSheet(style)

        if tooltip:
            self.bt.setToolTip(tooltip)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(align)
        layout.addWidget(self.bt)
        self.setLayout(layout)

    def setEnabled(self, enabled):
        super(IconButton, self).setEnabled(enabled)

        if not enabled:
            self.bt.setToolTip(self.i18n['icon_button.tooltip.disabled'])
        else:
            self.bt.setToolTip(self.default_tootip)


class PanelQt(QWidget):

    def __init__(self, model: PanelComponent, i18n: I18n, parent: QWidget = None):
        super(PanelQt, self).__init__(parent=parent)
        self.model = model
        self.i18n = i18n
        self.setLayout(QVBoxLayout())
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        if model.components:
            for c in model.components:
                self.layout().addWidget(to_widget(c, i18n))


class FormQt(QGroupBox):

    def __init__(self, model: FormComponent, i18n: I18n):
        super(FormQt, self).__init__(model.label if model.label else '')
        self.model = model
        self.i18n = i18n
        self.setLayout(QFormLayout())
        self.setStyleSheet(css.GROUP_BOX)

        self.layout().addRow(QLabel(), QLabel())

        for c in model.components:
            if isinstance(c, TextInputComponent):
                label, field = self._new_text_input(c)
                self.layout().addRow(label, field)
            elif isinstance(c, SingleSelectComponent):
                label = QLabel(c.label.capitalize() if c.label else '')
                field = ComboBoxQt(c) if c.type == SelectViewType.COMBO else RadioBoxQt(c)
                self.layout().addRow(label, field)
            elif isinstance(c, FileChooserComponent):
                label, field = self._new_file_chooser(c)
                self.layout().addRow(label, field)
            elif isinstance(c, FormComponent):
                self.layout().addRow(FormQt(c, self.i18n))
            else:
                raise Exception('Unsupported component type {}'.format(c.__class__.__name__))

        self.layout().addRow(QLabel(), QLabel())

    def _new_text_input(self, c: TextInputComponent) -> Tuple[QLabel, QLineEdit]:
        line_edit = QLineEdit()

        if c.only_int:
            line_edit.setValidator(QIntValidator())

        if c.tooltip:
            line_edit.setToolTip(c.tooltip)

        if c.placeholder:
            line_edit.setPlaceholderText(c.placeholder)

        if c.value:
            line_edit.setText(c.value)
            line_edit.setCursorPosition(0)

        if c.read_only:
            line_edit.setEnabled(False)

        def update_model(text: str):
            c.value = text

        line_edit.textChanged.connect(update_model)
        return QLabel(c.label.capitalize() if c.label else ''), line_edit

    def _new_file_chooser(self, c: FileChooserComponent) -> Tuple[QLabel, QLineEdit]:
        chooser = QLineEdit()
        chooser.setReadOnly(True)

        chooser.setPlaceholderText(self.i18n['view.components.file_chooser.placeholder'])

        def open_chooser(e):
            options = QFileDialog.Options()

            if c.allowed_extensions:
                exts = ';;'.join({'*.{}'.format(e) for e in c.allowed_extensions})
            else:
                exts = '{}} (*);;'.format(self.i18n['all_files'].capitalize())

            file_path, _ = QFileDialog.getOpenFileName(self, self.i18n['file_chooser.title'], str(Path.home()), exts, options=options)

            if file_path:
                c.file_path = file_path
                chooser.setText(file_path)
            else:
                c.file_path = None
                chooser.setText('')

            chooser.setCursorPosition(0)

        chooser.mousePressEvent = open_chooser

        return QLabel(c.label if c.label else ''), chooser


class TabGroupQt(QTabWidget):

    def __init__(self, model: TabGroupComponent, i18n: I18n, parent: QWidget = None):
        super(TabGroupQt, self).__init__(parent=parent)
        self.model = model
        self.setTabPosition(QTabWidget.North)

        for c in model.tabs:
            icon = QIcon(c.icon_path) if c.icon_path else None
            self.addTab(to_widget(c.content, i18n), icon, c.label)


def new_single_select(model: SingleSelectComponent) -> QWidget:
    if model.type == SelectViewType.RADIO:
        return RadioSelectQt(model)
    elif model.type == SelectViewType.COMBO:
        return ComboSelectQt(model)
    else:
        raise Exception("Unsupported type {}".format(model.type))


def new_spacer(min_width: int = None) -> QWidget:
    spacer = QWidget()

    if min_width:
        spacer.setMinimumWidth(min_width)

    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return spacer


def to_widget(comp: ViewComponent, i18n: I18n, parent: QWidget = None) -> QWidget:
    if isinstance(comp, SingleSelectComponent):
        return new_single_select(comp)
    elif isinstance(comp, MultipleSelectComponent):
        return MultipleSelectQt(comp, None)
    elif isinstance(comp, TextInputComponent):
        return TextInputQt(comp)
    elif isinstance(comp, FormComponent):
        return FormQt(comp, i18n)
    elif isinstance(comp, TabGroupComponent):
        return TabGroupQt(comp, i18n, parent)
    elif isinstance(comp, PanelComponent):
        return PanelQt(comp, i18n, parent)
    else:
        raise Exception("Cannot render instances of " + comp.__class__.__name__)
