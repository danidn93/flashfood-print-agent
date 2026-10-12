#define MyAppName "FlashFood Print Agent"
#define MyAppVersion "1.5.1"
#define MyAppPublisher "FlashFood"
#define MyAppExeName "FlashFoodPrintAgent.exe"

[Setup]
AppId={{A58D0B2E-1D77-4B43-B2C8-FF13A4D2D630}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FlashFood Print Agent
DefaultGroupName=FlashFood Print Agent
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=output
OutputBaseFilename=FlashFoodPrintAgent_Windows_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\dist\FlashFoodPrintAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FlashFood Print Agent"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\FlashFood Print Agent"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar FlashFood Print Agent"; Flags: nowait postinstall skipifsilent
