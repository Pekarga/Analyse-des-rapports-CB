; Installateur Windows de l'application « Analyse des rapports des CB » (Inno Setup 6).
; Compilation (après PyInstaller) : iscc /DVersionApp=2.0.0 packaging\installateur.iss
#ifndef VersionApp
  #define VersionApp "2.0.0"
#endif
#define NomApp "Analyse des rapports des CB"

[Setup]
AppId={{6F1E2B4D-9C3A-4E57-8B21-5D0C7A9E4F13}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName={#NomApp} {#VersionApp}
AppPublisher=Direction du Contrôle Budgétaire
DefaultDirName={autopf}\AnalyseRapportsCB
DefaultGroupName={#NomApp}
DisableProgramGroupPage=yes
; Installation possible sans droits d'administrateur (dans le profil de l'utilisateur)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installateur
OutputBaseFilename=AnalyseRapportsCB-Installation-{#VersionApp}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\AnalyseRapportsCB.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\AnalyseRapportsCB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NomApp}"; Filename: "{app}\AnalyseRapportsCB.exe"
Name: "{group}\Désinstaller {#NomApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\AnalyseRapportsCB.exe"; Tasks: bureau

[Run]
Filename: "{app}\AnalyseRapportsCB.exe"; Description: "Lancer {#NomApp}"; Flags: nowait postinstall skipifsilent
