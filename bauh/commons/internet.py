import socket


class InternetChecker:

    def __init__(self, offline: bool):
        self.offline = offline

    def is_available(self) -> bool:
        if self.offline:
            return False

        try:
            socket.gethostbyname('google.com')
            return True
        except:
            return False

