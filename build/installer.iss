; Inno Setup script. Compile with:  ISCC /DAppVersion=0.1.0 build\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6D1F3A52-7B64-4C2E-9A0E-5C3B8F4A21D7}
AppName=CEPWater
AppVersion={#AppVersion}
AppPublisher=Control Energy Pasargad
SetupIconFile=..\assets\brand\app.ico
UninstallDisplayIcon={app}\CEPWater.exe
DefaultDirName={autopf}\CEPWater
DefaultGroupName=CEPWater
UninstallDisplayName=CEPWater
OutputDir=..\Output
OutputBaseFilename=CEPWater-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\CEPWater\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CEPWater"; Filename: "{app}\CEPWater.exe"
Name: "{autodesktop}\CEPWater"; Filename: "{app}\CEPWater.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CEPWater.exe"; Description: "{cm:LaunchProgram,CEPWater}"; Flags: nowait postinstall skipifsilent
