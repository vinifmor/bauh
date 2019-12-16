from abc import ABC
from enum import Enum
from typing import List, Set


class MessageType:
    INFO = 0
    WARNING = 1
    ERROR = 2


class ViewComponent(ABC):
    """
    Represents a GUI component
    """
    def __init__(self, id_: str):
        self.id = id_


class InputViewComponent(ViewComponent):
    """
    Represents an component which needs a user interaction to provide its value
    """


class InputOption:
    """
    Represents a select component option.
    """

    def __init__(self, label: str, value: object, tooltip: str = None, icon_path: str = None, read_only: bool = False, id_: str = None):
        """
        :param label: the string that will be shown to the user
        :param value: the option value (not shown)
        :param tooltip: an optional tooltip
        :param icon_path: an optional icon path
        """
        if not label:
            raise Exception("'label' must be a not blank string")

        if value is None:
            raise Exception("'value' must be a not blank string")

        self.id = id_
        self.label = label
        self.value = value
        self.tooltip = tooltip
        self.icon_path = icon_path
        self.read_only = read_only

    def __hash__(self):
        return hash(self.label) + hash(self.value)


class SelectViewType(Enum):
    RADIO = 0
    COMBO = 1


class SingleSelectComponent(InputViewComponent):

    def __init__(self, type_: SelectViewType, label: str, options: List[InputOption], default_option: InputOption = None, max_per_line: int = 1, id_: str = None):
        super(SingleSelectComponent, self).__init__(id_=id_)
        self.type = type_
        self.label = label
        self.options = options
        self.value = default_option
        self.max_per_line = max_per_line

    def get_selected(self):
        if self.value:
            return self.value.value


class MultipleSelectComponent(InputViewComponent):

    def __init__(self, label: str, options: List[InputOption], default_options: Set[InputOption] = None, max_per_line: int = 1, id_: str = None):
        super(MultipleSelectComponent, self).__init__(id_=id_)

        if not options:
            raise Exception("'options' cannot be None or empty")

        self.options = options
        self.label = label
        self.values = default_options if default_options else set()
        self.max_per_line = max_per_line

    def get_selected_values(self) -> list:
        selected = []
        if self.values:
            selected.extend([op.value for op in self.values])

        return selected


class TextComponent(ViewComponent):

    def __init__(self, html: str, id_: str = None):
        super(TextComponent, self).__init__(id_=id_)
        self.value = html


class TextInputComponent(ViewComponent):

    def __init__(self, label: str, value: str = '', placeholder: str = None, tooltip: str = None, read_only: bool =False, id_: str = None):
        super(TextInputComponent, self).__init__(id_=id_)
        self.label = label
        self.value = value
        self.tooltip = tooltip
        self.placeholder = placeholder
        self.read_only = read_only

    def get_value(self) -> str:
        if self.value is not None:
            return self.value.strip()
        else:
            return ''


class FormComponent(ViewComponent):

    def __init__(self, components: List[ViewComponent], label: str = None, id_: str = None):
        super(FormComponent, self).__init__(id_=id_)
        self.label = label
        self.components = components


class FileChooserComponent(ViewComponent):

    def __init__(self, allowed_extensions: Set[str] = None, label: str = None, id_: str = None):
        super(FileChooserComponent, self).__init__(id_=id_)
        self.label = label
        self.allowed_extensions = allowed_extensions
        self.file_path = None
