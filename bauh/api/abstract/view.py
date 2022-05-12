from abc import ABC
from enum import Enum
from typing import List, Set, Optional, Dict, TypeVar, Type, Union, Tuple


class MessageType(Enum):
    INFO = 0
    WARNING = 1
    ERROR = 2


class ViewComponentAlignment(Enum):
    CENTER = 0
    LEFT = 1
    RIGHT = 2
    BOTTOM = 3
    TOP = 4
    HORIZONTAL_CENTER = 5
    VERTICAL_CENTER = 6


class ViewObserver:

    def on_change(self, change):
        pass


class ViewComponent(ABC):
    """
    Represents a GUI component
    """
    def __init__(self, id_: Optional[str], alignment: Optional[ViewComponentAlignment] = None,
                 observers: Optional[List[ViewObserver]] = None):
        self.id = id_
        self.alignment = alignment
        self.observers = observers if observers else []

    def add_observer(self, obs):
        self.observers.append(obs)


V = TypeVar('V', bound=ViewComponent)


class ViewContainer(ViewComponent, ABC):
    """
        Represents a GUI component composed by other components
    """

    def __init__(self, components: Union[List[V], Tuple[V]],
                 id_: Optional[str] = None,
                 observers: Optional[List[ViewObserver]] = None):
        super(ViewContainer, self).__init__(id_=id_, observers=observers)
        self.components = components
        self.component_map = {c.id: c for c in components if c.id is not None} if components else None

    def get_component(self, id_: str, type_: Type[V] = ViewComponent) -> Optional[V]:
        if self.component_map:
            instance = self.component_map.get(id_)

            if instance:
                if isinstance(instance, type_):
                    return instance

                raise Exception(f"The {ViewComponent.__class__.__name__} (id={id_}) is not an "
                                f"instance of '{type_.__name__}'")

    def get_component_by_idx(self, idx: int, type_: Type[V]) -> Optional[V]:
        if self.components and idx < len(self.components):
            c = self.components[idx]
            if isinstance(c, type_):
                return c

            raise Exception(f"The {ViewComponent.__class__.__name__} at index {idx} is not an "
                            f"instance of '{type_.__name__}'")


class SpacerComponent(ViewComponent):

    def __init__(self):
        super(SpacerComponent, self).__init__(id_=None)


class InputViewComponent(ViewComponent):
    """
    Represents a component which needs a user interaction to provide its value
    """


class InputOption:
    """
    Represents a select component option.
    """

    def __init__(self, label: str, value: object, tooltip: Optional[str] = None,
                 icon_path: Optional[str] = None, read_only: bool = False, id_: Optional[str] = None,
                 invalid: bool = False, extra_properties: Optional[Dict[str, str]] = None):
        """
        :param label: the string that will be shown to the user
        :param value: the option value (not shown)
        :param tooltip: an optional tooltip
        :param icon_path: an optional icon path
        :param invalid: if this option is considered invalid
        :param extra_properties: extra properties
        """
        if not label:
            raise Exception("'label' must be a not blank string")

        self.id = id_
        self.label = label
        self.value = value
        self.tooltip = tooltip
        self.icon_path = icon_path
        self.read_only = read_only
        self.invalid = invalid
        self.extra_properties = extra_properties

    def __hash__(self):
        return hash(self.label) + hash(self.value)


class SelectViewType(Enum):
    RADIO = 0
    COMBO = 1


class SingleSelectComponent(InputViewComponent):

    def __init__(self, type_: SelectViewType, label: str, options: List[InputOption],
                 default_option: InputOption = None, max_per_line: int = 1, tooltip: str = None,
                 max_width: Optional[int] = -1, id_: str = None, capitalize_label: bool = True,
                 alignment: Optional[ViewComponentAlignment] = None):
        super(SingleSelectComponent, self).__init__(id_=id_, alignment=alignment)
        self.type = type_
        self.label = label
        self.options = options
        self.value = default_option
        self.init_value = default_option
        self.max_per_line = max_per_line
        self.tooltip = tooltip
        self.max_width = max_width
        self.capitalize_label = capitalize_label

    def get_selected(self):
        if self.value:
            return self.value.value

    def changed(self) -> bool:
        return self.init_value != self.value


class MultipleSelectComponent(InputViewComponent):

    def __init__(self, label: Optional[str], options: List[InputOption], default_options: Set[InputOption] = None,
                 max_per_line: int = 1, tooltip: str = None, spaces: bool = True, max_width: int = -1,
                 max_height: int = -1, id_: str = None, min_width: Optional[int] = None,
                 opt_max_width: Optional[int] = None):
        super(MultipleSelectComponent, self).__init__(id_=id_)

        if not options:
            raise Exception("'options' cannot be None or empty")

        self.options = options
        self.spaces = spaces
        self.label = label
        self.tooltip = tooltip
        self.values = default_options if default_options else set()
        self.max_per_line = max_per_line
        self.min_width = min_width
        self.max_width = max_width
        self.max_height = max_height
        self.opt_max_width = opt_max_width

    def get_selected_values(self) -> list:
        selected = []
        if self.values:
            selected.extend([op.value for op in self.values])

        return selected


