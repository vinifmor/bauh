from typing import Optional, Any


class Value:

    def __init__(self, value: Optional[Any] = None):
        self.value = value

    def __repr__(self):
        return str(self.value)

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        if isinstance(other, Value):
            return self.value == other.value

    def __hash__(self):
        return hash(self.value)
