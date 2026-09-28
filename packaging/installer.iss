#ifndef AppVersion
  #error AppVersion must be passed by tools/build.ps1
#endif
#ifndef SourceDir
  #error SourceDir must be passed by tools/build.ps1
#endif
#ifndef OutputDir
  #error OutputDir must be passed by tools/build.ps1
#endif

[Setup]
AppId={{D9442C2D-5C16-4B2F-90D2-2D2E2E5298B7}
AppName=Arnold DW
AppVersion={#AppVersion}
AppVerName=Arnold DW {#AppVersion}
AppPublisher=ArnoldGods
DefaultDirName={autopf}\Arnold DW
DefaultGroupName=Arnold DW
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
OutputDir={#OutputDir}
OutputBaseFilename=ArnoldDW-{#AppVersion}-setup
SetupIconFile={#SourceDir}\_internal\logo\icon.ico
UninstallDisplayIcon={app}\Arnold DW.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
english.CreateDesktopIcon=Create a desktop shortcut
turkish.CreateDesktopIcon=Masaüstü kısayolu oluştur
english.AdditionalShortcuts=Additional shortcuts:
turkish.AdditionalShortcuts=Ek kısayollar:
english.LaunchDescription=Launch Arnold DW
turkish.LaunchDescription=Arnold DW'yi başlat
english.DeleteAppDataPrompt=Delete Arnold DW settings and data in your AppData folder?
turkish.DeleteAppDataPrompt=AppData klasöründeki Arnold DW ayarları ve verileri silinsin mi?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalShortcuts}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Arnold DW"; Filename: "{app}\Arnold DW.exe"
Name: "{autodesktop}\Arnold DW"; Filename: "{app}\Arnold DW.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Arnold DW.exe"; Description: "{cm:LaunchDescription}"; Flags: postinstall nowait skipifsilent

[Code]
var
  DeleteUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  DeleteUserData := False;
  if DirExists(ExpandConstant('{userappdata}\Arnold DW')) then
    DeleteUserData := MsgBox(
      CustomMessage('DeleteAppDataPrompt'),
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2
    ) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DeleteUserData then
    DelTree(ExpandConstant('{userappdata}\Arnold DW'), True, True, True);
end;
