from logging import Logger
from typing import Dict, Optional, Tuple

from bauh.api.abstract.model import SuggestionPriority


def parse(suggestions_str: str, logger: Optional[Logger] = None, type_: Optional[str] = None,
          splitter: str = '=') \
        -> Dict[str, SuggestionPriority]:
    output = dict()

    for line in suggestions_str.split('\n'):
        clean_line = line.strip()

        if clean_line:
            line_split = clean_line.split(splitter, 1)

            if len(line_split) == 2:
                prio_str, name = line_split[0].strip(), line_split[1].strip()

                if prio_str and name:
                    try:
                        prio = int(line_split[0])
                    except ValueError:
                        if logger:
                            logger.warning(f"Could not parse {type_ + ' ' if type_ else ''}suggestion: {line}")
                        continue

                    output[line_split[1]] = SuggestionPriority(prio)

    return output


def sort_by_priority(names_prios: Dict[str, SuggestionPriority]) -> Tuple[str, ...]:
    return tuple(pair[1] for pair in sorted(((names_prios[n], n) for n in names_prios), reverse=True))
