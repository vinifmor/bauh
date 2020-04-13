import os
import time
import traceback
from pathlib import Path
from threading import Thread
from typing import Tuple

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QIntValidator
from PyQt5.QtWidgets import QRadioButton, QGroupBox, QCheckBox, QComboBox, QGridLayout, QWidget, \
    QLabel, QSizePolicy, QLineEdit, QToolButton, QHBoxLayout, QFormLayout, QFileDialog, QTabWidget, QVBoxLayout, \
    QSlider, QScrollArea, QFrame

from bauh.api.abstract.view import SingleSelectComponent, InputOption, MultipleSelectComponent, SelectViewType, \
    TextInputComponent, FormComponent, FileChooserComponent, ViewComponent, TabGroupComponent, PanelComponent, \
    TwoStateButtonComponent, TextComponent, SpacerComponent
from bauh.view.qt import css
from bauh.view.util import resource
from bauh.view.util.translation import I18n


class RadioButtonQt(QRadioButton):

    def __init__(self, model: InputOption, model_parent: SingleSelectComponent):
        super(RadioButtonQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.toggled.connect(self._set_checked)

        if model.icon_path:
            self.setIcon(QIcon(model.icon_path))

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


class TwoStateButtonQt(QSlider):

    def __init__(self, model: TwoStateButtonComponent):
        super(TwoStateButtonQt, self).__init__(Qt.Horizontal)
        self.model = model
        self.setMaximum(1)
        self.valueChanged.connect(self._change_state)

    def mousePressEvent(self, QMouseEvent):
        self.setValue(1 if self.value() == 0 else 0)

    def _change_state(self, state: int):
        self.model.state = bool(state)


class FormComboBoxQt(QComboBox):

    def __init__(self, model: SingleSelectComponent):
        super(FormComboBoxQt, self).__init__()
        self.model = model

        if model.max_width > 0:
            self.setMaximumWidth(model.max_width)

        for idx, op in enumerate(self.model.options):
            icon = QIcon(op.icon_path) if op.icon_path else QIcon()
            self.addItem(icon, op.label, op.value)

            if op.tooltip:
                self.setItemData(idx, op.tooltip, Qt.ToolTipRole)

            if model.value and model.value == op:  # default
                self.setCurrentIndex(idx)
                self.setToolTip(model.value.tooltip)

        self.currentIndexChanged.connect(self._set_selected)

    def _set_selected(self, idx: int):
        self.model.value = self.model.options[idx]
        self.setToolTip(self.model.value.tooltip)


class FormRadioSelectQt(QWidget):

    def __init__(self, model: SingleSelectComponent, parent: QWidget = None):
        super(FormRadioSelectQt, self).__init__(parent=parent)
        self.model = model
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        if model.max_width > 0:
            self.setMaximumWidth(model.max_width)

        grid = QGridLayout()
        self.setLayout(grid)

        line, col = 0, 0
        for op in model.options:
            comp = RadioButtonQt(op, model)
            comp.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
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

        if model.max_width <= 0:
            self.setMaximumWidth(self.sizeHint().width())


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
        self.layout().addWidget(QLabel(model.label + ' :' if model.label else ''), 0, 0)
        self.layout().addWidget(FormComboBoxQt(model), 0, 1)


class TextInputQt(QGroupBox):

    def __init__(self, model: TextInputComponent):
        super(TextInputQt, self).__init__()
        self.model = model
        self.setLayout(QGridLayout())
        self.setStyleSheet('QGridLayout {margin-left: 0} QLabel { font-weight: bold}')
        self.layout().addWidget(QLabel(model.label.capitalize() + ' :' if model.label else ''), 0, 0)

        if self.model.max_width > 0:
            self.setMaximumWidth(self.model.max_width)

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


class MultipleSelectQt(QGroupBox):

    def __init__(self, model: MultipleSelectComponent, callback):
        super(MultipleSelectQt, self).__init__(model.label if model.label else None)
        self.setStyleSheet(css.GROUP_BOX)
        self.model = model
        self._layout = QGridLayout()
        self.setLayout(self._layout)

        if model.max_width > 0:
            self.setMaximumWidth(model.max_width)

        if model.max_height > 0:
            self.setMaximumHeight(model.max_height)

        if model.label:
            line = 1
            pre_label = QLabel()
            self.layout().addWidget(pre_label, 0, 1)
        else:
            line = 0

        col = 0

        pixmap_help = QPixmap()

        for op in model.options:  # loads the help icon if at least one option has a tooltip
            if op.tooltip:
                try:
                    pixmap_help = QIcon(resource.get_path('img/about.svg')).pixmap(QSize(16, 16))
                except:
                    traceback.print_exc()

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
            pos_label = QLabel()
            self.layout().addWidget(pos_label, line + 1, 1)


class FormMultipleSelectQt(QWidget):

    def __init__(self, model: MultipleSelectComponent, parent: QWidget = None):
        super(FormMultipleSelectQt, self).__init__(parent=parent)
        self.model = model
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        if model.max_width > 0:
            self.setMaximumWidth(model.max_width)

        if model.max_height > 0:
            self.setMaximumHeight(model.max_height)

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
                try:
                    pixmap_help = QIcon(resource.get_path('img/about.svg')).pixmap(QSize(16, 16))
                except:
                    traceback.print_exc()

                break

        for op in model.options:
            comp = CheckboxQt(op, model, None)

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
        self.typing = None

    def notify_text_change(self):
        time.sleep(2)
        text = self.text().strip()

        if text != self.last_text:
            self.last_text = text
            self.on_key_press()

        self.typing = None

    def keyPressEvent(self, event):
        super(InputFilter, self).keyPressEvent(event)

        if self.typing:
            return

        self.typing = Thread(target=self.notify_text_change, daemon=True)
        self.typing.start()

    def get_text(self):
        return self.last_text

    def setText(self, p_str):
        super(InputFilter, self).setText(p_str)
        self.last_text = p_str


class IconButton(QWidget):

    def __init__(self, icon: QIcon, action, i18n: I18n, background: str = None, align: int = Qt.AlignCenter, tooltip: str = None, expanding: bool = False):
        super(IconButton, self).__init__()
        self.bt = QToolButton()
        self.bt.setIcon(icon)
        self.bt.clicked.connect(action)
        self.i18n = i18n
        self.default_tootip = tooltip
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.bt.setSizePolicy(QSizePolicy.Expanding if expanding else QSizePolicy.Minimum, QSizePolicy.Minimum)

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

        if model.spaces:
            self.layout().addRow(QLabel(), QLabel())

        for c in model.components:
            if isinstance(c, TextInputComponent):
                label, field = self._new_text_input(c)
                self.layout().addRow(label, field)
            elif isinstance(c, SingleSelectComponent):
                label = self._new_label(c)
                field = FormComboBoxQt(c) if c.type == SelectViewType.COMBO else FormRadioSelectQt(c)
                self.layout().addRow(label, self._wrap(field, c))
            elif isinstance(c, FileChooserComponent):
                label, field = self._new_file_chooser(c)
                self.layout().addRow(label, field)
            elif isinstance(c, FormComponent):
                self.layout().addRow(FormQt(c, self.i18n))
            elif isinstance(c, TwoStateButtonComponent):
                label = self._new_label(c)
                self.layout().addRow(label, TwoStateButtonQt(c))
            elif isinstance(c, MultipleSelectComponent):
                label = self._new_label(c)
                self.layout().addRow(label, FormMultipleSelectQt(c))
            elif isinstance(c, TextComponent):
                self.layout().addRow(self._new_label(c), QWidget())
            else:
                raise Exception('Unsupported component type {}'.format(c.__class__.__name__))

        if model.spaces:
            self.layout().addRow(QLabel(), QLabel())

    def _new_label(self, comp) -> QWidget:
        label = QWidget()
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label.setLayout(QHBoxLayout())
        label_comp = QLabel()
        label.layout().addWidget(label_comp)

        if hasattr(comp, 'size') and comp.size is not None:
            label_comp.setStyleSheet("QLabel { font-size: " + str(comp.size) + "px }")

        attr = 'label' if hasattr(comp,'label') else 'value'
        text = getattr(comp, attr)

        if text:
            if hasattr(comp, 'capitalize_label') and getattr(comp, 'capitalize_label'):
                label_comp.setText(text.capitalize())
            else:
                label_comp.setText(text)

            if comp.tooltip:
                label.layout().addWidget(self.gen_tip_icon(comp.tooltip))

        return label

    def gen_tip_icon(self, tip: str) -> QLabel:
        tip_icon = QLabel()
        tip_icon.setToolTip(tip.strip())

        try:
            tip_icon.setPixmap(QIcon(resource.get_path('img/about.svg')).pixmap(QSize(12, 12)))
        except:
            traceback.print_exc()

        return tip_icon

    def _new_text_input(self, c: TextInputComponent) -> Tuple[QLabel, QLineEdit]:
        line_edit = QLineEdit()

        if c.only_int:
            line_edit.setValidator(QIntValidator())

        if c.tooltip:
            line_edit.setToolTip(c.tooltip)

        if c.placeholder:
            line_edit.setPlaceholderText(c.placeholder)

        if c.value:
            line_edit.setText(str(c.value) if c.value else '')
            line_edit.setCursorPosition(0)

        if c.read_only:
            line_edit.setEnabled(False)

        def update_model(text: str):
            c.value = text

        line_edit.textChanged.connect(update_model)

        label = QWidget()
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label.setLayout(QHBoxLayout())

        label_component = QLabel()
        label.layout().addWidget(label_component)

        if label:
            label_component.setText(c.label.capitalize())

            if c.tooltip:
                label.layout().addWidget(self.gen_tip_icon(c.tooltip))

        return label, self._wrap(line_edit, c)

    def _wrap(self, comp: QWidget, model: ViewComponent) -> QWidget:
        field_container = QWidget()
        field_container.setLayout(QHBoxLayout())

        if model.max_width > 0:
            field_container.setMaximumWidth(model.max_width)

        field_container.layout().addWidget(comp)
        return field_container

    def _new_file_chooser(self, c: FileChooserComponent) -> Tuple[QLabel, QLineEdit]:
        chooser = QLineEdit()
        chooser.setReadOnly(True)

        if c.max_width > 0:
            chooser.setMaximumWidth(c.max_width)

        if c.file_path:
            chooser.setText(c.file_path)

        chooser.setPlaceholderText(self.i18n['view.components.file_chooser.placeholder'])

        def open_chooser(e):
            options = QFileDialog.Options()

            if c.allowed_extensions:
                exts = ';;'.join({'*.{}'.format(e) for e in c.allowed_extensions})
            else:
                exts = '{}} (*);;'.format(self.i18n['all_files'].capitalize())

            if c.file_path and os.path.isfile(c.file_path):
                cur_path = c.file_path
            else:
                cur_path = str(Path.home())

            file_path, _ = QFileDialog.getOpenFileName(self, self.i18n['file_chooser.title'], cur_path, exts, options=options)

            if file_path:
                c.file_path = file_path
                chooser.setText(file_path)

            chooser.setCursorPosition(0)

        def clean_path():
            c.file_path = None
            chooser.setText('')

        chooser.mousePressEvent = open_chooser

        label = self._new_label(c)
        wrapped = self._wrap(chooser, c)

        try:
            icon = QIcon(resource.get_path('img/clean.svg'))
        except:
            traceback.print_exc()
            icon = QIcon()

        bt = IconButton(icon, i18n=self.i18n['clean'].capitalize(), action=clean_path, background='#cc0000', tooltip=self.i18n['action.run.tooltip'])

        wrapped.layout().addWidget(bt)
        return label, wrapped


class TabGroupQt(QTabWidget):

    def __init__(self, model: TabGroupComponent, i18n: I18n, parent: QWidget = None):
        super(TabGroupQt, self).__init__(parent=parent)
        self.model = model
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.setTabPosition(QTabWidget.North)

        for c in model.tabs:
            try:
                icon = QIcon(c.icon_path) if c.icon_path else QIcon()
            except:
                traceback.print_exc()
                icon = QIcon()

            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(to_widget(c.content, i18n))
            self.addTab(scroll, icon, c.label)


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
    elif isinstance(comp, TwoStateButtonComponent):
        return TwoStateButtonQt(comp)
    elif isinstance(comp, TextComponent):
        label = QLabel(comp.value)

        if comp.size is not None:
            label.setStyleSheet("QLabel { font-size: " + str(comp.size) + "px }")

        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        return label
    elif isinstance(comp, SpacerComponent):
        return new_spacer()
    else:
        raise Exception("Cannot render instances of " + comp.__class__.__name__)
