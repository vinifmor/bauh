from model import flatpak


def list_packages():
    packages = flatpak.list_installed()

    if packages:
        packages = [pak for pak in packages if not pak['runtime']]

        if packages:
            packages.sort(key=lambda p: p['name'].lower())

            for pak in packages:
                pak['update'] = flatpak.check_update(pak['ref'])

    return packages
