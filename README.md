## fpakman

Non-official graphical user interface for Flatpak application management. It is a tray icon that let the user known when new updates are available and
an application management panel where you can search, update, install and uninstall applications.

### Developed with:
- Python3 and Qt5.

### Requirements
- libappindicator3 ( for GTK3 desktop environments )
#### Debian-based distros
- python3-venv
#### Arch-based distros
- python
- python-requests
- python-virtualenv
- python-pip
- python-pyqt5

### Distribution
**PyPi**
```
sudo pip3 install fpakman
```

**AUR**

As **fpakman** package. There is also a staging version (**fpakman-staging**) but is intended for testing and may not work properly.


### Manual installation:
If you prefer a manual and isolated installation, type the following commands within the cloned project folder:
```
python3 -m venv env
env/bin/pip install .
env/bin/fpakman
```

### Autostart
In order to autostart the application, use your Desktop Environment settings to register it as a startup application / script ("fpakman").


### Settings
You can change some application settings via environment variables or arguments (type ```fpakman --help``` to get more information).
- **FPAKMAN_UPDATE_NOTIFICATION**: enable or disable system updates notifications. Use **0** (disable) or **1** (enable, default).
- **FPAKMAN_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.
- **FPAKMAN_LOCALE**: define a custom app translation for a given locale key (e.g: 'pt', 'en', 'es', ...). Default: system locale.
- **FPAKMAN_CACHE_EXPIRATION**: define a custom expiration time in SECONDS for cached API data. Default: 3600 (1 hour).
- **FPAKMAN_ICON_EXPIRATION**: define a custom expiration time in SECONDS for cached icons. Default: 300 (5 minutes).
- **FPAKMAN_DISK_CACHE**: enables / disables disk cache. When disk cache is enabled, the installed applications data are loaded faster. Use **0** (disable) or **1** (enable, default).


### Roadmap
- Support for other packaging technologies
- Memory and performance improvements
