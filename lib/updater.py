"""通过 GitHub Release 检查更新、下载安装包并静默安装。

不走 api.github.com：未登录的接口每个 IP 每小时只有 60 次，代理和共享网络很容易用完。
这里只用网页跳转、Release 附件和仓库原始文件，这几种地址没有这个限制。
每个 Release 需要带上安装包和同名的 .sha256 文件，更新说明取 docs/changelog/<版本>.md。
"""

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from lib.version import REPO, VERSION

RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
_DOWNLOAD = f"https://github.com/{REPO}/releases/download"
_RAW = f"https://raw.githubusercontent.com/{REPO}"
_TAG = re.compile(r"/releases/tag/v?([\d.]+)/?$")
_HEADERS = {"User-Agent": f"CHATUUTTS/{VERSION}"}


class UpdateError(Exception):
    pass


class UpdateCancelled(Exception):
    pass


def parse_version(text):
    return tuple(int(part) for part in re.findall(r"\d+", str(text or ""))[:4])


def is_newer(latest, current=VERSION):
    return parse_version(latest) > parse_version(current)


def can_install():
    """只有安装版能自己装更新；从源码运行时只打开下载页。"""
    return bool(getattr(sys, "frozen", False))


def _get_text(url, timeout):
    """取一个小文本文件，拿不到就返回空字符串。"""
    import requests

    try:
        response = requests.get(url, headers=_HEADERS, timeout=timeout)
    except requests.RequestException:
        return ""
    if response.status_code != 200:
        return ""
    response.encoding = "utf-8"
    return response.text


def fetch_latest(timeout=10):
    """读取最新正式版。还没有任何 Release 时返回 None。"""
    import requests

    response = requests.get(RELEASES_PAGE, headers=_HEADERS, timeout=timeout, allow_redirects=False)
    if response.status_code == 404:
        return None
    match = _TAG.search(response.headers.get("Location") or "")
    if response.status_code not in (301, 302, 303, 307, 308) or not match:
        raise UpdateError(f"读不到最新版本（{response.status_code}）")
    version = match.group(1)
    tag = f"v{version}"
    name = f"CHATUUTTS-Setup-{version}.exe"
    url = f"{_DOWNLOAD}/{tag}/{name}"
    checksum = _get_text(url + ".sha256", timeout).split()
    sha256 = checksum[0].lower() if checksum and re.fullmatch(r"[0-9a-fA-F]{64}", checksum[0]) else ""
    return {
        "version": version,
        "notes": _get_text(f"{_RAW}/{tag}/docs/changelog/{version}.md", timeout),
        "page": f"https://github.com/{REPO}/releases/tag/{tag}",
        "name": name,
        "url": url,
        "sha256": sha256,
    }


def check_for_update(timeout=10):
    """有比当前更新的版本时返回它的信息，否则返回 None。网络问题会抛出异常。"""
    info = fetch_latest(timeout)
    if info and is_newer(info["version"]):
        return info
    return None


def _download_dir():
    return Path(tempfile.gettempdir()) / "chatuutts-update"


def _verify(path, info):
    """和 Release 里 .sha256 文件给的值对上才算数。"""
    path = Path(path)
    expected = info.get("sha256")
    if not expected or not path.is_file():
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def download(info, on_progress=None, cancel=None):
    """下载安装包到临时目录并校验，返回文件路径。已下载过且校验通过就直接用。"""
    import requests

    if not info.get("sha256"):
        raise UpdateError("这个版本没有校验文件，请到下载页手动更新")
    folder = _download_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info["name"]
    if _verify(target, info):
        if on_progress:
            on_progress(1, 1)
        return target
    part = target.with_name(target.name + ".part")
    finished = False
    try:
        with requests.get(info["url"], headers={"User-Agent": _HEADERS["User-Agent"]}, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(part, "wb") as file:
                for chunk in response.iter_content(1 << 16):
                    if cancel is not None and cancel.is_set():
                        raise UpdateCancelled()
                    if not chunk:
                        continue
                    file.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
        if not _verify(part, info):
            raise UpdateError("安装包校验没有通过，请重新下载")
        part.replace(target)
        finished = True
        return target
    finally:
        if not finished:
            try:
                part.unlink()
            except OSError:
                pass


def launch_installer(path):
    """静默运行安装包。安装包会关掉旧程序，装完再把程序打开。"""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        cwd=str(Path(path).parent),
        creationflags=flags,
        close_fds=True,
    )
