"""开发时读项目目录，打包后读安装目录和内置资源。"""

import sys
from pathlib import Path


def app_dir():
    """配置、缓存写在程序旁边，避免装到只读目录里。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_dir():
    """图标、吉祥物和字标。打包后在解压出来的资源目录里。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]
