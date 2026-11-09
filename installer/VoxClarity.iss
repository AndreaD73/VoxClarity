; VoxClarity Windows installer (Inno Setup 6). Per-user, no administrator rights.
; Build:  ISCC.exe /DAppVersion=0.4.6 /DStageDir=C:\path\to\tracked-files installer\VoxClarity.iss
; StageDir = a folder holding exactly the tracked repository files (CI makes it with "git archive").
; Output: installer\Output\VoxClarity-Setup-<version>.exe
; Test switch (not shown to users): run the setup with /SKIPDEPS=1 to copy files only, without running install.ps1.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\build\stage"
#endif

[Setup]
AppId={{6B1F3D0A-7C2E-4C55-9A44-5D0E8B7F2A11}
AppName=VoxClarity
AppVersion={#AppVersion}
AppVerName=VoxClarity {#AppVersion}
AppPublisher=Andrea D.
AppPublisherURL=https://github.com/AndreaD73/VoxClarity
AppSupportURL=https://github.com/AndreaD73/VoxClarity/issues
AppUpdatesURL=https://github.com/AndreaD73/VoxClarity/releases
DefaultDirName={localappdata}\Programs\VoxClarity
DefaultGroupName=VoxClarity
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=VoxClarity-Setup-{#AppVersion}
SetupIconFile={#StageDir}\icon.ico
UninstallDisplayIcon={app}\icon.ico
LicenseFile={#StageDir}\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Signing-relevant metadata (SignPath requires product name and version on every signed binary).
VersionInfoVersion={#AppVersion}
VersionInfoProductName=VoxClarity
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=Andrea D.
VersionInfoDescription=VoxClarity installer
VersionInfoCopyright=MIT licence

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
english.DesktopIcon=Create a &desktop shortcut
english.RepairName=VoxClarity - finish or repair installation
english.InstallingDeps=Installing Python packages, ffmpeg and shortcuts. A console window shows the progress; a large download (several GB) is needed the first time. Please wait...
english.DepsFailed=The component installation did not complete (code %1). Your files are installed. Read the console message, then run "VoxClarity - finish or repair installation" from the Start menu.
english.AskRemoveSettings=Also delete your VoxClarity settings and logs (%APPDATA%\VoxClarity) and temporary files (%LOCALAPPDATA%\VoxClarity)?%n%nChoose No to keep them.
english.ModelsNote=The AI models in the Hugging Face cache (%USERPROFILE%\.cache\huggingface) are shared and were NOT removed.
italian.DesktopIcon=Crea un collegamento sul &desktop
italian.RepairName=VoxClarity - completa o ripara l'installazione
italian.InstallingDeps=Installo i pacchetti Python, ffmpeg e i collegamenti. Una finestra console mostra l'avanzamento; la prima volta serve un download grande (diversi GB). Attendere...
italian.DepsFailed=L'installazione dei componenti non e' terminata (codice %1). I file sono installati. Leggi il messaggio nella console, poi avvia "VoxClarity - completa o ripara l'installazione" dal menu Start.
italian.AskRemoveSettings=Eliminare anche le impostazioni e i log di VoxClarity (%APPDATA%\VoxClarity) e i file temporanei (%LOCALAPPDATA%\VoxClarity)?%n%nScegli No per conservarli.
italian.ModelsNote=I modelli AI nella cache di Hugging Face (%USERPROFILE%\.cache\huggingface) sono condivisi e NON sono stati rimossi.

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "installer,.github,tests,docs,.gitattributes,.gitignore"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\VoxClarity"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\VoxClarity.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\{cm:RepairName}"; Filename: "{app}\Installa.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\VoxClarity"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\VoxClarity.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[UninstallDelete]
; Folders created by install.ps1 (not part of the installed file list).
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\work"
Type: files; Name: "{app}\VoxClarity.lnk"
Type: dirifempty; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
  cmd: String;
begin
  if (CurStep = ssPostInstall) and (ExpandConstant('{param:SKIPDEPS|0}') <> '1') then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('InstallingDeps');
    { Same thing Installa.bat does: it runs install.ps1 (ExecutionPolicy Bypass) in a visible console. }
    cmd := '/c "' + AddBackslash(ExpandConstant('{app}')) + 'Installa.bat"';
    if WizardSilent then
      cmd := '/c "set VOX_NOPAUSE=1&& "' + AddBackslash(ExpandConstant('{app}')) + 'Installa.bat""';
    if not Exec(ExpandConstant('{cmd}'), cmd, ExpandConstant('{app}'), SW_SHOWNORMAL, ewWaitUntilTerminated, rc) then
      rc := -1;
    if rc <> 0 then
      SuppressibleMsgBox(FmtMessage(CustomMessage('DepsFailed'), [IntToStr(rc)]), mbError, MB_OK, IDOK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if SuppressibleMsgBox(CustomMessage('AskRemoveSettings'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      begin
      { Shared by every copy of VoxClarity on this PC, so only removed on explicit request. }
      DelTree(ExpandConstant('{userappdata}\VoxClarity'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\VoxClarity'), True, True, True);
    end;
    SuppressibleMsgBox(CustomMessage('ModelsNote'), mbInformation, MB_OK, IDOK);
  end;
end;
