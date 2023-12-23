APP_ATTRS = ('name', 'description', 'repository', 'source', 'version', 'url_download', 'url_icon',
             'url_screenshot', 'license', 'author', 'categories')
RELEASE_ATTRS = ('version', 'url_download', 'published_at')


SEARCH_APPS_BY_NAME_OR_DESCRIPTION = f"SELECT {','.join(APP_ATTRS)} FROM apps" + \
                                     " WHERE lower(name) LIKE '%{}%' or lower(description) LIKE '%{}%'"
FIND_APP_ID_BY_REPO_AND_NAME = "SELECT id FROM apps WHERE lower(repository) = '{}' and lower(name) = '{}'"
FIND_APPS_BY_NAME = "SELECT name, repository, version, url_download FROM apps WHERE lower(name) IN ({})"
FIND_APPS_BY_NAME_ONLY_NAME = "SELECT name FROM apps WHERE lower(name) IN ({})"
FIND_APPS_BY_NAME_FULL = "SELECT {} FROM apps".format(','.join(APP_ATTRS)) + " WHERE lower(name) IN ({})"
FIND_RELEASES_BY_APP_ID = "SELECT {} FROM releases".format(','.join(RELEASE_ATTRS)) + " WHERE app_id = {}"
