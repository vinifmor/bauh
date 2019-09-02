from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QRadioButton, QGroupBox, QCheckBox, QComboBox, QGridLayout, QWidget, \
    QLabel, QSizePolicy, QLineEdit
from bauh_api.abstract.view import SingleSelectComponent, InputOption, MultipleSelectComponent, SelectViewType


class RadioButtonQt(QRadioButton):

    def __init__(self, model: InputOption, model_parent: SingleSelectComponent):
        super(RadioButtonQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.toggled.connect(self._set_checked)

    def _set_checked(self, checked: bool):
        if checked:
            self.model_parent.value = self.model


class CheckboxQt(QCheckBox):

    def __init__(self, model: InputOption, model_parent: MultipleSelectComponent):
        super(CheckboxQt, self).__init__()
        self.model = model
        self.model_parent = model_parent
        self.stateChanged.connect(self._set_checked)

    def _set_checked(self, state):
        if state == 2:
            self.model_parent.values.add(self.model)
        else:
            if self.model in self.model_parent.values:
                self.model_parent.values.remove(self.model)


class ComboBoxQt(QComboBox):

    def __init__(self, model: SingleSelectComponent):
        super(ComboBoxQt, self).__init__()
        self.model = model
        for idx, op in enumerate(self.model.options):
            self.addItem(op.label, op.value)

            if model.value and model.value == op:  # default
                self.setCurrentIndex(idx)

        self.currentIndexChanged.connect(self._set_selected)

    def _set_selected(self, idx: int):
        self.model.value = self.model.options[idx]


class RadioSelectQt(QGroupBox):

    def __init__(self, model: SingleSelectComponent):
        super(RadioSelectQt, self).__init__(model.label + ' :')
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

# class ComboSelectQt(QGroupBox):
#
#     def __init__(self, model: SingleSelectComponent):
#         super(ComboSelectQt, self).__init__(model.label + ' :')
#         self.model = model
#         self.setLayout(QGridLayout())
#         self.setStyleSheet('QGridLayout {margin-left: 0} QLabel { font-weight: bold}')
#         self.layout().addWidget(ComboBoxQt(model), 0, 1)


class MultipleSelectQt(QGroupBox):

    def __init__(self, model: MultipleSelectComponent):
        super(MultipleSelectQt, self).__init__(model.label + ' :' if model.label else None)
        self.setStyleSheet("QGroupBox { font-weight: bold }")
        self.model = model
        self._layout = QGridLayout()
        self.setLayout(self._layout)

        line, col = 0, 0
        for op in model.options:
            comp = CheckboxQt(op, model)
            comp.setText(op.label)
            comp.setToolTip(op.tooltip)

            if model.values and op in model.values:
                self.value = comp
                comp.setChecked(True)

            self._layout.addWidget(comp, line, col)

            if col + 1 == self.model.max_per_line:
                line += 1
                col = 0
            else:
                col += 1


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


def new_single_select(model: SingleSelectComponent):
    if model.type == SelectViewType.RADIO:
        return RadioSelectQt(model)
    elif model.type == SelectViewType.COMBO:
        return ComboSelectQt(model)
    else:
        raise Exception("Unsupported type {}".format(model.type))


def new_spacer() -> QWidget:
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return spacer
