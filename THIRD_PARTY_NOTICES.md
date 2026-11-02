# 第三方组件与服务声明

CHATUUTTS 使用了下列第三方服务、模型和软件。它们的版权归各自作者所有，遵循各自的许可或服务条款。本项目与下列任何服务提供方都没有隶属或合作关系。

## 在线语音合成

| 名称 | 说明 |
| --- | --- |
| [xivCDN TTS PRO](https://ttspro.xivcdn.com/) | 在线音色的合成服务，即最终幻想14 FoxTTS 插件使用的肥肥咖啡（FFCafe）TTS Pro 引擎。CHATUUTTS 只是调用这个接口，不提供、不托管该服务；接口的可用性、额度和使用条款以服务方为准。 |

## 本地语音合成

| 名称 | 作者 | 许可 | 用途 |
| --- | --- | --- | --- |
| [Kokoro-82M v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) | hexgrad | Apache-2.0 | 本地离线语音模型 |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | k2-fsa | Apache-2.0 | 运行本地模型；模型的 int8 打包版本也来自其 tts-models 发布页 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Microsoft | MIT | sherpa-onnx 的推理引擎 |
| [eSpeak NG](https://github.com/espeak-ng/espeak-ng) 数据文件 | eSpeak NG 贡献者 | GPL-3.0-or-later | 模型目录中的 espeak-ng-data，用于英文发音 |
| [cppjieba](https://github.com/yanyiwu/cppjieba) 词典 | yanyiwu | MIT | 模型目录中的 dict，用于中文分词 |

## 虚拟麦克风

| 名称 | 说明 |
| --- | --- |
| [VB-CABLE](https://vb-audio.com/Cable/) | VB-Audio Software 的虚拟声卡驱动，捐赠软件。CHATUUTTS 不附带、不代为安装这个驱动，需要用户自行从官网下载安装。 |

## Python 依赖（打包在安装包内）

| 名称 | 许可 |
| --- | --- |
| Python | PSF License |
| [pygame](https://www.pygame.org/) | LGPL-2.1 |
| [pynput](https://github.com/moses-palmer/pynput) | LGPL-3.0 |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) / PortAudio | MIT |
| [pyminiaudio](https://github.com/irmen/pyminiaudio) | MIT |
| [Pillow](https://python-pillow.org/) | MIT-CMU |
| [requests](https://github.com/psf/requests) | Apache-2.0 |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | MPL-2.0 |
| [PyInstaller](https://pyinstaller.org/) 引导程序 | GPL-2.0，附带允许分发打包程序的例外条款 |

## 参考项目

| 名称 | 作者 | 说明 |
| --- | --- | --- |
| [TTSApp v1.0.1](https://github.com/Konn-yaku/TTSApp/tree/v1.0.1) | Konn-yaku | CHATUUTTS 在它的基础上修改而来，保留了原有的程序结构、文本替换和快捷键逻辑以及配置文件格式。TTSApp 未附带许可证，相关部分归原作者所有，详见 LICENSE 中的「许可范围」。 |
