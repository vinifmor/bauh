from typing import Optional


class PackageNotFoundException(Exception):

    def __init__(self, name: str):
        self.name = name


class PackageInHoldException(Exception):

    def __init__(self, name: Optional[str] = None):
        self.name = name
