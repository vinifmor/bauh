import http.client as http_client


class InternetChecker:

    def __init__(self, offline: bool):
        self.offline = offline

    def is_available(self) -> bool:
        if self.offline:
            return False

        conn = http_client.HTTPConnection("www.google.com", timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except:
            conn.close()
            return False
