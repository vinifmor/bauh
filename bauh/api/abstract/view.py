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


class SpacerComponent(ViewComponent):

    def __init__(self):
        super(SpacerComponent, self).__init__(id_=None)


class PanelComponent(ViewComponent):

    def __init__(self, components: List[ViewComponent], id_: str = None):
        super(PanelComponent, self).__init__(id_=id_)
        self.components = components
        self.component_map = {c.id: c for c in components if c.id is not None} if components else None

    def get_component(self, id_: str) -> ViewComponent:
        if self.component_map:
            return self.component_map.get(id_)


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

    def __init__(self, type_: SelectViewType, label: str, options: List[InputOption], default_option: InputOption = None,
                 max_per_line: int = 1, tooltip: str = None, max_width: int = -1, id_: str = None,
                 capitalize_label: bool = True):
        super(SingleSelectComponent, self).__init__(id_=id_)
        self.type = type_
        self.label = label
        self.options = options
        self.value = default_option
        self.max_per_line = max_per_line
        self.tooltip = tooltip
        self.max_width = max_width
        self.capitalize_label = capitalize_label

    def get_selected(self):
        if self.value:
            return self.value.value


class MultipleSelectComponent(InputViewComponent):

    def __init__(self, label: str, options: List[InputOption], default_options: Set[InputOption] = None,
                 max_per_line: int = 1, tooltip: str = None, spaces: bool = True, max_width: int = -1,
                 max_height: int = -1, id_: str = None):
        super(MultipleSelectComponent, self).__init__(id_=id_)

        if not options:
            raise Exception("'options' cannot be None or empty")

        self.options = options
        self.spaces = spaces
        self.label = label
        self.tooltip = tooltip
        self.values = default_options if default_options else set()
        self.max_per_line = max_per_line
        self.max_width = max_width
        self.max_height = max_height

    def get_selected_values(self) -> list:
        selected = []
        if self.values:
            selected.extend([op.value for op in self.values])

        return selected


class TextComponent(ViewComponent):

    def __init__(self, html: str, max_width: int = -1, tooltip: str = None, id_: str = None, size: int = None):
        super(TextComponent, self).__init__(id_=id_)
        self.value = html
        self.max_width = max_width
        self.tooltip = tooltip
        self.size = size


class TwoStateButtonComponent(ViewComponent):

    def __init__(self, label: str, tooltip: str = None, state: bool = False,  id_: str = None):
        super(TwoStateButtonComponent, self).__init__(id_=id_)
        self.label = label
        self.tooltip = tooltip
        self.state = state


class TextInputComponent(ViewComponent):

    def __init__(self, label: str, value: str = '', placeholder: str = None, tooltip: str = None, read_only: bool =False,
                 id_: str = None, only_int: bool = False, max_width: int = -1):
        super(TextInputComponent, self).__init__(id_=id_)
        self.label = label
        self.value = value
        self.tooltip = tooltip
        self.placeholder = placeholder
        self.read_only = read_only
        self.only_int = only_int
        self.max_width = max_width

    def get_value(self) -> str:
        if self.value is not None:
            return self.value.strip()
        else:
            return ''

    def get_int_value(self) -> int:
        if self.value is not None:
            val = self.value.strip() if isinstance(self.value, str) else self.value

            if val:
                return int(self.value)


class FormComponent(ViewComponent):

    def __init__(self, components: List[ViewComponent], label: str = None, spaces: bool = True, id_: str = None):
        super(FormComponent, self).__init__(id_=id_)
        self.label = label
        self.spaces = spaces
        self.components = components
        self.component_map = {c.id: c for c in components if c.id} if components else None

    def get_component(self, id_: str) -> ViewComponent:
        if self.component_map:
            return self.component_map.get(id_)


class FileChooserComponent(ViewComponent):

    def __init__(self, allowed_extensions: Set[str] = None, label: str = None, tooltip: str = None,
                 file_path: str = None, max_width: int = -1, id_: str = None):
        super(FileChooserComponent, self).__init__(id_=id_)
        self.label = label
        self.allowed_extensions = allowed_extensions
        self.file_path = file_path
        self.tooltip = tooltip
        self.max_width = max_width


class TabComponent(ViewComponent):

    def __init__(self, label: str, content: ViewComponent, icon_path: str = None, id_: str = None):
        super(TabComponent, self).__init__(id_=id_)
        self.label = label
        self.content = content
        self.icon_path = icon_path


class TabGroupComponent(ViewComponent):

    def __init__(self, tabs: List[TabComponent], id_: str = None):
        super(TabGroupComponent, self).__init__(id_=id_)
        self.tabs = tabs
        self.tab_map = {c.id: c for c in tabs if c.id} if tabs else None

    def get_tab(self, id_: str) -> TabComponent:
        if self.tab_map:
            return self.tab_map.get(id_)
