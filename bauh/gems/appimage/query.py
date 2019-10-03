ATTRS = ('name', 'description', 'github', 'source', 'version', 'url_download', 'url_icon', 'license')

_SELECT_BASE = "SELECT {} FROM apps".format(','.join(ATTRS))

SEARCH_BY_NAME_OR_DESCRIPTION = _SELECT_BASE + " WHERE lower(name) LIKE '%{}%' or lower(description) LIKE '%{}%'"
