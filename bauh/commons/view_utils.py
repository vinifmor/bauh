import locale
from typing import Tuple, Optional, Iterable

from bauh.api.abstract.view import SelectViewType, InputOption, SingleSelectComponent


def new_select(label: str, tip: Optional[str], id_: str, opts: Iterable[Tuple[Optional[str], object, Optional[str]]], value: object, max_width: Optional[int] = None,
               type_: SelectViewType = SelectViewType.RADIO, capitalize_label: bool = True):
    inp_opts = [InputOption(label=o[0].capitalize(), value=o[1], tooltip=o[2]) for o in opts]
    def_opt = [o for o in inp_opts if o.value == value]
    return SingleSelectComponent(label=label,
                                 tooltip=tip,
                                 options=inp_opts,
                                 default_option=def_opt[0] if def_opt else inp_opts[0],
                                 max_per_line=len(inp_opts),
                                 max_width=max_width,
                                 type_=type_,
                                 id_=id_,
                                 capitalize_label=capitalize_label)


def get_human_size_str(size, positive_sign: bool = False) -> Optional[str]:
    if type(size) in (int, float, str):
        int_size = abs(int(size))

        if int_size == 0:
            return '0'

        for power, unit in enumerate(('B', 'kB', 'MB', 'GB', 'TB', 'PB')):
            size_unit = int_size / (1000 ** power)

            if size_unit < 1000:
                size_unit = size_unit if size > 0 else size_unit * -1
                localized_size = locale.format_string('%.2f', size_unit)
                size_str = f'{int(size_unit)} {unit}' if unit == 'B' else f"{localized_size} {unit}"
                return f'+{size_str}' if positive_sign and size_unit > 0 else size_str
