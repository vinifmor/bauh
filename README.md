## fpakman
Graphical user interface for Flatpak application management. It is a tray icon to let the user known when new updates are available.
It has also a management window allowing the user to see all installed applications and update them.

### Developed with:
- Python3 and QT 5.

### Requirements
#### Debian-based distros
- libappindicator3 (for GTK3 desktop environments)
- python3-venv
#### Arch-based distros
- python
- python-requests
- python-pip
- python-pyqt5


### Installation script
You can install the application without compromising your system via the provided installation script called 'install.py'.
Type in the terminal:
```
sudo python3 install.py.
```
If you want to uninstall the application, just call the script the same way.

To start the application, type in the terminal:
```
fpakman
```

### Manual installation:
The following script shows how to install the application in a separate python environment in order to not mess up with your
system's python libraries. Inside the project directory type:
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
- **FPAKMAN_UPDATE_NOTIFICATION: enable or disable system updates notifications. Use 0 (disable) or 1 (enable, default).
- **FPAKMAN_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.

### Roadmap
- Show updates being applied.
- Search and install applications.
- Uninstall applications.
