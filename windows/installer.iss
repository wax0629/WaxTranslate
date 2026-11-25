#ifndef AppSource
  #error Define AppSource as the extracted portable application's directory
#endif
#ifndef OutputDir
  #error Define OutputDir as the directory for the installer
#endif

[Setup]
AppId=WaxTranslate.Desktop
AppName=WaxTranslate
AppVersion=0.3.0
DefaultDirName={localappdata}\Programs\WaxTranslate
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
MinVersion=10.0.22000
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\WaxTranslate.exe
SetupIconFile=waxtranslate.ico
OutputDir={#OutputDir}
OutputBaseFilename=WaxTranslate-Windows-x64-Setup
Compression=zip/2
WizardStyle=modern

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\WaxTranslate"; Filename: "{app}\WaxTranslate.exe"; Parameters: "--show"

[Run]
Filename: "{app}\WaxTranslate.exe"; Parameters: "--show"; Description: "Open WaxTranslate"; Flags: nowait postinstall skipifsilent
