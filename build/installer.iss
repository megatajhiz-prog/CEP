; Inno Setup script. Compile with:  ISCC /DAppVersion=0.1.0 build\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6D1F3A52-7B64-4C2E-9A0E-5C3B8F4A21D7}
AppName=Water Profiler
AppVersion={#AppVersion}
AppPublisher=Water Profiler
DefaultDirName={autopf}\WaterProfiler
DefaultGroupName=Water Profiler
UninstallDisplayName=Water Profiler
OutputDir=..\Output
OutputBaseFilename=WaterProfiler-Setup-{#AppVersion}
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
Source: "..\dist\WaterProfiler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Water Profiler"; Filename: "{app}\WaterProfiler.exe"
Name: "{autodesktop}\Water Profiler"; Filename: "{app}\WaterProfiler.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WaterProfiler.exe"; Description: "{cm:LaunchProgram,Water Profiler}"; Flags: nowait postinstall skipifsilent
