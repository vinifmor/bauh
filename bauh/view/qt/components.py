import os
import traceback
from pathlib import Path
from typing import Tuple, Dict, Optional, Set

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QIntValidator, QCursor, QFocusEvent
from PyQt5.QtWidgets import QRadioButton, QGroupBox, QCheckBox, QComboBox, QGridLayout, QWidget, \
    QLabel, QSizePolicy, QLineEdit, QToolButton, QHBoxLayout, QFormLayout, QFileDialog, QTabWidget, QVBoxLayout, \
    QSlider, QScrollArea, QFrame, QAction, QSpinBox, QPlainTextEdit, QWidgetAction, QPushButton, QMenu

from bauh.api.abstract.view import SingleSelectComponent, InputOption, MultipleSelectComponent, SelectViewType, \
    TextInputComponent, FormComponent, FileChooserComponent, ViewComponent, TabGroupComponent, PanelComponent, \
    TwoStateButtonComponent, TextComponent, SpacerComponent, RangeInputComponent, ViewObserver, TextInputType
from bauh.view.util.translation import I18n


class QtComponentsManager:

    def __init__(self):
        self.components = {}
        self.groups = {}
        self.group_of_groups = {}
        self._saved_states = {}

    def register_component(self, component_id: int, instance: QWidget, action: Optional[QAction] = None):
        comp = (instance, action, {'v': True, 'e': True, 'r': False})
        self.components[component_id] = comp
        self._save_state(comp)

    def register_group(self, group_id: int, subgroups: bool, *ids: int):
        if not subgroups:
            self.groups[group_id] = {*ids}
        else:
            self.group_of_groups[group_id] = {*ids}

    def get_subgroups(self, root_group: int) -> Set[str]:
        return self.group_of_groups.get(root_group, set())

    def set_components_visible(self, visible: bool, *ids: int):
        if ids:
            for cid in ids:
                self.set_component_visible(cid, visible)
        else:
            for cid in self.components:
                self.set_component_visible(cid, visible)

    def set_component_visible(self, cid: int, visible: bool):
        comp = self.components.get(cid)
        if comp and self._is_visible(comp) != visible:
            self._save_state(comp)
            self._set_visible(comp, visible)

    def set_component_enabled(self, cid: int, enabled: bool):
        comp = self.components.get(cid)
        if comp and self._is_enabled(comp) != enabled:
            self._save_state(comp)
            self._set_enabled(comp, enabled)

    def set_component_read_only(self, cid: int, read_only: bool):
        comp = self.components.get(cid)
        if comp and self._supports_read_only(comp) and self._is_read_only(comp) != read_only:
            self._save_state(comp)
            self._set_read_only(comp, read_only)

    def set_components_enabled(self, enabled: bool, *ids: int):
        if ids:
            for cid in ids:
                self.set_component_enabled(cid, enabled)
        else:
            for cid in self.components:
                self.set_component_enabled(cid, enabled)

    def restore_previous_states(self, *ids: int):
        if ids:
            for cid in ids:
                self.restore_previous_state(cid)
        else:
            for cid in self.components:
                self.restore_previous_state(cid)

    def restore_previous_group_state(self, group_id: int):
        ids = self.groups.get(group_id)

        if ids:
            self.restore_previous_states(*ids)

    def restore_previous_groups_states(self, *groups: int):
        if groups:
            for group in groups:
                self.restore_previous_group_state(group)

    def set_group_visible(self, group_id: int, visible: bool):
        ids = self.groups.get(group_id)

        if ids:
            self.set_components_visible(visible, *ids)

    def set_groups_visible(self, visible: bool, *groups: int):
        if groups:
            for group in groups:
                self.set_group_visible(group, visible)

    def set_group_enabled(self, group_id: int, enabled: bool):
        ids = self.groups.get(group_id)

        if ids:
            self.set_components_enabled(enabled, *ids)

    def restore_previous_state(self, cid: int):
        comp = self.components.get(cid)

        if comp:
            previous_state = {**comp[2]}
            self._restore_state(comp, previous_state)

    def _set_visible(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]], visible: bool):
        if comp[1]:
            comp[1].setVisible(visible)
        else:
            comp[0].setVisible(visible)

    def _set_enabled(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]], enabled: bool):
        comp[0].setEnabled(enabled)

    def _set_read_only(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]], read_only: bool):
        comp[0].setReadOnly(read_only)

    def _supports_read_only(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]]) -> bool:
        return isinstance(comp, QLineEdit)

    def is_visible(self, cid: int) -> bool:
        comp = self.components.get(cid)
        return self._is_visible(comp) if comp else False

    def _is_visible(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]]) -> bool:
        return comp[1].isVisible() if comp[1] else comp[0].isVisible()

    def _is_enabled(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]]) -> bool:
        return comp[0].isEnabled()

    def _is_read_only(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]]) -> bool:
        return comp[0].isReadOnly() if self._supports_read_only(comp) else False

    def _save_state(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]]):
        comp[2]['v'] = self._is_visible(comp)
        comp[2]['e'] = self._is_enabled(comp)
        comp[2]['r'] = self._is_read_only(comp)

    def list_visible_from_group(self, group_id: int) -> Set[str]:
        ids = self.groups.get(group_id)
        if ids:
            return {cid for cid in ids if self.is_visible(cid)}

    def disable_visible_from_groups(self, *groups):
        if groups:
            for group in groups:
                ids = self.list_visible_from_group(group)

                if ids:
                    self.set_components_enabled(False, *ids)

    def disable_visible(self):
        self.set_components_enabled(False, *{cid for cid in self.components if self.is_visible(cid)})

    def enable_visible(self):
        self.set_components_enabled(True, *{cid for cid in self.components if self.is_visible(cid)})

    def enable_visible_from_groups(self, *groups):
        if groups:
            for group in groups:
                ids = self.list_visible_from_group(group)

                if ids:
                    self.set_components_enabled(True, *ids)

    def save_state(self, cid: int, state_id: int):
        comp = self.components.get(cid)

        if comp:
            self._save_state(comp)
            states = self._saved_states.get(state_id)

            if states is None:
                states = {}
                self._saved_states[state_id] = states

            states[cid] = {**comp[2]}

    def save_states(self, state_id: int, *ids, only_visible: bool = False):
        for cid in (ids if ids else self.components):
            if not only_visible or self.is_visible(cid):
                self.save_state(cid, state_id)

    def save_group_state(self, group_id: int, state_id: int):
        ids = self.groups.get(group_id)

        if ids:
            self.save_states(state_id, *ids)

    def save_groups_states(self, state_id: int, *group_ids):
        if group_ids:
            for group_id in group_ids:
                self.save_group_state(group_id, state_id)

    def _restore_state(self, comp: Tuple[QWidget, Optional[QAction], Dict[str, bool]], state: Dict[str, bool]):
        self._save_state(comp)

        if state['v'] != self._is_visible(comp):
            self._set_visible(comp, state['v'])

        if state['e'] != self._is_enabled(comp):
            self._set_enabled(comp, state['e'])

        if state['r'] != self._is_read_only(comp):
            self._set_read_only(comp, state['r'])

    def restore_group_state(self, group_id: int,  state_id: int):
        states = self._saved_states.get(state_id)

        if states:
            ids = self.groups.get(group_id)

            if ids:
                for cid in ids:
                    comp_state = states.get(cid)

                    if comp_state:
                        comp = self.components.get(cid)

                        if comp:
                            self._restore_state(comp, comp_state)

    def restore_groups_state(self, state_id: int, *group_ids):
        if group_ids:
            for group_id in group_ids:
                self.restore_group_state(group_id, state_id)

    def restore_state(self, state_id: int):
        state = self._saved_states.get(state_id)

        if state:
            for cid, cstate in state.items():
                comp = self.components.get(cid)

                if comp:
                    self._restore_state(comp, cstate)

            del self._saved_states[state_id]

    def clear_saved_states(self):
        self._saved_states.clear()

    def remove_saved_state(self, state_id: int):
        if state_id in self._saved_states:
            del self._saved_states[state_id]


