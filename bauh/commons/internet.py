import socket


class InternetChecker:

    def __init__(self, offline: bool):
        self.offline = offline

    def is_available(self) -> bool:
        if self.offline:
            return False

        try:
            socket.gethostbyname("w3.org")
            return True
        except Exception:
            return False
