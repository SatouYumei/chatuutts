# CHATUUTTS

当前版本：**1.0.13**（2026-11-02）

CHATUUTTS 是一个 Windows 桌面上的中文文字转语音小工具。输入文字或按快捷键，它就会用选好的声音读出来；还可以把声音送进虚拟麦克风，让游戏和语音软件里的人听到。

## 主要功能

- **在线音色**：10 个微软中文 Neural 音色，支持风格（温柔、欢快等）、角色、语速、音调、音量。
- **本地离线音色**：8 个本地音色（本地 女1–4、男1–4），断网也能说话。
- **声音档案**：把音色和参数存成多个档案，一键切换。
- **快捷发言**：全局快捷键直接说出预设的句子。
- **虚拟麦克风**：配合 VB-CABLE，把语音送到其他软件的麦克风输入。
- **读音修正**：固定搭配和词语替换，让缩写、谐音读得对。
- **缓存**：说过的话会被缓存，再说时立即播放。
- **主题**：15 套配色，紧凑和展开两种窗口模式。

## 安装

1. 先安装 VB-CABLE 驱动：<https://vb-audio.com/Cable/>，装完重启电脑。安装包不附带这个驱动。
2. 运行 `CHATUUTTS-Setup-1.0.13.exe`。默认装到 `%LOCALAPPDATA%\CHATUUTTS`，不需要管理员权限。
3. 升级时直接覆盖安装，原有的配置和声音档案都会保留。

## 使用

**说话**：在输入框里打字，按回车或点播放按钮。连续发几句会按顺序依次播放。

**切换音色**：在侧栏选一个声音档案。要新建或修改档案，打开「编辑配置」，选音色、风格、语速等，点「试听」，满意后「保存」。

**离线说话**：在「编辑配置」里选带「本地」的音色并保存。本地音色只有语速和音量可调，第一次使用时会先加载约 1.5 秒。

**快捷发言**：在「快捷发言」里设置快捷键和对应的句子，然后开启快捷键。新安装的默认快捷键是 Ctrl+Alt+1/2/3。

**虚拟麦克风**：在音频设置里打开虚拟麦克风，然后在游戏或语音软件里把麦克风选成 `chatuu-tts`。扬声器可以选「只输出」，这样本机不出声，只有对方能听到。

## 配置文件

都在安装目录的 `config` 文件夹里，可以直接用文本编辑器改：

| 文件 | 作用 |
| --- | --- |
| sound_model.json | 接口地址、当前音色参数、缓存位置 |
| voice_profiles.json | 声音档案 |
| shortcut_key.json | 快捷发言 |
| fixed_collocation.json | 整句替换，如 `?` → `啊？` |
| word_replacement.json | 词语替换，如 `cod` → `C O D`，支持正则 |
| ui_state.json | 主题、窗口位置、扬声器和虚拟麦克风设置 |

## 更新说明

每个版本的详细改动在 `docs\changelog` 文件夹里：

- [1.0.13](docs/changelog/1.0.13.md)：本地离线语音
- [1.0.12](docs/changelog/1.0.12.md)：按顺序播放、连接复用、缓存更安全、默认快捷键调整

## 语音来源

CHATUUTTS 本身不提供语音合成服务，两种语音分别来自：

| 类型 | 来源 | 说明 |
| --- | --- | --- |
| 在线音色 | [xivCDN TTS PRO](https://ttspro.xivcdn.com/) | 最终幻想14 FoxTTS 插件使用的肥肥咖啡（FFCafe）TTS Pro 引擎。CHATUUTTS 只调用它的接口，与服务方没有隶属关系，接口的可用性和使用条款以服务方为准。 |
| 本地音色 | [Kokoro-82M v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)（hexgrad，Apache-2.0） | 通过 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（k2-fsa，Apache-2.0）在本机运行，不联网。 |

## 致谢与许可

- 本项目基于 Konn-yaku 的 [TTSApp v1.0.1](https://github.com/Konn-yaku/TTSApp/tree/v1.0.1) 修改而来，感谢原作者。TTSApp 未附带许可证，来自它的部分归原作者所有。
- SatouYumei 编写的部分采用 MIT 许可，范围见 [LICENSE](LICENSE)。
- 虚拟麦克风驱动 VB-CABLE 来自 [vb-audio.com](https://vb-audio.com/Cable/)，是捐赠软件，需要自行安装，本项目不附带。
- 全部第三方组件和服务见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 从源码运行和打包

源码仓库里**不包含**在线接口密钥和本地模型，需要自己准备：

1. 安装 Python 3.12，然后 `pip install -r requirements.txt`。
2. 把 `build/package-config` 里的文件复制到 `config/`，再把 `sound_model.example.json` 改名为 `sound_model.json`，并填上 `API_KEY`。没有密钥时只能用本地音色。
3. 下载本地模型 [kokoro-int8-multi-lang-v1_1.tar.bz2](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_1.tar.bz2)，解压到 `models/kokoro-int8-multi-lang-v1_1/`。
4. 运行 `python app.py`，或双击 `CHATUUTTS.vbs`。
5. 打包：在 `build/package-config/` 里也放一份填好密钥的 `sound_model.json`，执行 `python -m PyInstaller --noconfirm chatuutts.spec`，再用 Inno Setup 6 编译 `installer/chatuutts.iss`。
