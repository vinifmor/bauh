from typing import List, Tuple, Optional

from bauh.api.abstract.view import SelectViewType, InputOption, SingleSelectComponent


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
