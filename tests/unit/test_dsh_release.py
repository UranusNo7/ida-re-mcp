"""发布脚本的打包清单、校验值和可移植启动配置测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Protocol, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "build_dsh_release.py"
PLUGIN_ROOT = REPOSITORY_ROOT / "dsh-plugin"

DIGEST = "0123456789abcdef" * 4
WHEEL_NAME = "ida_re_mcp-1.0.0.dev0-py3-none-any.whl"
STAGED_FILES = {
    "package/package.json",
    "package/cordis.patch.yml",
    "package/README.md",
    "package/LICENSE",
    "package/icon.svg",
    "package/locale/en.json",
    "package/locale/zh.json",
}
MACHINE_PATH_PATTERN = re.compile(r"[A-Za-z]:\\|python_code|AppData|\.venv", re.IGNORECASE)


class _Builder(Protocol):
    """发布脚本对测试暴露的常量与函数。"""

    OUTPUT_ROOT: Path
    BUNDLE_NAME: str
    BUNDLE_VERSION: str
    RELEASE_TAG: str
    RELEASE_REPOSITORY: str
    TGZ_NAME: str
    SUMS_NAME: str
    SERVER_NAME: str
    TOOL_CALL_TIMEOUT_MS: int
    SERVE_COMMAND: tuple[str, ...]

    def sha256_file(self, path: Path) -> str: ...

    def wheel_url(self, wheel_name: str, digest: str) -> str: ...

    def portable_patch(self, bundle_wheel_url: str) -> str: ...

    def stage_package(self, staging_root: Path, bundle_wheel_url: str) -> Path: ...

    def pack_tgz(self, package_dir: Path, tgz: Path) -> None: ...

    def write_sums(self, output_root: Path, files: list[Path]) -> Path: ...

    def validate_wheel(self, wheel: Path) -> None: ...


def _load_builder() -> _Builder:
    spec = importlib.util.spec_from_file_location("build_dsh_release", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(_Builder, module)


BUILDER = _load_builder()


def _wheel_url() -> str:
    return BUILDER.wheel_url(WHEEL_NAME, DIGEST)


def _staged(tmp_path: Path) -> Path:
    return BUILDER.stage_package(tmp_path / "staging", _wheel_url())


def _patch_config(tmp_path: Path) -> dict[str, object]:
    package_dir = _staged(tmp_path)
    patch = cast(
        list[dict[str, object]],
        json.loads((package_dir / "cordis.patch.yml").read_text(encoding="utf-8")),
    )
    insert = cast(list[dict[str, object]], patch[0]["insert"])
    return cast(dict[str, object], insert[0]["config"])


def _write_wheel(path: Path, extra: dict[str, bytes] | None = None) -> Path:
    members = {
        "ida_re_mcp/__init__.py": b"",
        "ida_re_mcp-1.0.0.dev0.dist-info/METADATA": b"Name: ida-re-mcp\n",
        "ida_re_mcp-1.0.0.dev0.dist-info/entry_points.txt": b"[console_scripts]\n",
        "ida_re_mcp-1.0.0.dev0.dist-info/licenses/LICENSE": b"MIT\n",
    }
    if extra:
        members.update(extra)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_manifest_matches_release() -> None:
    manifest = cast(
        dict[str, object],
        json.loads((PLUGIN_ROOT / "package.json").read_text(encoding="utf-8")),
    )
    assert manifest["name"] == BUILDER.BUNDLE_NAME == "@local/ida-re-mcp"
    assert manifest["version"] == BUILDER.BUNDLE_VERSION
    assert manifest["license"] == "MIT"
    description = cast(str, manifest["description"])
    assert "ida_re" in description
    assert "scripts" not in manifest
    files = cast(list[str], manifest["files"])
    assert {"cordis.patch.yml", "locale/*.json", "icon.svg", "README.md", "LICENSE"} <= set(files)
    exports = cast(dict[str, object], manifest["exports"])
    assert exports["./icon"] == "./icon.svg"
    assert exports["./locale/*.json"] == "./locale/*.json"
    bundle = cast(dict[str, object], cast(dict[str, object], manifest["dsh"])["bundle"])
    assert bundle["patch"] == "./cordis.patch.yml"


def test_source_patch_keeps_local_installation() -> None:
    source_patch = (PLUGIN_ROOT / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "cwd:" in source_patch
    assert ".venv" in source_patch


def test_release_constants_pin_tag_and_outputs() -> None:
    assert BUILDER.RELEASE_TAG == "dsh-v1.1.0"
    assert BUILDER.RELEASE_REPOSITORY == "https://github.com/UranusNo7/ida-re-mcp"
    assert BUILDER.TGZ_NAME == "ida-re-mcp-dsh-1.1.0.tgz"
    assert BUILDER.SUMS_NAME == "SHA256SUMS"
    assert BUILDER.OUTPUT_ROOT == REPOSITORY_ROOT / "dist" / "dsh-release"


def test_wheel_url_is_pinned() -> None:
    address = _wheel_url()
    assert address == (
        "https://github.com/UranusNo7/ida-re-mcp/releases/download/dsh-v1.1.0/"
        f"{WHEEL_NAME}#sha256={DIGEST}"
    )
    assert re.fullmatch(r".*#sha256=[0-9a-f]{64}", address)


def test_staging_layout(tmp_path: Path) -> None:
    package_dir = _staged(tmp_path)
    names = {
        path.relative_to(tmp_path / "staging").as_posix()
        for path in package_dir.rglob("*")
        if path.is_file()
    }
    assert names == STAGED_FILES


def test_staging_leaves_repository_files_untouched(tmp_path: Path) -> None:
    before = {
        path: path.read_bytes()
        for path in (
            PLUGIN_ROOT / "cordis.patch.yml",
            PLUGIN_ROOT / "package.json",
            PLUGIN_ROOT / "icon.svg",
            PLUGIN_ROOT / "locale" / "en.json",
            PLUGIN_ROOT / "locale" / "zh.json",
        )
    }
    _staged(tmp_path)
    after = {path: path.read_bytes() for path in before}
    assert after == before


def test_portable_patch_starts_service_through_uv(tmp_path: Path) -> None:
    config = _patch_config(tmp_path)
    assert config["serverName"] == "ida_re"
    assert config["transport"] == "stdio"
    assert config["command"] == "uv"
    assert config["args"] == [
        "tool",
        "run",
        "--python",
        "3.13",
        "--from",
        _wheel_url(),
        "ida-re-mcp",
        "serve",
    ]
    assert config["toolCallTimeoutMs"] == 3_900_000
    assert config["failOnStartupError"] is True
    assert "cwd" not in config
    assert "env" not in config


def test_portable_patch_has_no_private_paths(tmp_path: Path) -> None:
    package_dir = _staged(tmp_path)
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".yml", ".md", ".svg"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert MACHINE_PATH_PATTERN.search(text) is None, path.name
        assert "refs/heads" not in text
    patch_text = (package_dir / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "/main/" not in patch_text
    assert "config.toml" not in patch_text


def test_package_display_metadata_and_icon(tmp_path: Path) -> None:
    package_dir = _staged(tmp_path)
    for locale in ("en.json", "zh.json"):
        data = cast(
            dict[str, object],
            json.loads((package_dir / "locale" / locale).read_text(encoding="utf-8")),
        )
        meta = cast(dict[str, object], data["meta"])
        assert cast(str, meta["title"]).strip()
        assert cast(str, meta["description"]).strip()
    icon = (package_dir / "icon.svg").read_text(encoding="utf-8")
    assert icon.lstrip().startswith("<svg")
    assert "</svg>" in icon
    assert len(icon.encode("utf-8")) <= 256 * 1024
    assert "MIT License" in (package_dir / "LICENSE").read_text(encoding="utf-8")


def test_package_readme_stays_short(tmp_path: Path) -> None:
    readme = (_staged(tmp_path) / "README.md").read_text(encoding="utf-8")
    assert "ida-re-mcp" in readme
    assert "uv tool run" in readme
    assert len(readme.splitlines()) <= 40


def test_package_readme_explains_manual_checksum(tmp_path: Path) -> None:
    readme = (_staged(tmp_path) / "README.md").read_text(encoding="utf-8")
    assert "SHA256SUMS" in readme
    assert "手动" in readme
    assert "#sha256" in readme
    assert "uv 不会校验" in readme


def test_tgz_members_and_reproducible_output(tmp_path: Path) -> None:
    package_dir = _staged(tmp_path)
    first = tmp_path / "first.tgz"
    second = tmp_path / "second.tgz"
    BUILDER.pack_tgz(package_dir, first)
    BUILDER.pack_tgz(package_dir, second)
    assert BUILDER.sha256_file(first) == BUILDER.sha256_file(second)
    with tarfile.open(first) as archive:
        names = set(archive.getnames())
    assert names == STAGED_FILES
    assert all(name.startswith("package/") for name in names)
    assert not any(part in name for name in names for part in ("data/", "logs/", "tests/"))


def test_sha256sums_lists_each_artifact(tmp_path: Path) -> None:
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    sums = BUILDER.write_sums(tmp_path, [second, first])
    assert sums.name == "SHA256SUMS"
    assert sums.read_text(encoding="utf-8").splitlines() == [
        f"{hashlib.sha256(b'a').hexdigest()}  a.bin",
        f"{hashlib.sha256(b'b').hexdigest()}  b.bin",
    ]


def test_validate_wheel_accepts_source_and_license_only(tmp_path: Path) -> None:
    BUILDER.validate_wheel(_write_wheel(tmp_path / WHEEL_NAME))


def test_validate_wheel_rejects_project_directories(tmp_path: Path) -> None:
    wheel = _write_wheel(tmp_path / WHEEL_NAME, {"data/sample.bin": b"x"})
    try:
        BUILDER.validate_wheel(wheel)
    except ValueError as error:
        assert "不该发布" in str(error)
    else:
        raise AssertionError("wheel 中的 data/ 必须被拒绝")


def test_validate_wheel_requires_license(tmp_path: Path) -> None:
    wheel = tmp_path / WHEEL_NAME
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("ida_re_mcp/__init__.py", b"")
        archive.writestr("ida_re_mcp-1.0.0.dev0.dist-info/METADATA", b"Name: ida-re-mcp\n")
        archive.writestr("ida_re_mcp-1.0.0.dev0.dist-info/entry_points.txt", b"")
    try:
        BUILDER.validate_wheel(wheel)
    except ValueError as error:
        assert "licenses/LICENSE" in str(error)
    else:
        raise AssertionError("缺少许可证的 wheel 必须被拒绝")
