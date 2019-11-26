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

    def __init__(self, label: str, value: object, tooltip: str = None, icon_path: str = None, read_only: bool = False):
        """
        :param label: the string that will be shown to the user
        :param value: the option value (not shown)
        :param tooltip: an optional tooltip
        :param icon_path: an optional icon path
        """
        if not label:
            raise Exception("'label' must be a not blank string")

        if not value:
            raise Exception("'value' must be a not blank string")

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


class MultipleSelectComponent(InputViewComponent):

    def __init__(self, label: str, options: List[InputOption], default_options: Set[InputOption] = None, max_per_line: int = 1, id_: str = None):
        super(MultipleSelectComponent, self).__init__(id_=id_)

        if not options:
            raise Exception("'options' cannot be None or empty")

        self.options = options
        self.label = label
        self.values = default_options if default_options else set()
        self.max_per_line = max_per_line


class TextComponent(ViewComponent):

    def __init__(self, html: str, id_: str = None):
        super(TextComponent, self).__init__(id_=id_)
        self.value = html
