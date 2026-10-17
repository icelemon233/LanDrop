; UTF-8 source. Current-user installation; application data is never removed.
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!ifndef AppKey
  !define AppKey "LanDrop.Cinna"
!endif
!ifndef ShortcutName
  !define ShortcutName "LanDrop"
!endif
!ifndef DataArgs
  !define DataArgs ""
!endif
!ifndef LegacyShortcutName
  !define LegacyShortcutName "隔空传"
!endif
!define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppKey}"
Name "LanDrop ${AppVersion}"
BrandingText "LanDrop"
OutFile "${OutputFile}"
InstallDir "$LOCALAPPDATA\Programs\LanDrop"
InstallDirRegKey HKCU "${UninstallKey}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
CRCCheck force
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "${AppVersion}.0"
VIAddVersionKey /LANG=2052 "ProductName" "LanDrop"
VIAddVersionKey /LANG=2052 "FileDescription" "LanDrop Windows 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${AppVersion}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "${Developer}"
VIAddVersionKey /LANG=2052 "CompanyName" "${Developer}"
!define MUI_ICON "${ProjectRoot}\resources\app.ico"
!define MUI_UNICON "${ProjectRoot}\resources\app.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${ProjectRoot}\resources\installer-header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "${ProjectRoot}\resources\installer-header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${ProjectRoot}\resources\installer-sidebar.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装 LanDrop ${AppVersion}"
!define MUI_WELCOMEPAGE_TEXT "电脑端使用独立桌面窗口，手机扫码后即可传文件。$\r$\n$\r$\n支持 Windows 10/11 x64，无需安装 Python。缺少 WebView2 时，安装程序会从 Microsoft 下载运行时。$\r$\n$\r$\n升级和卸载会保留收到的文件与共享设置。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\LanDrop.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS '${DataArgs}'
!define MUI_FINISHPAGE_RUN_TEXT "打开LanDrop"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Var SetupMutex
Var CheckResult
Var Helper
Var AllowClose
Var WebViewVersion

Function ReadWebViewVersion
  StrCpy $WebViewVersion ""
  SetRegView 32
  ReadRegStr $WebViewVersion HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    ReadRegStr $WebViewVersion HKLM "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  SetRegView 64
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    ReadRegStr $WebViewVersion HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    ReadRegStr $WebViewVersion HKLM "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
FunctionEnd

Function EnsureWebView
  Call ReadWebViewVersion
  ${If} $WebViewVersion != ""
  ${AndIf} $WebViewVersion != "0.0.0.0"
    Return
  ${EndIf}
  DetailPrint "正在安装 Microsoft Edge WebView2 运行时…"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=webview2-setup.exe "${WebViewBootstrapper}"
  ExecWait '"$PLUGINSDIR\webview2-setup.exe" /silent /install' $0
  Call ReadWebViewVersion
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    MessageBox MB_OK|MB_ICONSTOP "WebView2 运行时未能安装。请连接网络后重试安装，或先从 Microsoft 安装 WebView2。原程序和收到的文件未修改。" /SD IDOK
    SetErrorLevel 14
    Quit
  ${EndIf}
FunctionEnd

!macro Guard Prefix
Function ${Prefix}PrepareApp
  ExecWait '"$Helper" --headless --check-running ${DataArgs}' $CheckResult
  ${If} $CheckResult = 0
    Return
  ${EndIf}
  ${If} $CheckResult != 10
    MessageBox MB_OK|MB_ICONSTOP "无法确认LanDrop的运行状态。请先正常退出程序，再重试。" /SD IDOK
    SetErrorLevel 20
    Quit
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/CLOSEAPP" $1
  StrCpy $AllowClose 1
  ${If} ${Errors}
    StrCpy $AllowClose 0
  ${EndIf}
  IfSilent silent_check ask_close
  silent_check:
    ${If} $AllowClose = 0
      SetErrorLevel 10
      Quit
    ${EndIf}
    Goto close_app
  ask_close:
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "LanDrop正在运行。$\r$\n$\r$\n点击“确定”后，程序会正常退出，未完成的传输会中断。已保存的文件和共享设置会保留。$\r$\n$\r$\n点击“取消”停止本次操作。" /SD IDCANCEL IDOK close_app
    SetErrorLevel 10
    Quit
  close_app:
    DetailPrint "正在等待LanDrop正常退出…"
    ExecWait '"$Helper" --headless --prepare-upgrade ${DataArgs}' $CheckResult
    ${If} $CheckResult != 0
      MessageBox MB_OK|MB_ICONSTOP "LanDrop尚未正常退出，程序文件未修改。请关闭系统文件选择窗口，退出应用后重试。" /SD IDOK
      SetErrorLevel 20
      Quit
    ${EndIf}
FunctionEnd
!macroend
!insertmacro Guard ""
!insertmacro Guard "un."

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "需要 Windows 10/11 x64。" /SD IDOK
    SetErrorLevel 13
    Quit
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    SetErrorLevel 13
    Quit
  ${EndIf}
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\${AppKey}.Installing") p .r0 ?e'
  Pop $1
  StrCpy $SetupMutex $0
  ${If} $1 = 183
    MessageBox MB_OK|MB_ICONEXCLAMATION "另一个安装或卸载程序正在运行。" /SD IDOK
    SetErrorLevel 12
    Quit
  ${EndIf}
