## fpakman
Graphical user interface for Flatpak application management. It is a tray icon to let the user known when new updates are available.
It has also a management window allowing the user to see all installed applications and update them.

### Developed with:
- Python3 and QT 5.

### Requirements
- libappindicator3 (for GTK3 desktop environments)
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
As **fpakman** package. There is also a staging version (**fpakman-staging**) but is intended for testing and it may not work properly.


### Manual installation:
If you prefer a manual and isolated installation, type the following commands within the cloned project folder:
```
python3 -m venv env
env/bin/pip install .
env/bin/fpakman
```

### Autostart
In order to autostart the application, use your Desktop Environment settings to register it as startup script ("fpakman").
(P.S: the installation script currently does not do that)

### Settings
You can change some application settings via environment variables:
- **FPAKMAN_UPDATE_NOTIFICATION**: enable or disable system updates notifications. Use **0** (disable) or **1** (enable, default).
- **FPAKMAN_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.

### Roadmap
- Search and install applications
- Uninstall applications
