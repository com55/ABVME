; ABVME - Inno Setup script (per-user install, no admin required).
; Compile from repo root:
;   ISCC.exe /DMyAppVersion=0.1.9 packaging\windows\ABVME.iss
; Packages Nuitka standalone output at dist_main\ABVME.dist
; Paths below are relative to the repo root via SourceDir.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "ABVME"
#define MyAppExeName "ABVME.exe"
#define MyAppPublisher "com55"
#define MyAppURL "https://github.com/com55/ABVME"
#define MyAppProgIdBundle "ABVME.bundle"
#define MyAppProgIdUnity3d "ABVME.unity3d"

[Setup]
; AppId MUST stay constant across releases so upgrades replace in place.
AppId={{B306AF69-104D-40B1-9520-A69642EE2AE9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
; Script lives under packaging\windows\; resolve assets/dist from repo root.
SourceDir=..\..
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
DisableDirPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=ABVME-Windows-x64-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupMutex=ABVMESetupMutex
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "Associate .bundle and .unity3d files with {#MyAppName}"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "dist_main\ABVME.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.bundle\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgIdBundle}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.bundle"; ValueType: string; ValueName: ""; ValueData: "{#MyAppProgIdBundle}"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}"; ValueType: string; ValueName: ""; ValueData: "Unity Asset Bundle"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

Root: HKA; Subkey: "Software\Classes\.unity3d\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgIdUnity3d}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.unity3d"; ValueType: string; ValueName: ""; ValueData: "{#MyAppProgIdUnity3d}"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}"; ValueType: string; ValueName: ""; ValueData: "Unity Asset Bundle"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{localappdata}\{#MyAppName}\update"""; Flags: runhidden; RunOnceId: "DelUpdateCache"

[Code]
var
  DeleteSettingsChecked: Boolean;

function GetUninstallString(): String;
var
  Key: String;
  S: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B306AF69-104D-40B1-9520-A69642EE2AE9}_is1';
  S := '';
  if not RegQueryStringValue(HKCU, Key, 'UninstallString', S) then
    RegQueryStringValue(HKLM, Key, 'UninstallString', S);
  Result := S;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UnInstStr, OldExe: String;
  ResultCode, Waited: Integer;
begin
  if CurStep <> ssInstall then
    Exit;
  UnInstStr := GetUninstallString();
  if UnInstStr = '' then
    Exit;
  UnInstStr := RemoveQuotes(UnInstStr);
  OldExe := ExtractFilePath(UnInstStr) + '{#MyAppExeName}';
  if Exec(UnInstStr, '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Waited := 0;
    while FileExists(OldExe) and (Waited < 100) do
    begin
      Sleep(200);
      Waited := Waited + 1;
    end;
  end;
end;

{ Interactive uninstall: checkbox page (default unchecked). Silent uninstall
  (e.g. in-place upgrade) skips the page and never deletes settings. }
procedure InitializeUninstallProgressForm();
var
  UninstallPage: TNewNotebookPage;
  UninstallButton: TNewButton;
  DeleteSettingsCheckbox: TNewCheckBox;
  PageText: TNewStaticText;
  OriginalPageNameLabel: String;
  OriginalPageDescriptionLabel: String;
  OriginalCancelButtonEnabled: Boolean;
  OriginalCancelButtonModalResult: Integer;
  Ctrl: TWinControl;
begin
  DeleteSettingsChecked := False;
  if UninstallSilent then
    Exit;

  Ctrl := UninstallProgressForm.CancelButton;
  UninstallButton := TNewButton.Create(UninstallProgressForm);
  UninstallButton.Parent := UninstallProgressForm;
  UninstallButton.Left := Ctrl.Left - Ctrl.Width - ScaleX(10);
  UninstallButton.Top := Ctrl.Top;
  UninstallButton.Width := Ctrl.Width;
  UninstallButton.Height := Ctrl.Height;
  UninstallButton.TabOrder := Ctrl.TabOrder;
  UninstallButton.Caption := 'Uninstall';
  UninstallButton.ModalResult := mrOk;
  UninstallProgressForm.CancelButton.TabOrder := UninstallButton.TabOrder + 1;

  UninstallPage := TNewNotebookPage.Create(UninstallProgressForm);
  UninstallPage.Notebook := UninstallProgressForm.InnerNotebook;
  UninstallPage.Parent := UninstallProgressForm.InnerNotebook;
  UninstallPage.Align := alClient;
  UninstallProgressForm.InnerNotebook.ActivePage := UninstallPage;

  Ctrl := UninstallProgressForm.StatusLabel;
  PageText := TNewStaticText.Create(UninstallProgressForm);
  PageText.Parent := UninstallPage;
  PageText.Top := Ctrl.Top;
  PageText.Left := Ctrl.Left;
  PageText.Width := Ctrl.Width;
  PageText.Height := ScaleY(40);
  PageText.AutoSize := False;
  PageText.WordWrap := True;
  PageText.ShowAccelChar := False;
  PageText.Caption := 'Click Uninstall to remove {#MyAppName} from this computer.';

  DeleteSettingsCheckbox := TNewCheckBox.Create(UninstallProgressForm);
  DeleteSettingsCheckbox.Parent := UninstallPage;
  DeleteSettingsCheckbox.Top := PageText.Top + PageText.Height + ScaleY(12);
  DeleteSettingsCheckbox.Left := Ctrl.Left;
  DeleteSettingsCheckbox.Width := Ctrl.Width;
  DeleteSettingsCheckbox.Caption := 'Also delete application settings (preferences)';
  DeleteSettingsCheckbox.Checked := False;

  OriginalPageNameLabel := UninstallProgressForm.PageNameLabel.Caption;
  OriginalPageDescriptionLabel := UninstallProgressForm.PageDescriptionLabel.Caption;
  OriginalCancelButtonEnabled := UninstallProgressForm.CancelButton.Enabled;
  OriginalCancelButtonModalResult := UninstallProgressForm.CancelButton.ModalResult;

  UninstallProgressForm.PageNameLabel.Caption := 'Uninstall {#MyAppName}';
  UninstallProgressForm.PageDescriptionLabel.Caption := 'Remove the application. Settings are kept unless you opt in below.';
  UninstallProgressForm.CancelButton.Enabled := True;
  UninstallProgressForm.CancelButton.ModalResult := mrCancel;

  if UninstallProgressForm.ShowModal = mrCancel then
    Abort;

  DeleteSettingsChecked := DeleteSettingsCheckbox.Checked;

  UninstallButton.Visible := False;
  UninstallProgressForm.PageNameLabel.Caption := OriginalPageNameLabel;
  UninstallProgressForm.PageDescriptionLabel.Caption := OriginalPageDescriptionLabel;
  UninstallProgressForm.CancelButton.Enabled := OriginalCancelButtonEnabled;
  UninstallProgressForm.CancelButton.ModalResult := OriginalCancelButtonModalResult;
  UninstallProgressForm.InnerNotebook.ActivePage := UninstallProgressForm.InstallingPage;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DeleteSettingsChecked then
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\ABVME');
end;
