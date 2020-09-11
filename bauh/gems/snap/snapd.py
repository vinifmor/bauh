import socket
import traceback
from logging import Logger
from typing import Optional, List

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool

from bauh.commons.system import run_cmd

URL_BASE = 'http://snapd/v2'


class SnapdConnection(HTTPConnection):
    def __init__(self):
        super(SnapdConnection, self).__init__('localhost')

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/run/snapd.socket")


class SnapdConnectionPool(HTTPConnectionPool):
    def __init__(self):
        super(SnapdConnectionPool, self).__init__('localhost')

    def _new_conn(self):
        return SnapdConnection()


class SnapdAdapter(HTTPAdapter):

    def get_connection(self, url, proxies=None):
        return SnapdConnectionPool()


class SnapdClient:

    def __init__(self, logger: Logger):
        self.logger = logger
        self.session = self._new_session()

    def _new_session(self) -> Optional[Session]:
        try:
            session = Session()
            session.mount("http://snapd/", SnapdAdapter())
            return session
        except:
            self.logger.error("Could not establish a connection to 'snapd.socker'")
            traceback.print_exc()

    def query(self, query: str) -> Optional[List[dict]]:
        final_query = query.strip()

        if final_query and self.session:
            res = self.session.get(url='{}/find'.format(URL_BASE), params={'q': final_query})

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

    def find_by_name(self, name: str) -> Optional[List[dict]]:
        if name and self.session:
            res = self.session.get('{}/find?name={}'.format(URL_BASE, name))

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

    def list_all_snaps(self) -> List[dict]:
        if self.session:
            res = self.session.get('{}/snaps'.format(URL_BASE))

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

        return []

    def list_only_apps(self) -> List[dict]:
        if self.session:
            res = self.session.get('{}/apps'.format(URL_BASE))

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']
        return []

    def list_commands(self, name: str) -> List[dict]:
        if self.session:
            res = self.session.get('{}/apps?names={}'.format(URL_BASE, name))

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return [r for r in json_res['result'] if r['snap'] == name]
        return []


def is_running() -> bool:
    status = run_cmd('systemctl is-active snapd.service snapd.socket', print_error=False)
    if not status:
        return False
    else:
        for status in status.split('\n'):
            if status.strip().lower() == 'active':
                return True

        return False
