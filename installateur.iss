; Programme d'installation de Jarvis (Inno Setup 6) : "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installateur.iss
; Prérequis : avoir construit dist\Jarvis avec  .venv\Scripts\pyinstaller jarvis.spec --noconfirm

; La version vient de jarvis/version.py (construire.bat et GitHub Actions passent /DVersion=x.y.z)
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6E0B7C1A-4C1F-4B9B-9E2A-3F7D1A2B9C01}
AppName=Jarvis
AppVersion={#Version}
AppVerName=Jarvis {#Version}
AppPublisher=AbdelRMB
AppCopyright=© AbdelRMB
VersionInfoCompany=AbdelRMB
VersionInfoDescription=Installation de Jarvis
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\Programs\Jarvis
DefaultGroupName=Jarvis
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installateur
OutputBaseFilename=JarvisSetup-{#Version}
SetupIconFile=jarvis.ico
UninstallDisplayIcon={app}\Jarvis.exe
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
Name: "demarrage"; Description: "Lancer Jarvis au démarrage de Windows (caché, il attend que tu l'appelles)"; GroupDescription: "Options :"
Name: "bureau"; Description: "Créer une icône sur le bureau"; GroupDescription: "Options :"

[Files]
Source: "dist\Jarvis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Jarvis"; Filename: "{app}\Jarvis.exe"; Comment: "Ton assistant personnel"
Name: "{userprograms}\Mettre à jour Jarvis"; Filename: "{app}\Jarvis.exe"; Parameters: "--maj"; Comment: "Voir et installer les mises à jour de Jarvis"
Name: "{userdesktop}\Jarvis"; Filename: "{app}\Jarvis.exe"; Tasks: bureau

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Jarvis"; ValueData: """{app}\Jarvis.exe"" --cache"; Tasks: demarrage; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Jarvis.exe"; Description: "Lancer Jarvis maintenant"; Flags: nowait postinstall skipifsilent
; mise à jour depuis l'appli (installation silencieuse) : Jarvis redémarre tout seul
Filename: "{app}\Jarvis.exe"; Flags: nowait skipifnotsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Jarvis.exe /F"; Flags: runhidden; RunOnceId: "ArretJarvis"

[Messages]
french.WelcomeLabel2=Jarvis va être installé sur ce PC.%n%nIl démarre avec Windows, reste caché près de l'horloge, et apparaît quand tu dis « Jarvis » ou que tu appuies sur Ctrl+Alt+J.%n%nSa mémoire est partagée avec tes autres PC via OneDrive.
