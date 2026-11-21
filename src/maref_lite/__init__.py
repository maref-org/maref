"""MAREF Lite — zero-config governance overlay.

版本号不再手写：以 `maref.__version__` 为唯一事实源，缺失时回退到已安装分发元数据。
（回归：曾经硬编码 0.55.0，而包/README/STATE 是 0.55.2，用户 `maref --version` 看到的就是那个错值；
 而 editable 安装的元数据可能比源码旧，所以不能把 importlib.metadata 当首选。）
"""

try:  # 唯一事实源：源码树内的单一常量（tests/packaging 会拿它对齐 pyproject 与 README）
    from maref import __version__
except Exception:  # pragma: no cover - 仅在 maref 不可导入时触发
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _dist_version

    try:
        __version__ = _dist_version("maref")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
