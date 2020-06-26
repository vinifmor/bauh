import os


def find_appimage_file(folder: str) -> str:
    for r, d, files in os.walk(folder):
        for f in files:
            if f.lower().endswith('.appimage'):
                return '{}/{}'.format(folder, f)
