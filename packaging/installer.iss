; Arnold DW - Windows setup wizard and uninstaller (Inno Setup 6.3+).
; Built by tools/build.ps1, which passes AppVersion, SourceDir, OutputDir and LicenseFile.

#ifndef AppVersion
  #error AppVersion must be passed by tools/build.ps1
#endif
#ifndef SourceDir
  #error SourceDir must be passed by tools/build.ps1
#endif
#ifndef OutputDir
  #error OutputDir must be passed by tools/build.ps1
#endif

#define AppName "Arnold DW"
#define AppExeName "Arnold DW.exe"
#define AppPublisher "ArnoldGods"
#define AppURL "https://github.com/arnoldgodsx/ArnoldDW"
#define AppUserModelID "ArnoldDW.YoutubeDownloader.1"

[Setup]
AppId={{D9442C2D-5C16-4B2F-90D2-2D2E2E5298B7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases/latest
AppCopyright=Copyright (C) 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Admin install by default; the dialog lets users without admin rights install for themselves only.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=ArnoldDW-{#AppVersion}-setup
SetupIconFile={#SourceDir}\_internal\logo\icon.ico
#ifdef LicenseFile
LicenseFile={#LicenseFile}
#endif
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
WizardImageFile=wizard_large.bmp,wizard_large_highdpi.bmp
WizardSmallImageFile=wizard_small.bmp,wizard_small_highdpi.bmp
ShowLanguageDialog=auto
UsePreviousLanguage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=force
RestartApplications=no
Uninstallable=yes
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
english.CreateDesktopIcon=Create a &desktop shortcut
turkish.CreateDesktopIcon=&Masaüstü kısayolu oluştur
english.AdditionalShortcuts=Additional shortcuts:
turkish.AdditionalShortcuts=Ek kısayollar:
english.LaunchDescription=Launch Arnold DW
turkish.LaunchDescription=Arnold DW'yi başlat
english.UninstallShortcut=Uninstall Arnold DW
turkish.UninstallShortcut=Arnold DW'yi kaldır
english.AppRunningUninstall=Arnold DW is running. Close it and continue uninstalling?%n%nDownloads that are in progress will be stopped.
turkish.AppRunningUninstall=Arnold DW çalışıyor. Kapatılıp kaldırma işlemine devam edilsin mi?%n%nSüren indirmeler durdurulur.
english.DeleteAppDataPrompt=Also delete your Arnold DW settings, download history, logs and engine updates?%n%nYour downloaded files are NOT touched.
turkish.DeleteAppDataPrompt=Arnold DW ayarları, indirme geçmişi, günlükleri ve motor güncellemeleri de silinsin mi?%n%nİndirdiğiniz dosyalara DOKUNULMAZ.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalShortcuts}"; Flags: unchecked

[InstallDelete]
; PyInstaller onedir builds change their file set between versions: drop the old
; runtime before an upgrade so no stale DLL or module is left behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{group}\{cm:UninstallShortcut}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchDescription}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Anything the app may have created next to itself (e.g. Python byte-code caches).
Type: filesandordirs; Name: "{app}\_internal"
; ffmpeg and Deno, downloaded by the app on first launch (program files, not user data).
Type: filesandordirs; Name: "{localappdata}\{#AppName}\runtime"
Type: dirifempty; Name: "{localappdata}\{#AppName}"
Type: dirifempty; Name: "{app}"

[Code]
const
  AppExe = '{#AppExeName}';

var
  DeleteUserData: Boolean;

function UserDataDir(): String;
begin
  Result := ExpandConstant('{userappdata}\{#AppName}');
end;

{ True when an "Arnold DW.exe" process is running (any session visible to this user). }
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{cmd}'),
      '/C tasklist /FI "IMAGENAME eq ' + AppExe + '" /NH | find /I "' + AppExe + '" >NUL',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode = 0;
end;

procedure StopApp();
var
  ResultCode: Integer;
  Tries: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "' + AppExe + '"', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
  { Give Windows a moment to release the file handles. }
  Tries := 0;
  while IsAppRunning() and (Tries < 20) do
  begin
    Sleep(250);
    Tries := Tries + 1;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  DeleteUserData := False;

  if IsAppRunning() then
  begin
    if SuppressibleMsgBox(CustomMessage('AppRunningUninstall'), mbConfirmation,
        MB_YESNO, IDYES) <> IDYES then
    begin
      Result := False;
      Exit;
    end;
    StopApp();
  end;

  { Silent uninstalls keep user data unless /SUPPRESSMSGBOXES is combined with
    an explicit choice; the default answer is "No". }
  if DirExists(UserDataDir()) then
    DeleteUserData := SuppressibleMsgBox(CustomMessage('DeleteAppDataPrompt'),
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DeleteUserData then
    DelTree(UserDataDir(), True, True, True);
end;
