@echo off
rem 一键打包（等价于 build.ps1）
rem   build.bat              打包单文件版
rem   build.bat portable     打包便携目录版
rem   build.bat installer    打包便携目录版 + Windows 安装包
rem   build.bat all          单文件 + 便携目录版 + 安装包
setlocal
cd /d "%~dp0"

set MODE=%1
if "%MODE%"=="" set MODE=onefile

echo ==^> 生成图标与版本资源
python tools\make_icon.py || goto :error
python tools\make_version_info.py || goto :error
if not exist "assets\app.ico" goto :error

if /i "%MODE%"=="all" goto :all
if /i "%MODE%"=="portable" goto :portable
if /i "%MODE%"=="installer" goto :installer

:onefile
echo ==^> 打包单文件版
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build VRShutdownTimer.spec || goto :error
if not exist "dist\VRShutdownTimer.exe" goto :error
echo ==^> 完成: dist\VRShutdownTimer.exe
goto :done

:portable
echo ==^> 打包便携目录版
python -m PyInstaller --noconfirm --clean --distpath dist_portable --workpath build_portable VRShutdownTimer-portable.spec || goto :error
if not exist "dist_portable\VRShutdownTimer\VRShutdownTimer.exe" goto :error
echo ==^> 完成: dist_portable\VRShutdownTimer\
goto :done

:installer
echo ==^> 打包便携目录版
python -m PyInstaller --noconfirm --clean --distpath dist_portable --workpath build_portable VRShutdownTimer-portable.spec || goto :error
echo ==^> 打包安装包
python installer\build_installer.py || goto :error
goto :done

:all
echo ==^> 打包单文件版
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build VRShutdownTimer.spec || goto :error
echo ==^> 打包便携目录版
python -m PyInstaller --noconfirm --clean --distpath dist_portable --workpath build_portable VRShutdownTimer-portable.spec || goto :error
echo ==^> 打包安装包
python installer\build_installer.py || goto :error
echo ==^> 完成: dist\VRShutdownTimer.exe、dist_portable\VRShutdownTimer\、dist_installer\
goto :done

:done
pause
exit /b 0

:error
echo.
echo ==^> 打包失败
pause
exit /b 1
