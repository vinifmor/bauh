import re

HTML_RE = re.compile(r'<[^>]+>')


def strip_html(string: str):
    return HTML_RE.sub('', string)
