; ============================================================================
;  VR 定时关机 —— NSIS 安装脚本（Steam 的安装器也是 NSIS 做的）
;
;  构建（由 installer/build_installer.py 调用，也可手工执行）：
;      makensis /DAPP_VERSION=1.2.0 ^
;               /DSOURCE_DIR="<仓库>\dist_portable\VRShutdownTimer" ^
;               /DOUT_FILE="<仓库>\dist_installer\VRShutdownTimer-Setup-1.2.0.exe" ^
;               /DUNINSTALLER_EXE="<仓库>\dist_installer\VRShutdownTimer-Uninstall.exe" ^
;               /DICON_FILE="<仓库>\assets\app.ico" ^
;               /DLICENSE_FILE="<仓库>\LICENSE" ^
;               installer\VRShutdownTimer.nsi
;
;  行为：
;    * 当前用户级安装（RequestExecutionLevel user），不弹 UAC；
;    * 默认装到 %LOCALAPPDATA%\Programs\VRShutdownTimer，可自选目录；
;    * 可选桌面快捷方式 / 开始菜单项；
;    * 登记「应用和功能」卸载项，卸载器是独立的 VRShutdownTimer-Uninstall.exe；
;    * 静默安装：Setup.exe /S ，指定目录：Setup.exe /S /D=C:\path
;
;  本文件必须保存成 **UTF-8 with BOM**，否则 makensis 会因为中文报
;  "Bad text encoding" 而拒绝编译。
; ============================================================================

Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma
; 注意：**不要**把 LZMA 字典调大（例如 SetCompressorDictSize 64）。
; NSIS 解压器会在安装器启动时按字典大小一次性申请内存，字典一大（64MB）
; 在内存受限 / 被作业对象限制的环境里会分配失败，表现为双击后瞬间退出、
; 退出码 2、没有任何提示。实测 8MB（默认值）与 64MB 的产物体积只差 0.8MB
; （30.8MB vs 30.0MB），完全没必要冒这个风险。

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"

; ----------------------------------------------------------------- 可覆盖项 --
!ifndef APP_VERSION
  !define APP_VERSION "1.2.0"
!endif
!ifndef SOURCE_DIR
  !define SOURCE_DIR "..\dist_portable\VRShutdownTimer"
!endif
!ifndef OUT_FILE
  !define OUT_FILE "..\dist_installer\VRShutdownTimer-Setup-${APP_VERSION}.exe"
!endif
!ifndef UNINSTALLER_EXE
  !define UNINSTALLER_EXE "..\dist_installer\VRShutdownTimer-Uninstall.exe"
!endif
!ifndef ICON_FILE
  !define ICON_FILE "..\assets\app.ico"
!endif
!ifndef LICENSE_FILE
  !define LICENSE_FILE "..\LICENSE"
!endif

!define APP_KEY      "VRShutdownTimer"
!define APP_DISPLAY  "VR 定时关机"
!define APP_EXE      "VRShutdownTimer.exe"
!define RUN_VALUE    "VRShutdownTimer"
!define PROJECT_URL  "https://github.com/"
!define UNINST_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_KEY}"

Name "${APP_DISPLAY} ${APP_VERSION}"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_KEY}"
InstallDirRegKey HKCU "Software\${APP_KEY}" "InstallDir"
BrandingText "${APP_DISPLAY} ${APP_VERSION}"
ShowInstDetails show
XPStyle on
CRCCheck on

VIProductVersion "${APP_VERSION}.0"
VIFileVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_DISPLAY}"
VIAddVersionKey "FileDescription" "${APP_DISPLAY} 安装程序"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "CompanyName"     "VR Shutdown Timer"
VIAddVersionKey "LegalCopyright"  "MIT License"
VIAddVersionKey "OriginalFilename" "VRShutdownTimer-Setup-${APP_VERSION}.exe"

; ------------------------------------------------------------------- 界面 --
!define MUI_ICON "${ICON_FILE}"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${APP_DISPLAY} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "这是一个面向 VR 玩家的定时关机小工具。$\r$\n$\r$\n安装会为**当前用户**进行，不需要管理员权限，也不会修改系统设置。$\r$\n$\r$\n点击「下一步」继续。"

!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 ${APP_DISPLAY}"
!define MUI_FINISHPAGE_LINK "${PROJECT_URL}"
!define MUI_FINISHPAGE_LINK_LOCATION "${PROJECT_URL}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENSE_FILE}"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

; ------------------------------------------------------------------- 安装 --
Section "主程序（必需）" SEC_MAIN
  SectionIn RO

  ; 升级安装：先把还在跑的旧版本关掉，否则文件被占用会写不进去。
  ; 这里刻意用核心指令 ExecWait 而不是 nsExec 插件：NSIS 会把插件 DLL
  ; 释放到 %TEMP% 再加载，在临时目录被重定向 / 加固的环境里这一步会失败，
  ; 安装器会瞬间退出且不给任何提示（实测：退出码 2、0.1 秒）。
  ; ExecWait 不需要任何插件，代价只是 taskkill 的窗口闪一下。
  ExecWait '"$SYSDIR\taskkill.exe" /IM "${APP_EXE}" /F'

  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*.*"
  File "/oname=uninstall.exe" "${UNINSTALLER_EXE}"

  WriteRegStr HKCU "Software\${APP_KEY}" "InstallDir" "$INSTDIR"
SectionEnd

Section "桌面快捷方式" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${APP_DISPLAY}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 SW_SHOWNORMAL "" "${APP_DISPLAY} —— 定时关机小工具"
SectionEnd

Section "开始菜单项" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\${APP_DISPLAY}"
  CreateShortCut "$SMPROGRAMS\${APP_DISPLAY}\${APP_DISPLAY}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 SW_SHOWNORMAL "" "${APP_DISPLAY} —— 定时关机小工具"
  CreateShortCut "$SMPROGRAMS\${APP_DISPLAY}\卸载 ${APP_DISPLAY}.lnk" \
    "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
SectionEnd

; 「应用和功能」条目：始终写入，不出现在组件列表里
Section "-卸载信息"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_DISPLAY}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "VR Shutdown Timer"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegStr   HKCU "${UNINST_KEY}" "URLInfoAbout"    "${PROJECT_URL}"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  ; 已安装体积（KB），供「应用和功能」显示
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN}     "程序本体：$INSTDIR"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP}  "在桌面创建「${APP_DISPLAY}」快捷方式"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} "在开始菜单创建「${APP_DISPLAY}」文件夹"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ${IfNot} ${AtLeastWin7}
    MessageBox MB_OK|MB_ICONSTOP "本程序需要 Windows 7 或更高版本。"
    Abort
  ${EndIf}
FunctionEnd
