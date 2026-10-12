; ============================================================================
;  VR 定时关机 —— 独立卸载器（NSIS）
;
;  这是安装目录里的 uninstall.exe，也是「应用和功能」里被调用的那个。
;  它被安装程序用 File 直接放进 $INSTDIR，而不是用 WriteUninstaller：
;  这样安装流程和便携版 / 手工安装共用同一份卸载逻辑，不会两处走样。
;
;  安装目录优先从注册表读（用户可能选了别的路径），读不到就用默认值。
;
;  构建（由 installer/build_installer.py 调用）：
;      makensis /DOUT_FILE="...\VRShutdownTimer-Uninstall.exe" ^
;               /DICON_FILE="...\assets\app.ico" installer\VRShutdownTimer-Uninstall.nsi
; ============================================================================

Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma

!include "LogicLib.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.3.0"
!endif
!ifndef ICON_FILE
  !define ICON_FILE "..\assets\app.ico"
!endif
!ifndef OUT_FILE
  !define OUT_FILE "..\dist_installer\VRShutdownTimer-Uninstall.exe"
!endif

!define APP_KEY     "VRShutdownTimer"
!define APP_DISPLAY "VR 定时关机"
!define APP_EXE     "VRShutdownTimer.exe"
!define RUN_VALUE   "VRShutdownTimer"
!define UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_KEY}"

Name "卸载 ${APP_DISPLAY}"
OutFile "${OUT_FILE}"
Icon "${ICON_FILE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_KEY}"
ShowUninstDetails show

VIProductVersion "${APP_VERSION}.0"
VIFileVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_DISPLAY}"
VIAddVersionKey "FileDescription" "${APP_DISPLAY} 卸载程序"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "CompanyName"     "VR Shutdown Timer"
VIAddVersionKey "LegalCopyright"  "MIT License"
VIAddVersionKey "OriginalFilename" "VRShutdownTimer-Uninstall.exe"

Section
  ; 用户可能把程序装到了自选目录，以注册表记录的为准
  ReadRegStr $0 HKCU "Software\${APP_KEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}

  ; /S 静默卸载时默认就是"确定"
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "确定要卸载 ${APP_DISPLAY} 吗？$\r$\n$\r$\n程序位于：$INSTDIR" \
    /SD IDYES IDYES do_uninstall
  Abort

  do_uninstall:
  ; 先关掉正在运行的程序，否则文件被占用删不掉
  ExecWait '"$SYSDIR\taskkill.exe" /IM "${APP_EXE}" /F'

  ; 只删指向本安装目录的自启项
  ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${RUN_VALUE}"
  ${If} $1 == '"$INSTDIR\${APP_EXE}" --minimized'
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${RUN_VALUE}"
  ${EndIf}

  Delete "$DESKTOP\${APP_DISPLAY}.lnk"
  Delete "$SMPROGRAMS\${APP_DISPLAY}\${APP_DISPLAY}.lnk"
  Delete "$SMPROGRAMS\${APP_DISPLAY}\卸载 ${APP_DISPLAY}.lnk"
  RMDir  "$SMPROGRAMS\${APP_DISPLAY}"

  ; 安装目录是用户选的，只删我们自己的东西，不无脑 RMDir /r
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP_KEY}"

  ; 是否连设置一起删：/SD IDNO 让静默卸载默认保留配置
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "是否同时删除你的设置与日志？$\r$\n$\r$\n$APPDATA\${APP_KEY}" \
    /SD IDNO IDNO keep_config
    RMDir /r "$APPDATA\${APP_KEY}"
  keep_config:

  ; 卸载器自己正被占用，交给一个隐藏的 cmd 等我们退出后收尾
  ExecShell "" '"$SYSDIR\cmd.exe" /c timeout /t 2 /nobreak >nul & rmdir /s /q "$INSTDIR"' SW_HIDE
SectionEnd
