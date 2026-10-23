"""生成 DSH 插件的 Release 资产。

运行方式：

    uv run --locked python scripts/build_dsh_release.py --uv <uv 可执行文件>

产物写入 ``dist/dsh-release``：

- ``ida-re-mcp-dsh-<版本>.tgz``：只含配置的可移植 DSH bundle；
- ``ida_re_mcp-<版本>-py3-none-any.whl``：当前仓库构建出的 Python wheel；
- ``SHA256SUMS``：上面两个文件的 SHA-256。

bundle 内的 ``cordis.patch.yml`` 在 staging 目录中重新生成，使用固定版本的
wheel 地址和校验值启动服务，不写入本机路径，也不依赖 Git 仓库的工作副本。
仓库中已经安装的 ``dsh-plugin/cordis.patch.yml`` 保持不变。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "dsh-plugin"
OUTPUT_ROOT = REPOSITORY_ROOT / "dist" / "dsh-release"

BUNDLE_NAME = "@local/ida-re-mcp"
BUNDLE_VERSION = "1.1.0"
RELEASE_TAG = "dsh-v1.1.0"
RELEASE_REPOSITORY = "https://github.com/UranusNo7/ida-re-mcp"
TGZ_NAME = f"ida-re-mcp-dsh-{BUNDLE_VERSION}.tgz"
SUMS_NAME = "SHA256SUMS"

REQUIRED_MANIFEST_FILES = (
    "cordis.patch.yml",
    "locale/*.json",
    "icon.svg",
    "README.md",
    "LICENSE",
)

# 源文件都在仓库内；staging 中的 cordis.patch.yml 和 README.md 由本脚本生成。
PACKAGE_SOURCES = {
    "package.json": PLUGIN_ROOT / "package.json",
    "icon.svg": PLUGIN_ROOT / "icon.svg",
    "locale/en.json": PLUGIN_ROOT / "locale" / "en.json",
    "locale/zh.json": PLUGIN_ROOT / "locale" / "zh.json",
    "LICENSE": REPOSITORY_ROOT / "LICENSE",
}

SERVER_NAME = "ida_re"
TOOL_CALL_TIMEOUT_MS = 3_900_000
SERVE_COMMAND = (
    "tool",
    "run",
    "--python",
    "3.13",
    "--from",
    "{wheel_url}",
    "ida-re-mcp",
    "serve",
)

README_TEMPLATE = """\
# ida-re-mcp DSH 插件

这个包把 [ida-re-mcp]({repository}) 注册为 DeepSeek Harness 的 `ida_re` MCP 服务，
工具以 `mcp__ida_re__<tool>` 的形式提供给 Agent。

安装前请确认已经安装 uv 和 IDA Pro 9.2+。服务启动时由 uv 从固定版本的 wheel
地址安装并运行，不需要先把本仓库放到固定目录。

需要检查本机 IDA 环境时，可以在任意目录运行：

```powershell
uv tool run --python 3.13 --from "{wheel_url}" ida-re-mcp doctor
```

启动命令、固定版本地址和校验值见同目录的 `cordis.patch.yml`。

## 校验下载的文件

同一次 Release 的 `SHA256SUMS` 列出 bundle 和 wheel 的 SHA-256，下载后请手动
比对。启动命令里的 `#sha256` 片段只用来固定 wheel 地址，当前 uv 不会校验它，
因此不能当作运行时的完整性检查。
"""


@dataclass(frozen=True, slots=True)
class ReleaseArtifacts:
    """一次构建产生的 Release 资产。"""

    wheel: Path
    tgz: Path
    sums: Path
    wheel_address: str


def sha256_file(path: Path) -> str:
    """返回文件的 SHA-256 十六进制值。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_url(wheel_name: str, digest: str) -> str:
    """返回同一次 Release 中的固定 wheel 地址，附带校验值。"""

    return f"{RELEASE_REPOSITORY}/releases/download/{RELEASE_TAG}/{wheel_name}#sha256={digest}"


