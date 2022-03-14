from typing import List, Tuple, Optional

from bauh.api.abstract.view import SelectViewType, InputOption, SingleSelectComponent


SIZE_UNITS = ((1, 'B'), (1024, 'Kb'), (1048576, 'Mb'), (1073741824, 'Gb'),
              (1099511627776, 'Tb'), (1125899906842624, 'Pb'))


def new_select(label: str, tip: str, id_: str, opts: List[Tuple[Optional[str], object, Optional[str]]], value: object, max_width: int,
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


def get_human_size_str(size) -> Optional[str]:
    if type(size) in (int, float, str):
        int_size = abs(int(size))

        if int_size == 0:
            return '0'

        for div, unit in SIZE_UNITS:

            size_unit = int_size / div

            if size_unit < 1024:
                size_unit = size_unit if size > 0 else size_unit * -1
                return f'{int(size_unit)} {unit}' if unit == 'B' else f'{size_unit:.2f} {unit}'
