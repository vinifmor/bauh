APP_ATTRS = ('name', 'description', 'github', 'source', 'version', 'url_download', 'url_icon', 'license', 'author')
RELEASE_ATTRS = ('version', 'url_download', 'published_at')


SEARCH_APPS_BY_NAME_OR_DESCRIPTION = "SELECT {} FROM apps".format(','.join(APP_ATTRS)) + " WHERE lower(name) LIKE '%{}%' or lower(description) LIKE '%{}%'"
FIND_APP_ID_BY_NAME_AND_GITHUB = "SELECT id FROM apps WHERE lower(name) = '{}' and lower(github) = '{}'"
FIND_RELEASES_BY_APP_ID = "SELECT {} FROM releases".format(','.join(RELEASE_ATTRS)) + " WHERE app_id = {} ORDER BY version desc"