class TextComponent(ViewComponent):

    def __init__(self, html: str, min_width: Optional[int] = None, max_width: int = -1,
                 tooltip: str = None, id_: str = None, size: int = None):
        super(TextComponent, self).__init__(id_=id_)
        self.value = html
        self.min_width = min_width
        self.max_width = max_width
        self.tooltip = tooltip
        self.size = size


class TwoStateButtonComponent(ViewComponent):

    def __init__(self, label: str, tooltip: str = None, state: bool = False,  id_: str = None):
        super(TwoStateButtonComponent, self).__init__(id_=id_)
        self.label = label
        self.tooltip = tooltip
        self.state = state


class TextInputType(Enum):
    SINGLE_LINE = 0
    MULTIPLE_LINES = 1


class TextInputComponent(ViewComponent):

    def __init__(self, label: str, value: str = '', placeholder: Optional[str] = None, tooltip: Optional[str] = None,
                 read_only: bool = False, id_: Optional[str] = None, only_int: bool = False, max_width: int = -1,
                 type_: TextInputType = TextInputType.SINGLE_LINE, capitalize_label: bool = True, min_width: int = -1,
                 min_height: int = -1):
        super(TextInputComponent, self).__init__(id_=id_)
        self.label = label
        self.value = value
        self.tooltip = tooltip
        self.placeholder = placeholder
        self.read_only = read_only
        self.only_int = only_int
        self.max_width = max_width
        self.type = type_
        self.capitalize_label = capitalize_label
        self.min_width = min_width
        self.min_height = min_height

    def get_value(self) -> str:
        if self.value is not None:
            return self.value
        else:
            return ''

    def set_value(self, val: Optional[str], caller: object = None):
        if val != self.value:
            self.value = val

            if self.observers:
                for o in self.observers:
                    if caller != o:
                        o.on_change(val)

    def get_int_value(self) -> Optional[int]:
        if self.value is not None:
            val = self.value.strip() if isinstance(self.value, str) else self.value

            if val is not None:
                return int(self.value)

    def get_label(self) -> str:
        if not self.label:
            return ''
        else:
            return self.label.capitalize() if self.capitalize_label else self.label


class FormComponent(ViewContainer):

    def __init__(self, components: List[ViewComponent], label: str = None, spaces: bool = True, id_: str = None,
                 min_width: Optional[int] = None):
        super(FormComponent, self).__init__(id_=id_, components=components)
        self.label = label
        self.spaces = spaces
        self.min_width = min_width


class FileChooserComponent(ViewComponent):

    def __init__(self, allowed_extensions: Optional[Set[str]] = None, label: Optional[str] = None, tooltip: Optional[str] = None,
                 file_path: Optional[str] = None, max_width: int = -1, id_: Optional[str] = None,
                 search_path: Optional[str] = None, capitalize_label: bool = True, directory: bool = False):
        super(FileChooserComponent, self).__init__(id_=id_)
        self.label = label
        self.allowed_extensions = allowed_extensions
        self.file_path = file_path
        self.tooltip = tooltip
        self.max_width = max_width
        self.search_path = search_path
        self.capitalize_label = capitalize_label
        self.directory = directory

    def set_file_path(self, fpath: Optional[str]):
        self.file_path = fpath

        if self.observers:
            for o in self.observers:
                o.on_change(self.file_path)

    def get_label(self) -> str:
        if not self.label:
            return ''
        else:
            return self.label.capitalize() if self.capitalize_label else self.label


class TabComponent(ViewComponent):

    def __init__(self, label: str, content: ViewComponent, icon_path: str = None, id_: str = None):
        super(TabComponent, self).__init__(id_=id_)
        self.label = label
        self._content = content
        self.icon_path = icon_path

    def get_content(self, type_: Type[V] = ViewComponent) -> V:
        if isinstance(self._content, type_):
            return self._content

        raise Exception(f"'content' is not an instance of '{type_.__name__}'")


class TabGroupComponent(ViewContainer):

    def __init__(self, tabs: List[TabComponent], id_: str = None):
        super(TabGroupComponent, self).__init__(id_=id_, components=tabs)

    def get_tab(self, id_: str) -> Optional[TabComponent]:
        return self.get_component(id_, TabComponent)

    @property
    def tabs(self) -> List[TabComponent]:
        return self.components


class RangeInputComponent(InputViewComponent):

    def __init__(self, id_: str, label: str, tooltip: str, min_value: int, max_value: int,
                 step_value: int, value: Optional[int] = None, max_width: int = None):
        super(RangeInputComponent, self).__init__(id_=id_)
        self.label = label
        self.tooltip = tooltip
        self.min = min_value
        self.max = max_value
        self.step = step_value
        self.value = value
        self.max_width = max_width


class PanelComponent(ViewContainer):

    def __init__(self, components: List[ViewComponent], id_: str = None):
        super(PanelComponent, self).__init__(id_=id_, components=components)
