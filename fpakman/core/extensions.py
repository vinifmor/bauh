import inspect


def find_manager(member):
    if inspect.isclass(member) and inspect.getmro(member)[1].__name__ == 'ApplicationManager':
            return member
    elif inspect.ismodule(member):
        for name, mod in inspect.getmembers(member):
            manager_found = find_manager(mod)
            if manager_found:
                return manager_found