class RadioButtonQt(QRadioButton):

    def __init__(self, model: InputOption, model_parent: SingleSelectComponent):
        super(RadioButtonQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.toggled.connect(self._set_checked)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        if model.icon_path:
            if model.icon_path.startswith('/'):
                self.setIcon(QIcon(model.icon_path))
            else:
                self.setIcon(QIcon.fromTheme(model.icon_path))

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
            if model.icon_path.startswith('/'):
                self.setIcon(QIcon(model.icon_path))
            else:
                self.setIcon(QIcon.fromTheme(model.icon_path))

        if model.read_only:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.setFocusPolicy(Qt.NoFocus)
        else:
            self.setCursor(QCursor(Qt.PointingHandCursor))

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
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.view().setCursor(QCursor(Qt.PointingHandCursor))

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
        if not model.label:
            self.setObjectName('radio_select_notitle')

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


class ComboSelectQt(QGroupBox):

    def __init__(self, model: SingleSelectComponent):
        super(ComboSelectQt, self).__init__()
        self.model = model
        self._layout = QGridLayout()
        self.setLayout(self._layout)
        self._layout.addWidget(QLabel(model.label + ' :' if model.label else ''), 0, 0)
        self._layout.addWidget(FormComboBoxQt(model), 0, 1)


class QLineEditObserver(QLineEdit, ViewObserver):

    def __init__(self, **kwargs):
        super(QLineEditObserver, self).__init__(**kwargs)

    def on_change(self, change: str):
        if self.text() != change:
            self.setText(change if change is not None else '')


class QPlainTextEditObserver(QPlainTextEdit, ViewObserver):

    def __init__(self, **kwargs):
        super(QPlainTextEditObserver, self).__init__(**kwargs)

    def on_change(self, change: str):
        self.setText(change)

    def setText(self, text: str):
        if text != self.toPlainText():
            self.setPlainText(text if text is not None else '')

    def setCursorPosition(self, idx: int):
        self.textCursor().setPosition(idx)


class TextInputQt(QGroupBox):

    def __init__(self, model: TextInputComponent):
        super(TextInputQt, self).__init__()
        self.model = model
        self.setLayout(QGridLayout())

        if self.model.max_width > 0:
            self.setMaximumWidth(self.model.max_width)

        self.text_input = QLineEditObserver() if model.type == TextInputType.SINGLE_LINE else QPlainTextEditObserver()

        if model.only_int:
            self.text_input.setValidator(QIntValidator())

        if model.placeholder:
            self.text_input.setPlaceholderText(model.placeholder)

        if model.min_width >= 0:
            self.text_input.setMinimumWidth(model.min_width)

        if model.min_height >= 0:
            self.text_input.setMinimumHeight(model.min_height)

        if model.tooltip:
            self.text_input.setToolTip(model.tooltip)

        if model.value is not None:
            self.text_input.setText(model.value)
            self.text_input.setCursorPosition(0)

        self.text_input.textChanged.connect(self._update_model)

        self.model.observers.append(self.text_input)
        self.layout().addWidget(self.text_input, 0, 1)

    def _update_model(self, *args):
        change = args[0] if args else self.text_input.toPlainText()
        self.model.set_value(val=change, caller=self)


class MultipleSelectQt(QGroupBox):

    def __init__(self, model: MultipleSelectComponent, callback):
        super(MultipleSelectQt, self).__init__(model.label if model.label else None)
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
                help_icon.setProperty('help_icon', 'true')
                help_icon.setCursor(QCursor(Qt.WhatsThisCursor))
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
            self._layout.addWidget(QLabel(), 0, 1)
        else:
            line = 0

        col = 0

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
                help_icon.setProperty('help_icon', 'true')
                help_icon.setToolTip(op.tooltip)
                help_icon.setCursor(QCursor(Qt.WhatsThisCursor))
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
        self.typing = QTimer()
        self.typing.timeout.connect(self.notify_text_change)

    def notify_text_change(self):
        text = self.text().strip()

        if text != self.last_text:
            self.last_text = text
            self.on_key_press()

    def keyPressEvent(self, event):
        super(InputFilter, self).keyPressEvent(event)

        if self.typing.isActive():
            return

        self.typing.start(3000)

    def get_text(self):
        return self.last_text

    def setText(self, p_str):
        super(InputFilter, self).setText(p_str)
        self.last_text = p_str


class IconButton(QToolButton):

    def __init__(self, action, i18n: I18n, align: int = Qt.AlignCenter, tooltip: str = None, expanding: bool = False):
        super(IconButton, self).__init__()
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.clicked.connect(action)
        self.i18n = i18n
        self.default_tootip = tooltip
        self.setSizePolicy(QSizePolicy.Expanding if expanding else QSizePolicy.Minimum, QSizePolicy.Minimum)

        if tooltip:
            self.setToolTip(tooltip)

    def setEnabled(self, enabled):
        super(IconButton, self).setEnabled(enabled)

        if not enabled:
            self.setToolTip(self.i18n['icon_button.tooltip.disabled'])
        else:
            self.setToolTip(self.default_tootip)


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

        if model.spaces:
            self.layout().addRow(QLabel(), QLabel())

        for idx, c in enumerate(model.components):
            if isinstance(c, TextInputComponent):
                label, field = self._new_text_input(c)
                self.layout().addRow(label, field)
            elif isinstance(c, SingleSelectComponent):
                label = self._new_label(c)
                form = FormComboBoxQt(c) if c.type == SelectViewType.COMBO else FormRadioSelectQt(c)
                field = self._wrap(form, c)
                self.layout().addRow(label, field)
            elif isinstance(c, RangeInputComponent):
                label = self._new_label(c)
                field = self._wrap(self._new_range_input(c), c)
                self.layout().addRow(label, field)
            elif isinstance(c, FileChooserComponent):
                label, field = self._new_file_chooser(c)
                self.layout().addRow(label, field)
            elif isinstance(c, FormComponent):
                label, field = None,  FormQt(c, self.i18n)
                self.layout().addRow(field)
            elif isinstance(c, TwoStateButtonComponent):
                label, field = self._new_label(c), TwoStateButtonQt(c)
                self.layout().addRow(label, field)
            elif isinstance(c, MultipleSelectComponent):
                label, field = self._new_label(c), FormMultipleSelectQt(c)
                self.layout().addRow(label, field)
            elif isinstance(c, TextComponent):
                label, field = self._new_label(c), QWidget()
                self.layout().addRow(label, field)
            elif isinstance(c, RangeInputComponent):
                label, field = self._new_label(c), self._new_range_input(c)
                self.layout().addRow(label, field)
            else:
                raise Exception('Unsupported component type {}'.format(c.__class__.__name__))

            if label:  # to prevent C++ wrap errors
                setattr(self, 'label_{}'.format(idx), label)

            if field:  # to prevent C++ wrap errors
                setattr(self, 'field_{}'.format(idx), field)

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

        if hasattr(comp, 'get_label'):
            text = comp.get_label()
        else:
            attr = 'label' if hasattr(comp, 'label') else 'value'
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
        tip_icon.setProperty('tip_icon', 'true')
        tip_icon.setToolTip(tip.strip())
        tip_icon.setCursor(QCursor(Qt.WhatsThisCursor))
        return tip_icon

    def _new_text_input(self, c: TextInputComponent) -> Tuple[QLabel, QLineEdit]:
        view = QLineEditObserver() if c.type == TextInputType.SINGLE_LINE else QPlainTextEditObserver()

        if c.min_width >= 0:
            view.setMinimumWidth(c.min_width)

        if c.min_height >= 0:
            view.setMinimumHeight(c.min_height)

        if c.only_int:
            view.setValidator(QIntValidator())

        if c.tooltip:
            view.setToolTip(c.tooltip)

        if c.placeholder:
            view.setPlaceholderText(c.placeholder)

        if c.value is not None:
            view.setText(str(c.value))
            view.setCursorPosition(0)

        if c.read_only:
            view.setEnabled(False)

        def update_model(text: str):
            c.set_value(val=text, caller=view)

        view.textChanged.connect(update_model)
        c.observers.append(view)

        label = QWidget()
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label.setLayout(QHBoxLayout())

        label_component = QLabel()
        label.layout().addWidget(label_component)

        if label:
            label_component.setText(c.get_label())

            if c.tooltip:
                label.layout().addWidget(self.gen_tip_icon(c.tooltip))

        return label, self._wrap(view, c)

    def _new_range_input(self, model: RangeInputComponent) -> QSpinBox:
        spinner = QSpinBox()
        spinner.setCursor(QCursor(Qt.PointingHandCursor))
        spinner.setMinimum(model.min)
        spinner.setMaximum(model.max)
        spinner.setSingleStep(model.step)
        spinner.setValue(model.value if model.value is not None else model.min)

        if model.tooltip:
            spinner.setToolTip(model.tooltip)

        def _update_value():
            model.value = spinner.value()

        spinner.valueChanged.connect(_update_value)
        return spinner

    def _wrap(self, comp: QWidget, model: ViewComponent) -> QWidget:
        field_container = QWidget()
        field_container.setLayout(QHBoxLayout())

        if model.max_width > 0:
            field_container.setMaximumWidth(model.max_width)

        field_container.layout().addWidget(comp)
        return field_container

    def _new_file_chooser(self, c: FileChooserComponent) -> Tuple[QLabel, QLineEdit]:
        chooser = QLineEditObserver()
        chooser.setReadOnly(True)

        if c.max_width > 0:
            chooser.setMaximumWidth(c.max_width)

        if c.file_path:
            chooser.setText(c.file_path)
            chooser.setCursorPosition(0)

        c.observers.append(chooser)
        chooser.setPlaceholderText(self.i18n['view.components.file_chooser.placeholder'])

        def open_chooser(e):
            if c.allowed_extensions:
                exts = ';;'.join({'*.{}'.format(e) for e in c.allowed_extensions})
            else:
                exts = '{} (*);;'.format(self.i18n['all_files'].capitalize())

            if c.file_path and os.path.isfile(c.file_path):
                cur_path = c.file_path
            elif c.search_path and os.path.exists(c.search_path):
                cur_path = c.search_path
            else:
                cur_path = str(Path.home())

            if c.directory:
                file_path = QFileDialog.getExistingDirectory(self, self.i18n['file_chooser.title'], cur_path, options=QFileDialog.Options())
            else:
                file_path, _ = QFileDialog.getOpenFileName(self, self.i18n['file_chooser.title'], cur_path, exts, options=QFileDialog.Options())

            if file_path:
                c.set_file_path(file_path)

            chooser.setCursorPosition(0)

        def clean_path():
            c.set_file_path(None)

        chooser.mousePressEvent = open_chooser

        label = self._new_label(c)
        wrapped = self._wrap(chooser, c)

        bt = IconButton(i18n=self.i18n['clean'].capitalize(), action=clean_path, tooltip=self.i18n['clean'].capitalize())
        bt.setObjectName('clean_field')

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

        self.tabBar().setCursor(QCursor(Qt.PointingHandCursor))


def new_single_select(model: SingleSelectComponent) -> QWidget:
    if model.type == SelectViewType.RADIO:
        return RadioSelectQt(model)
    elif model.type == SelectViewType.COMBO:
        return ComboSelectQt(model)
    else:
        raise Exception("Unsupported type {}".format(model.type))


def new_spacer(min_width: int = None) -> QWidget:
    spacer = QWidget()
    spacer.setProperty('spacer', 'true')

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
    elif isinstance(comp, RangeInputComponent):
        return RangeInputQt(comp)
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


class RangeInputQt(QGroupBox):

    def __init__(self, model: RangeInputComponent):
        super(RangeInputQt, self).__init__()
        self.model = model
        self.setLayout(QGridLayout())
        self.layout().addWidget(QLabel(model.label.capitalize() + ' :' if model.label else ''), 0, 0)

        if self.model.max_width > 0:
            self.setMaximumWidth(self.model.max_width)

        self.spinner = QSpinBox()
        self.spinner.setCursor(QCursor(Qt.PointingHandCursor))
        self.spinner.setMinimum(model.min)
        self.spinner.setMaximum(model.max)
        self.spinner.setSingleStep(model.step)
        self.spinner.setValue(model.value if model.value is not None else model.min)

        if model.tooltip:
            self.spinner.setToolTip(model.tooltip)

        self.layout().addWidget(self.spinner, 0, 1)

        self.spinner.valueChanged.connect(self._update_value)

    def _update_value(self):
        self.model.value = self.spinner.value()


class QCustomLineEdit(QLineEdit):

    def __init__(self, focus_in_callback, focus_out_callback, **kwargs):
        super(QCustomLineEdit, self).__init__(**kwargs)
        self.focus_in_callback = focus_in_callback
        self.focus_out_callback = focus_out_callback

    def focusInEvent(self, ev: QFocusEvent):
        super(QCustomLineEdit, self).focusInEvent(ev)
        if self.focus_in_callback:
            self.focus_in_callback()

    def focusOutEvent(self, ev: QFocusEvent):
        super(QCustomLineEdit, self).focusOutEvent(ev)
        if self.focus_out_callback:
            self.focus_out_callback()

        self.clearFocus()


class QSearchBar(QWidget):

    def __init__(self, search_callback, parent: Optional[QWidget] = None):
        super(QSearchBar, self).__init__(parent=parent)
        self.setLayout(QHBoxLayout())
        self.setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.callback = search_callback

        self.inp_search = QCustomLineEdit(focus_in_callback=self._set_focus_in,
                                          focus_out_callback=self._set_focus_out)
        self.inp_search.setObjectName('inp_search')
        self.inp_search.setFrame(False)
        self.inp_search.returnPressed.connect(search_callback)
        search_background_color = self.inp_search.palette().color(self.inp_search.backgroundRole()).name()

        self.search_left_corner = QLabel()
        self.search_left_corner.setObjectName('lb_left_corner')

        self.layout().addWidget(self.search_left_corner)

        self.layout().addWidget(self.inp_search)

        self.search_button = QPushButton()
        self.search_button.setObjectName('search_button')
        self.search_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.search_button.clicked.connect(search_callback)

        self.layout().addWidget(self.search_button)

    def clear(self):
        self.inp_search.clear()

    def text(self) -> str:
        return self.inp_search.text()

    def set_text(self, text: str):
        self.inp_search.setText(text)

    def setFocus(self):
        self.inp_search.setFocus()

    def set_tooltip(self, tip: str):
        self.inp_search.setToolTip(tip)

    def set_button_tooltip(self, tip: str):
        self.search_button.setToolTip(tip)

    def set_placeholder(self, placeholder: str):
        self.inp_search.setPlaceholderText(placeholder)

    def _set_focus_in(self):
        self.search_button.setProperty('focused', 'true')
        self.search_left_corner.setProperty('focused', 'true')

        for c in (self.search_button, self.search_left_corner):
            c.style().unpolish(c)
            c.style().polish(c)

    def _set_focus_out(self):
        self.search_button.setProperty('focused', 'false')
        self.search_left_corner.setProperty('focused', 'false')

        for c in (self.search_button, self.search_left_corner):
            c.style().unpolish(c)
            c.style().polish(c)


class QCustomMenuAction(QWidgetAction):

    def __init__(self, parent: QWidget, label: Optional[str] = None, action=None, button_name: Optional[str] = None,
                 icon: Optional[QIcon] = None, tooltip: Optional[str] = None):
        super(QCustomMenuAction, self).__init__(parent)
        self.button = QPushButton()
        self.set_label(label)
        self._action = None
        self.set_action(action)
        self.set_button_name(button_name)
        self.set_icon(icon)
        self.setDefaultWidget(self.button)

        if tooltip:
            self.button.setToolTip(tooltip)

    def set_label(self, label: str):
        self.button.setText(label)

    def set_action(self, action):
        self._action = action
        self.button.clicked.connect(self._handle_action)

    def _handle_action(self):
        if self._action:
            self._action()

            if self.parent() and isinstance(self.parent(), QMenu):
                self.parent().close()

    def set_button_name(self, name: str):
        if name:
            self.button.setObjectName(name)

    def set_icon(self, icon: QIcon):
        if icon:
            self.button.setIcon(icon)

    def get_label(self) -> str:
        return self.button.text()


class QCustomToolbar(QWidget):

    def __init__(self, spacing: int = 2, parent: Optional[QWidget] = None, alignment: Qt.Alignment = Qt.AlignRight,
                 policy_width: QSizePolicy.Policy = QSizePolicy.Minimum,
                 policy_height: QSizePolicy.Policy = QSizePolicy.Preferred):
        super(QCustomToolbar, self).__init__(parent=parent)
        self.setProperty('container', 'true')
        self.setSizePolicy(policy_width, policy_height)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(spacing)
        self.layout().setAlignment(alignment)

    def add_widget(self, widget: QWidget):
        if widget:
            self.layout().addWidget(widget)

    def add_stretch(self, value: int = 0):
        self.layout().addStretch(value)

    def add_space(self, min_width: int = 0):
        self.layout().addWidget(new_spacer(min_width))
