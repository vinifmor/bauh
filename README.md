## bauh

Non-official graphical user interface for Flatpak / Snap application management (old **fpakman**). It is a tray icon that let the user known when new updates are available and
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
sudo pip3 install bauh
```

**AUR**

As **bauh** package. There is also a staging version (**bauh-staging**) but is intended for testing and may not work properly.


### Manual installation:
If you prefer a manual and isolated installation, type the following commands within the cloned project folder:
```
python3 -m venv env
env/bin/pip install .
env/bin/bauh
```

### Autostart
In order to autostart the application, use your Desktop Environment settings to register it as a startup application / script (**bauh**).


### Settings
You can change some application settings via environment variables or arguments (type ```bauh --help``` to get more information).
- **BAUH_UPDATE_NOTIFICATION**: enable or disable system updates notifications. Use **0** (disable) or **1** (enable, default).
- **BAUH_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.
- **BAUH_LOCALE**: define a custom app translation for a given locale key (e.g: 'pt', 'en', 'es', ...). Default: system locale.
- **BAUH_CACHE_EXPIRATION**: define a custom expiration time in SECONDS for cached API data. Default: 3600 (1 hour).
- **BAUH_ICON_EXPIRATION**: define a custom expiration time in SECONDS for cached icons. Default: 300 (5 minutes).
- **BAUH_DISK_CACHE**: enables / disables disk cache. When disk cache is enabled, the installed applications data are loaded faster. Use **0** (disable) or **1** (enable, default).
- **BAUH_DOWNLOAD_ICONS**: Enables / disables app icons download. It may improve the application speed depending on how applications data are being retrieved. Use **0** (disable) or **1** (enable, default).
- **BAUH_FLATPAK**: enables / disables flatpak usage. Use **0** (disable) or **1** (enabled, default)
- **BAUH_SNAP**: enables / disables snap usage. Use **0** (disable) or **1** (enabled, default)
- **BAUH_CHECK_PACKAGING_ONCE**: If the available supported packaging types should be checked ONLY once. It improves the application speed if enabled, but can generate errors if you uninstall any packaging technology while using it, and every time a supported packaging type is installed it will only be available after a restart. Use **0** (disable, default) or **1** (enable).
- **BAUH_TRAY**: If the tray icon and update-check daemon should be created. Use **0** (disable, default) or **1** (enable).
- **BAUH_SUGGESTIONS**: If application suggestions should be displayed if no app is installed (runtimes do not count as apps). Use **0** (disable) or **1** (enable, default).

### How to improve the application performance
- If you don't care about a specific packaging technology and don't want the app to deal with it, just disable it via the specific argument or environment variable. For instance, if I don't care
about **snaps**, I can initialize the application setting "snap=0" (**bauh --snap=0**). This will improve the application response time, since it won't need to do any verifications associated
with the technology that I don't care every time an action is executed.
- If you don't care about restarting the app every time a new supported packaging technology is installed, set "check-packaging-once=1" (**bauh --check-packaging-once=1**). This can reduce the application response time up to 80% in some scenarios, since it won't need to recheck if the packaging type is available for every action you request.
- If you don't mind to see the applications icons, you can set "download-icons=0" (**bauh --download-icons=0**). The application may have a slight response improvement, since it will reduce the parallelism within it.
- If you don't mind app suggestions, disable it (**bauh --sugs=0**)

### Roadmap
- Support for other packaging technologies
- Separate modules for each packaging technology
- Memory and performance improvements
- Improve user experience