FunctionEnd

Function .onVerifyInstDir
  GetFullPathName $0 "$INSTDIR"
  ${GetRoot} $0 $1
  ${If} $0 == "$1\"
  ${OrIf} $0 == "$WINDIR"
  ${OrIf} $0 == "$LOCALAPPDATA"
  ${OrIf} $0 == "$LOCALAPPDATA\LanDrop"
    Abort
  ${EndIf}
FunctionEnd

Section "LanDrop应用（必选）" Application
  SectionIn RO
  Call .onVerifyInstDir
  ReadRegStr $0 HKCU "${UninstallKey}" "InstallLocation"
  ${If} $0 != ""
  ${AndIf} $0 != $INSTDIR
    MessageBox MB_OK|MB_ICONSTOP "升级请选择原安装位置，或先卸载旧版再更换位置。文件和共享设置会保留。" /SD IDOK
    SetErrorLevel 11
    Quit
  ${EndIf}
  IfFileExists "$INSTDIR\Uninstall.exe" 0 location_checked
    ${If} $0 != $INSTDIR
      MessageBox MB_OK|MB_ICONSTOP "此文件夹中已有其他卸载程序，请选择新的安装文件夹。" /SD IDOK
      SetErrorLevel 11
      Quit
    ${EndIf}
  location_checked:
  Call EnsureWebView
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=maintenance.exe "${Payload}\LanDrop.exe"
  StrCpy $Helper "$PLUGINSDIR\maintenance.exe"
  Call PrepareApp
  SetOutPath "$INSTDIR"
  File "${Payload}\LanDrop.exe"
  File "${Payload}\app.ico"
  File "${Payload}\使用说明.txt"
  File "${Payload}\THIRD_PARTY_NOTICES.txt"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ; Remove only the previous product's known entries after copying the new app.
  ReadRegStr $1 HKCU "${UninstallKey}" "DisplayName"
  ${If} $1 == "${LegacyShortcutName}"
    Delete "$INSTDIR\隔空传.exe"
    Delete "$DESKTOP\${LegacyShortcutName}.lnk"
    Delete "$SMPROGRAMS\${LegacyShortcutName}\${LegacyShortcutName}.lnk"
    Delete "$SMPROGRAMS\${LegacyShortcutName}\卸载.lnk"
    RMDir "$SMPROGRAMS\${LegacyShortcutName}"
  ${EndIf}
  CreateDirectory "$SMPROGRAMS\${ShortcutName}"
  CreateShortcut "$SMPROGRAMS\${ShortcutName}\${ShortcutName}.lnk" "$INSTDIR\LanDrop.exe" '${DataArgs}' "$INSTDIR\app.ico" 0
  CreateShortcut "$SMPROGRAMS\${ShortcutName}\卸载.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\app.ico" 0
  WriteRegStr HKCU "${UninstallKey}" "DisplayName" "${ShortcutName}"
  WriteRegStr HKCU "${UninstallKey}" "DisplayVersion" "${AppVersion}"
  WriteRegStr HKCU "${UninstallKey}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UninstallKey}" "Publisher" "${Developer}"
  WriteRegStr HKCU "${UninstallKey}" "DisplayIcon" "$INSTDIR\app.ico,0"
  WriteRegStr HKCU "${UninstallKey}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UninstallKey}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UninstallKey}" "NoModify" 1
  WriteRegDWORD HKCU "${UninstallKey}" "NoRepair" 1
  WriteRegDWORD HKCU "${UninstallKey}" "EstimatedSize" ${InstalledSizeKB}
SectionEnd

Section "桌面快捷方式" Desktop
  CreateShortcut "$DESKTOP\${ShortcutName}.lnk" "$INSTDIR\LanDrop.exe" '${DataArgs}' "$INSTDIR\app.ico" 0
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\${AppKey}.Installing") p .r0 ?e'
  Pop $1
  StrCpy $SetupMutex $0
  ${If} $1 = 183
    SetErrorLevel 12
    Quit
  ${EndIf}
  ReadRegStr $0 HKCU "${UninstallKey}" "InstallLocation"
  ${If} $0 != $INSTDIR
    MessageBox MB_OK|MB_ICONSTOP "安装位置与记录不符，已停止卸载。" /SD IDOK
    SetErrorLevel 11
    Quit
  ${EndIf}
FunctionEnd

Section "Uninstall"
  StrCpy $Helper "$INSTDIR\LanDrop.exe"
  IfFileExists "$Helper" 0 remove_files
    Call un.PrepareApp
  remove_files:
  SetOutPath "$TEMP"
  Delete "$INSTDIR\LanDrop.exe"
  Delete "$INSTDIR\app.ico"
  Delete "$INSTDIR\使用说明.txt"
  Delete "$INSTDIR\THIRD_PARTY_NOTICES.txt"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\${ShortcutName}.lnk"
  Delete "$SMPROGRAMS\${ShortcutName}\${ShortcutName}.lnk"
  Delete "$SMPROGRAMS\${ShortcutName}\卸载.lnk"
  RMDir "$SMPROGRAMS\${ShortcutName}"
  DeleteRegKey HKCU "${UninstallKey}"
  RMDir "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
