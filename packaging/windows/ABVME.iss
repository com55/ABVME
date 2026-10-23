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

[Files]
Source: "dist_main\ABVME.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Advertise ABVME as a handler without changing the user's Windows default.
Root: HKA; Subkey: "Software\Classes\.bundle\OpenWithProgids"; ValueType: none; ValueName: "{#MyAppProgIdBundle}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}"; ValueType: string; ValueName: ""; ValueData: "ABVME Asset Bundle"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdBundle}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKA; Subkey: "Software\Classes\.unity3d\OpenWithProgids"; ValueType: none; ValueName: "{#MyAppProgIdUnity3d}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}"; ValueType: string; ValueName: ""; ValueData: "ABVME Unity Asset Bundle"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppProgIdUnity3d}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Keep the legacy Applications ProgID functional for existing Windows UserChoice
; records while giving it a stable display name in Open with.
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".bundle"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".unity3d"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

; Register with Default Apps so Windows owns the user's default selection.
Root: HKA; Subkey: "Software\ABVME\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\ABVME\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Asset Bundles Viewer Modifier and Exporter"
Root: HKA; Subkey: "Software\ABVME\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\ABVME\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bundle"; ValueData: "{#MyAppProgIdBundle}"
Root: HKA; Subkey: "Software\ABVME\Capabilities\FileAssociations"; ValueType: string; ValueName: ".unity3d"; ValueData: "{#MyAppProgIdUnity3d}"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\ABVME\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{localappdata}\{#MyAppName}\update"""; Flags: runhidden; RunOnceId: "DelUpdateCache"

[Code]
var
  DeleteSettingsChecked: Boolean;

procedure RemoveLegacyExtensionDefault(const Extension, ProgId: String);
var
  CurrentProgId: String;
begin
  { Releases through 0.3.0 wrote the extension's default value directly.
    Remove only our legacy value; never touch Explorer's hashed UserChoice. }
  if RegQueryStringValue(HKCU, 'Software\Classes\' + Extension, '', CurrentProgId) and
     (CurrentProgId = ProgId) then
    RegDeleteValue(HKCU, 'Software\Classes\' + Extension, '');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RemoveLegacyExtensionDefault('.bundle', '{#MyAppProgIdBundle}');
    RemoveLegacyExtensionDefault('.unity3d', '{#MyAppProgIdUnity3d}');
  end;
end;

{ Interactive uninstall: checkbox page (default unchecked). Silent uninstall
  skips the page and never deletes settings. Inno upgrades use the stable AppId
  directly and do not run the old uninstaller. }
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
