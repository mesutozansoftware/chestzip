; ChestZip Windows kurulum programı (Inno Setup 6)
;   iscc packaging\windows\chestzip.iss
; Kurulum .chz dosyalarını ChestZip ile ilişkilendirir ve diğer arşivler için
; "Birlikte aç" menüsüne ekler.

#define AppName "ChestZip"
#define AppVersion "1.0.0"

[Setup]
AppId={{6E0B7C1A-3F0D-4C4B-9C2E-5A1C2E7F9B10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ChestZip contributors
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\..\dist
OutputBaseFilename=ChestZip-setup-windows-x64
SetupIconFile=..\icons\chestzip.ico
UninstallDisplayIcon={app}\chestzip.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\ChestZip\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\icons\chz-document.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\chestzip.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\chestzip.exe"; Tasks: desktopicon

[Registry]
; .chz -> ChestZip.Archive (sahibi ChestZip)
Root: HKA; Subkey: "Software\Classes\.chz"; ValueType: string; ValueName: ""; ValueData: "ChestZip.Archive"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.chz"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-chestzip"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\ChestZip.Archive"; ValueType: string; ValueName: ""; ValueData: "ChestZip Archive"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\ChestZip.Archive\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\chz-document.ico"
Root: HKA; Subkey: "Software\Classes\ChestZip.Archive\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\chestzip.exe"" ""%1"""
; Diğer arşivler için yalnızca "Birlikte aç" seçeneği (varsayılanı değiştirmez)
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".zip"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".7z"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".rar"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".tar"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".gz"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".xz"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\SupportedTypes"; ValueType: string; ValueName: ".bz2"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\chestzip.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\chestzip.exe"" ""%1"""

[Run]
Filename: "{app}\chestzip.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
