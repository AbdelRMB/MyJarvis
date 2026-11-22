; Programme d'installation de Wesley (Inno Setup 6) : "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installateur.iss
; Prérequis : avoir construit dist\Wesley avec  .venv\Scripts\pyinstaller wesley.spec --noconfirm

; La version vient de wesley/version.py (construire.bat et GitHub Actions passent /DVersion=x.y.z)
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6E0B7C1A-4C1F-4B9B-9E2A-3F7D1A2B9C01}
AppName=Wesley
AppVersion={#Version}
AppVerName=Wesley {#Version}
AppPublisher=Abdelrahim Riche
AppCopyright=© Abdelrahim Riche
VersionInfoCompany=Abdelrahim Riche
VersionInfoDescription=Installation de Wesley
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\Programs\Wesley
DefaultGroupName=Wesley
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installateur
OutputBaseFilename=WesleySetup-{#Version}
SetupIconFile=wesley.ico
UninstallDisplayIcon={app}\Wesley.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "demarrage"; Description: "Lancer Wesley au démarrage de Windows (caché, il attend que tu l'appelles)"; GroupDescription: "Options :"
Name: "bureau"; Description: "Créer une icône sur le bureau"; GroupDescription: "Options :"

[Files]
Source: "dist\Wesley\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Wesley"; Filename: "{app}\Wesley.exe"; Comment: "Ton assistant personnel"
Name: "{userprograms}\Mettre à jour Wesley"; Filename: "{app}\Wesley.exe"; Parameters: "--maj"; Comment: "Voir et installer les mises à jour de Wesley"
Name: "{userdesktop}\Wesley"; Filename: "{app}\Wesley.exe"; Tasks: bureau

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Wesley"; ValueData: """{app}\Wesley.exe"" --cache"; Tasks: demarrage; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Wesley.exe"; Description: "Lancer Wesley maintenant"; Flags: nowait postinstall skipifsilent
; mise à jour depuis l'appli (installation silencieuse) : Wesley redémarre tout seul
Filename: "{app}\Wesley.exe"; Flags: nowait skipifnotsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Wesley.exe /F"; Flags: runhidden; RunOnceId: "ArretWesley"

[Messages]
french.WelcomeLabel2=Wesley va être installé sur ce PC.%n%nIl démarre avec Windows, reste caché près de l'horloge, et apparaît quand tu dis « Wesley » ou que tu appuies sur Ctrl+Alt+W.%n%nSa mémoire est partagée avec tes autres PC via OneDrive.
