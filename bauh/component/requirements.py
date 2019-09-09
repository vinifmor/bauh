import re
from typing import List, Dict

RE_RULES = re.compile(r'([\w.\-_]+)|([>=<][>=<]?[\w.]+)')
RE_SPLIT_RULE = re.compile(r'([<=>]+)(.+)')
RE_BAUH_REQ = re.compile(r'bauh_.+')


class Requirement:

    def __init__(self, name: str, rules: List[str] = None):
        self.name = name
        self.rules = rules

    def accepts(self, version: str) -> bool:
        if self.rules:
            for rule in self.rules:
                res = eval("'{}'{}".format(version, rule))
                if not res:
                    return False
        return True

    def __str__(self):
        return '{} ({}){}'.format(self.__class__.__name__, self.name, ' {}'.format(self.rules) if self.rules else '')


def parse(line: str) -> Requirement:
    match = RE_RULES.findall(line)

    if match:
        rules = None

        if len(match) > 1:
            rules = []
            for r in match[1:]:
                split_rule = RE_SPLIT_RULE.findall(r[1])[0]
                rules.append("{}'{}'".format(split_rule[0], split_rule[1]))

        return Requirement(name=match[0][0], rules=rules)


def full_parse(text: str, only_components: bool = True) -> Dict[str, Requirement]:
    res = {}
    req_list = RE_BAUH_REQ.findall(text) if only_components else text.split('\n')

    for l in req_list:
        if l and not l.startswith('#'):
            req = parse(l)
            res[req.name] = req

    return res
