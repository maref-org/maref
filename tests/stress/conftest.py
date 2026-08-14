"""pytest conftest: ensure missing maref.stress.* modules are stubbed before imports."""

from __future__ import annotations

from tests._stress_stubs import install_stubs

install_stubs()
