ERR_FORCE Installer
===================

Windows:
Run INSTALL_ON_WINDOWS.cmd on the target Windows PC.
Advanced/silent entrypoint: install_app.cmd
Do not run as Administrator unless you intentionally want to install for the
Administrator account.

What this installer includes:
- ERR_FORCE application files
- the full game folder
- a bundled Python 3.10 installer
- offline pip wheels for the Python packages, including tobii-research
- ERR_FORCE_fast.cmd fast launcher
- ERR_FORCE.exe fallback launcher
- Desktop shortcut with the ERR_FORCE icon

Default install location:
%LOCALAPPDATA%\ER_FORCE

If the Desktop shortcut is missing, open:
%LOCALAPPDATA%\ER_FORCE
and run:
ERR_FORCE_fast.cmd

The installer also writes INSTALLED_TO.txt and
RUN_ERR_FORCE_FROM_INSTALLED_LOCATION.cmd next to the installer files.

Custom install location:
install_app.cmd -InstallDir "C:\ER_FORCE"

macOS bonus:
Run install_app.command on macOS. This path is experimental and online: it uses
the Mac's installed Python 3.10+ and downloads Python packages with pip.
The UI may run, but FlightGear, Tobii drivers/SDK, and hardware calibration may
require separate macOS-specific setup.

Important Tobii note:
The Python tobii-research package is installed offline by this installer.
The physical eye tracker can still require Tobii's Windows driver / Eye Tracker Manager
to be installed and calibrated on the target machine.
