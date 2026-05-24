ER_FORCE Offline Installer
==========================

Run install_app.cmd on the target Windows PC.

What this installer includes:
- ER_FORCE application files
- the full game folder
- a bundled Python 3.10 installer
- offline pip wheels for the Python packages, including tobii-research
- ER_FORCE.exe launcher

Default install location:
%LOCALAPPDATA%\ER_FORCE

Custom install location:
install_app.cmd -InstallDir "C:\ER_FORCE"

Important Tobii note:
The Python tobii-research package is installed offline by this installer.
The physical eye tracker can still require Tobii's Windows driver / Eye Tracker Manager
to be installed and calibrated on the target machine.
