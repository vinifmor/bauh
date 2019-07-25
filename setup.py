import os
from setuptools import setup, find_packages

DESCRIPTION = (
    "Graphical user interface to manage Flatpak / Snap applications."
)

AUTHOR = "Vinicius Moreira"
AUTHOR_EMAIL = "vinicius_fmoreira@hotmail.com"
URL = "https://github.com/vinifmor/fpakman"

file_dir = os.path.dirname(os.path.abspath(__file__))

with open(file_dir + '/requirements.txt', 'r') as f:
    requirements = [line.strip() for line in f.readlines() if line]


with open(file_dir + '/fpakman/__init__.py', 'r') as f:
    exec(f.readlines()[0])


setup(
    name="fpakman",
    version=eval('__version__'),
    description=DESCRIPTION,
    long_description=DESCRIPTION,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    python_requires=">=3.5",
    url=URL,
    packages=find_packages(),
    package_data={"fpakman": ["resources/locale/*", "resources/img/*"]},
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "fpakman=fpakman.app"
        ]
    },
    include_package_data=True,
    license="zlib/libpng",
    classifiers=[
        'Topic :: Utilities',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ]
)
