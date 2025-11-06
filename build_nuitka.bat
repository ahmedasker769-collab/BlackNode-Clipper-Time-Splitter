@echo off
echo Starting Nuitka build for BlackNode-Clipper...

:: This command builds the application as a single executable file, 
:: compiling with MinGW64 and including all necessary dependencies.

python -m nuitka ^
--output-filename=BlackNodeClipper ^
--mingw64 ^
--standalone ^
--onefile ^
--windows-icon-from-ico=assets/icon.ico ^
--output-dir=dist ^
--remove-output ^
--assume-yes-for-downloads ^
--plugin-enable=pyside6 ^
--plugin-enable=numpy ^
--include-package=modules ^
--include-data-dir=assets=assets ^
--include-data-file=config.yaml=config.yaml ^
main.py

echo Build complete.
pause