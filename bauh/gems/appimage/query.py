APP_ATTRS = ('name', 'description', 'github', 'source', 'version', 'url_download', 'url_icon', 'url_screenshot', 'license', 'author', 'categories')
RELEASE_ATTRS = ('version', 'url_download', 'published_at')


SEARCH_APPS_BY_NAME_OR_DESCRIPTION = "SELECT {} FROM apps".format(','.join(APP_ATTRS)) + " WHERE lower(name) LIKE '%{}%' or lower(description) LIKE '%{}%'"
FIND_APP_ID_BY_NAME_AND_GITHUB = "SELECT id FROM apps WHERE lower(name) = '{}' and lower(github) = '{}'"
FIND_APPS_BY_NAME = "SELECT name, github, version, url_download FROM apps WHERE lower(name) IN ({})"
FIND_APPS_BY_NAME_ONLY_NAME = "SELECT name FROM apps WHERE lower(name) IN ({})"
FIND_APPS_BY_NAME_FULL = "SELECT {} FROM apps".format(','.join(APP_ATTRS)) + " WHERE lower(name) IN ({})"
FIND_RELEASES_BY_APP_ID = "SELECT {} FROM releases".format(','.join(RELEASE_ATTRS)) + " WHERE app_id = {} ORDER BY version desc"
