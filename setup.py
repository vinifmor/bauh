
import os

from setuptools import setup, find_packages

DESCRIPTION = (
    "Graphical interface to manage Linux applications (AppImage, Arch / AUR, Flatpak, Snap and Web)"
)

AUTHOR = "bauh developers"
AUTHOR_EMAIL = "bauh4linux@gmail.com"
NAME = 'bauh'
URL = "https://github.com/vinifmor/" + NAME

file_dir = os.path.dirname(os.path.abspath(__file__))

with open(file_dir + '/requirements.txt', 'r') as f:
    requirements = [line.strip() for line in f.readlines() if line]


with open(file_dir + '/{}/__init__.py'.format(NAME), 'r') as f:
    exec(f.readlines()[0])


setup(
    name=NAME,
    version=eval('__version__'),
    description=DESCRIPTION,
    long_description=DESCRIPTION,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    python_requires=">=3.5",
    url=URL,
    packages=find_packages(exclude=["tests.*", "tests"]),
    package_data={NAME: ["view/resources/locale/*", "view/resources/img/*",  "view/resources/style/*", 'view/resources/style/*/img/*', "gems/*/resources/img/*", "gems/*/resources/locale/*", "desktop/*"]},
    install_requires=requirements,
    test_suite="tests",
    entry_points={
        "console_scripts": [
            "{name}={name}.app:main".format(name=NAME),
            "{name}-tray={name}.app:tray".format(name=NAME),
            "{name}-cli={name}.cli.app:main".format(name=NAME)
        ]
    },
    include_package_data=True,
    license="zlib/libpng",
    classifiers=[
        'Topic :: Utilities',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ]
)
