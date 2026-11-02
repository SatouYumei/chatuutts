; CHATUUTTS 安装包。不包含 VB-CABLE 驱动。

#define AppName "CHATUUTTS"
#define AppVersion "1.0.13"
#define AppPublisher "CHATUUTTS"
#define AppExe "CHATUUTTS.exe"

[Setup]
AppId={{A7C3E1B4-6D28-4F0A-9B55-C4A7EE775001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\CHATUUTTS
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=CHATUUTTS-Setup-{#AppVersion}
SetupIconFile=..\chatuutts.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableWelcomePage=no
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
Source: "..\dist\CHATUUTTS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\package-config\*"; DestDir: "{app}\config"; Excludes: "*.example.json"; Flags: ignoreversion onlyifdoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\changelog\*.md"; DestDir: "{app}\docs\changelog"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "启动 CHATUUTTS"; Flags: nowait postinstall skipifsilent

[Code]
function CableInstalled: Boolean;
var
  Code: Integer;
begin
  Result := False;
  if not Exec(ExpandConstant('{cmd}'), '/c reg query HKLM\SYSTEM\CurrentControlSet\Enum\ROOT\MEDIA /s /f VBAudioVACWDM >nul', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Exit;
  Result := Code = 0;
end;

function InitializeSetup: Boolean;
var
  ErrorCode: Integer;
begin
  if CableInstalled then
  begin
    Result := True;
    Exit;
  end;
  MsgBox('还没有安装 VB-CABLE。' + #13#10 + #13#10 +
    '请先到官方页面下载并安装，重启电脑后，再运行这个安装包。' + #13#10 +
    'https://vb-audio.com/Cable/' + #13#10 + #13#10 +
    '驱动来自 www.vb-cable.com，是捐赠软件。本安装包不附带这个驱动。',
    mbInformation, MB_OK);
  ShellExec('open', 'https://vb-audio.com/Cable/', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  Result := False;
end;
