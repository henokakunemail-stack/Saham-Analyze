; =========================================================================
; NSIS Script: SAHAM Desktop Analyzer Installer
; Creates SAHAM_Setup_x64.exe installer for Windows 64-bit
; =========================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; General Definitions
Name "SAHAM Desktop Analyzer"
OutFile "dist\SAHAM_Setup_x64.exe"
InstallDir "$PROGRAMFILES64\SAHAM"
InstallDirRegKey HKLM "Software\SAHAM" "Install_Dir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; Version Information
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "SAHAM Desktop Analyzer"
VIAddVersionKey "CompanyName" "SAHAM Team"
VIAddVersionKey "LegalCopyright" "Copyright (C) 2026 SAHAM"
VIAddVersionKey "FileDescription" "Desktop Stock Market & Money Flow Analyzer"
VIAddVersionKey "FileVersion" "1.0.0.0"

; Interface Settings
!define MUI_ABORTWARNING
; "Run now" must start SAHAM as the normal user, not elevated like this installer:
; explorer.exe launches it at the desktop user's (non-admin) level.
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchSahamUnelevated
!define MUI_FINISHPAGE_RUN_TEXT "Jalankan SAHAM Desktop Analyzer sekarang"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller Pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "Indonesian"
!insertmacro MUI_LANGUAGE "English"

Function LaunchSahamUnelevated
    Exec '"$WINDIR\explorer.exe" "$INSTDIR\SAHAM.exe"'
FunctionEnd

; =========================================================================
; Installer Section
; =========================================================================
Section "SAHAM Desktop Analyzer (required)" SecMain
    SectionIn RO

    ; Close a running SAHAM first, otherwise its files are locked and the update fails halfway
    nsExec::Exec 'taskkill /IM SAHAM.exe /T /F'
    Sleep 1500

    ; Set output path to installation directory
    SetOutPath "$INSTDIR"

    ; Copy all files recursively from dist/SAHAM
    File /r "dist\SAHAM\*.*"

    ; Store installation folder in registry
    WriteRegStr HKLM "Software\SAHAM" "Install_Dir" "$INSTDIR"

    ; Register Uninstaller in Windows Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "DisplayName" "SAHAM Desktop Analyzer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "DisplayIcon" '"$INSTDIR\SAHAM.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "Publisher" "SAHAM Team"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "DisplayVersion" "1.0.0"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM" "NoRepair" 1

    ; Create uninstaller executable
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Create Start Menu Shortcuts
    CreateDirectory "$SMPROGRAMS\SAHAM Desktop Analyzer"
    CreateShortcut "$SMPROGRAMS\SAHAM Desktop Analyzer\SAHAM.lnk" "$INSTDIR\SAHAM.exe" "" "$INSTDIR\SAHAM.exe" 0
    CreateShortcut "$SMPROGRAMS\SAHAM Desktop Analyzer\Uninstall.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0

    ; Create Desktop Shortcut
    CreateShortcut "$DESKTOP\SAHAM Desktop Analyzer.lnk" "$INSTDIR\SAHAM.exe" "" "$INSTDIR\SAHAM.exe" 0
SectionEnd

; =========================================================================
; Uninstaller Section
; =========================================================================
Section "Uninstall"
    ; Close a running SAHAM so its files can be removed
    nsExec::Exec 'taskkill /IM SAHAM.exe /T /F'
    Sleep 1500

    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAHAM"
    DeleteRegKey HKLM "Software\SAHAM"

    ; Remove Shortcuts
    Delete "$DESKTOP\SAHAM Desktop Analyzer.lnk"
    Delete "$SMPROGRAMS\SAHAM Desktop Analyzer\SAHAM.lnk"
    Delete "$SMPROGRAMS\SAHAM Desktop Analyzer\Uninstall.lnk"
    RMDir "$SMPROGRAMS\SAHAM Desktop Analyzer"

    ; Remove only what the installer wrote (dist\SAHAM = SAHAM.exe + _internal\ + uninstaller),
    ; never the whole $INSTDIR: the user may have picked an existing folder with other files.
    Delete "$INSTDIR\SAHAM.exe"
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\uninstall.exe"
    RMDir "$INSTDIR"
SectionEnd
