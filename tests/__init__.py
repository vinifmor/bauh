
class AnyInstance(object):
    def __init__(self, instance_class: type):
        self._class = instance_class

    def __eq__(self, other):
        return other is not None and isinstance(other, self._class)

    def __repr__(self):
        return f'<ANY_{self._class.__name__}>'
