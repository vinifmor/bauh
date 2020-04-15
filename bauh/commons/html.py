import re

HTML_RE = re.compile(r'<[^>]+>')


def strip_html(string: str):
    return HTML_RE.sub('', string)


def bold(text: str) -> str:
    return '<span style="font-weight: bold">{}</span>'.format(text)


def link(url: str) -> str:
    return '<a href="{}">{}</a>'.format(url, url)