def read_manifest() -> dict[str, object]:
    """读取本机已安装 bundle 的清单。"""

    with (PLUGIN_ROOT / "package.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise ValueError("dsh-plugin/package.json 的顶层必须是对象")
    return manifest


def check_manifest(manifest: dict[str, object]) -> None:
    """确认清单与本次 Release 的名称、版本和显示信息一致。"""

    if manifest.get("name") != BUNDLE_NAME:
        raise ValueError(f"清单名称应为 {BUNDLE_NAME}")
    if manifest.get("version") != BUNDLE_VERSION:
        raise ValueError(f"清单版本应为 {BUNDLE_VERSION}，请先修改 dsh-plugin/package.json")
    if manifest.get("license") != "MIT":
        raise ValueError("清单必须声明 license: MIT")
    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("清单必须说明插件用途")
    if "scripts" in manifest:
        raise ValueError("清单不得包含安装脚本")
    declared = manifest.get("files")
    if not isinstance(declared, list):
        raise ValueError("清单必须用 files 列出打包内容")
    missing = [name for name in REQUIRED_MANIFEST_FILES if name not in declared]
    if missing:
        raise ValueError(f"清单的 files 缺少 {missing[0]}")


def validate_wheel(wheel: Path) -> None:
    """检查 wheel 只包含包源码、元数据和许可证。"""

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    unexpected = [
        name for name in names if not (name.startswith("ida_re_mcp/") or ".dist-info/" in name)
    ]
    if unexpected:
        raise ValueError(f"wheel 包含不该发布的文件：{unexpected[0]}")
    for suffix in ("METADATA", "entry_points.txt", "licenses/LICENSE"):
        if not any(name.endswith(suffix) for name in names):
            raise ValueError(f"wheel 缺少 {suffix}；请检查 pyproject.toml 的打包配置")


def build_wheel(uv: str, work_root: Path) -> Path:
    """用 uv 构建当前仓库的 wheel。"""

    wheel_root = work_root / "wheel"
    wheel_root.mkdir(parents=True)
    _run([uv, "build", "--wheel", "--no-sources", "--out-dir", str(wheel_root)])
    wheels = sorted(wheel_root.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("uv build 必须且只能产出一个 wheel")
    return wheels[0]


def portable_patch(bundle_wheel_url: str) -> str:
    """生成可移植的 bundle patch；内容用 JSON 表示，属于合法的 YAML 子集。"""

    patch = [
        {
            "insert": [
                {
                    "id": "ida-re-mcp",
                    "name": "@deepseek-ai/dsh-mcp-client",
                    "config": {
                        "serverName": SERVER_NAME,
                        "transport": "stdio",
                        "command": "uv",
                        "args": [item.format(wheel_url=bundle_wheel_url) for item in SERVE_COMMAND],
                        "toolCallTimeoutMs": TOOL_CALL_TIMEOUT_MS,
                        "failOnStartupError": True,
                    },
                }
            ]
        }
    ]
    return json.dumps(patch, ensure_ascii=False, indent=2) + "\n"


def stage_package(staging_root: Path, bundle_wheel_url: str) -> Path:
    """在隔离目录中生成待打包的 package 目录。"""

    package_dir = staging_root / "package"
    for relative, source in PACKAGE_SOURCES.items():
        target = package_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (package_dir / "cordis.patch.yml").write_text(
        portable_patch(bundle_wheel_url), encoding="utf-8", newline="\n"
    )
    readme_text = README_TEMPLATE.format(repository=RELEASE_REPOSITORY, wheel_url=bundle_wheel_url)
    (package_dir / "README.md").write_text(readme_text, encoding="utf-8", newline="\n")
    return package_dir


def pack_tgz(package_dir: Path, tgz: Path) -> None:
    """把 staging 目录打成 npm 风格的 tgz，成员路径以 package/ 开头。"""

    members = sorted(path for path in package_dir.rglob("*") if path.is_file())
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in members:
            relative = path.relative_to(package_dir).as_posix()
            info = archive.gettarinfo(str(path), arcname=f"package/{relative}")
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(path.read_bytes()))
    tgz.parent.mkdir(parents=True, exist_ok=True)
    with (
        tgz.open("wb") as stream,
        gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressor,
    ):
        compressor.write(archive_buffer.getvalue())


def write_sums(output_root: Path, files: Sequence[Path]) -> Path:
    """写入 SHA256SUMS，按文件名排序列出每个文件的校验值。"""

    lines = [
        f"{sha256_file(path)}  {path.name}" for path in sorted(files, key=lambda item: item.name)
    ]
    target = output_root / SUMS_NAME
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return target


def build(uv: str, output_root: Path = OUTPUT_ROOT) -> ReleaseArtifacts:
    """构建 wheel 和 bundle tgz，并在输出目录写入校验值。"""

    manifest = read_manifest()
    check_manifest(manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ida-re-mcp-dsh-release-") as temporary:
        work_root = Path(temporary)
        wheel = build_wheel(uv, work_root)
        validate_wheel(wheel)
        address = wheel_url(wheel.name, sha256_file(wheel))
        package_dir = stage_package(work_root / "staging", address)
        tgz = output_root / TGZ_NAME
        pack_tgz(package_dir, tgz)
        published_wheel = output_root / wheel.name
        shutil.copy2(wheel, published_wheel)
        sums = write_sums(output_root, [tgz, published_wheel])
    return ReleaseArtifacts(wheel=published_wheel, tgz=tgz, sums=sums, wheel_address=address)


def _run(arguments: list[str]) -> None:
    """执行外部命令；失败时说明命令和退出码。"""

    completed = subprocess.run(arguments, cwd=REPOSITORY_ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"命令执行失败，退出码 {completed.returncode}：{' '.join(arguments)}。"
            "请先确认 uv 可以正常运行。"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_dsh_release.py",
        description="生成 DSH 插件的 Release 资产：bundle tgz、Python wheel 和 SHA256SUMS",
    )
    parser.add_argument(
        "--uv",
        default="uv",
        help="uv 命令或可执行文件路径；默认使用 PATH 中的 uv",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(list(arguments) if arguments is not None else None)
    artifacts = build(str(namespace.uv))
    print("已生成 DSH Release 资产：")
    print(f"- bundle：{artifacts.tgz}")
    print(f"- wheel：{artifacts.wheel}")
    print(f"- 校验值：{artifacts.sums}")
    print(f"- wheel 固定地址：{artifacts.wheel_address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
