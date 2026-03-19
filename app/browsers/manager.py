from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import UpstreamTrackingError


@dataclass
class BrowserRenderResult:
    html: str
    strategy: str


class BrowserManager:
    def __init__(self) -> None:
        self._wsl_lightpanda_available: bool | None = None
        self._chromium_executable: str | None = None

    async def render(self, url: str) -> BrowserRenderResult:
        settings = get_settings()
        lightpanda_error: Exception | None = None
        chromium_error: Exception | None = None

        if await self._has_lightpanda():
            try:
                html = await self._run_lightpanda(url)
                return BrowserRenderResult(html=html, strategy="lightpanda")
            except Exception as error:
                lightpanda_error = error

        if self._has_chromium_runner():
            try:
                html = await self._run_chromium(url)
                return BrowserRenderResult(html=html, strategy="chromium")
            except Exception as error:
                chromium_error = error

        if settings.allow_edge_fallback:
            try:
                html = await self._run_edge(url)
                return BrowserRenderResult(html=html, strategy="edge")
            except Exception as error:
                details = str(error)
                if chromium_error:
                    details = f"Chromium runner failed: {chromium_error}; Edge fallback failed: {details}"
                if lightpanda_error:
                    details = f"Lightpanda failed: {lightpanda_error}; {details}"
                raise UpstreamTrackingError(details) from error

        if chromium_error:
            details = f"Chromium runner failed: {chromium_error}"
            if lightpanda_error:
                details = f"Lightpanda failed: {lightpanda_error}; {details}"
            raise UpstreamTrackingError(details) from chromium_error

        if lightpanda_error:
            raise UpstreamTrackingError(f"Lightpanda failed and Edge fallback is disabled: {lightpanda_error}") from lightpanda_error

        raise UpstreamTrackingError("No supported browser runtime is available. Install a supported lightweight browser runner or enable Edge fallback.")

    async def _has_lightpanda(self) -> bool:
        settings = get_settings()
        if shutil.which(settings.lightpanda_command):
            return True
        if await self._has_wsl_lightpanda():
            return True
        return self._has_lightpanda_node_runner()

    def _has_lightpanda_node_runner(self) -> bool:
        settings = get_settings()
        package_json = os.path.join(
            os.path.dirname(settings.lightpanda_node_script),
            "node_modules",
            "@lightpanda",
            "browser",
            "package.json"
        )
        return os.path.exists(settings.lightpanda_node_script) and os.path.exists(package_json) and sys.platform != "win32"

    def _has_chromium_runner(self) -> bool:
        settings = get_settings()
        package_json = os.path.join(
            os.path.dirname(settings.browser_runner_script),
            "node_modules",
            "puppeteer-core",
            "package.json"
        )
        return os.path.exists(settings.browser_runner_script) and os.path.exists(package_json) and bool(self._find_chromium_executable())

    def _find_chromium_executable(self) -> str | None:
        if self._chromium_executable is not None:
            return self._chromium_executable

        settings = get_settings()
        candidates = [
            settings.browser_executable_path,
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                self._chromium_executable = candidate
                return candidate
        self._chromium_executable = None
        return None

    async def _has_wsl_lightpanda(self) -> bool:
        if sys.platform != "win32":
            return False

        if self._wsl_lightpanda_available is not None:
            return self._wsl_lightpanda_available

        settings = get_settings()
        def check() -> bool:
            result = subprocess.run(
                [
                    "wsl.exe",
                    "-d",
                    settings.lightpanda_wsl_distro,
                    "--",
                    "bash",
                    "-lc",
                    "command -v lightpanda >/dev/null 2>&1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0

        self._wsl_lightpanda_available = await asyncio.to_thread(check)
        return self._wsl_lightpanda_available

    async def _run_lightpanda(self, url: str) -> str:
        settings = get_settings()
        if shutil.which(settings.lightpanda_command):
            stdout, stderr, returncode = await asyncio.to_thread(
                self._run_process,
                [settings.lightpanda_command, "fetch", url],
            )
        elif await self._has_wsl_lightpanda():
            stdout, stderr, returncode = await asyncio.to_thread(
                self._run_process,
                [
                    "wsl.exe",
                    "-d",
                    settings.lightpanda_wsl_distro,
                    "--",
                    "bash",
                    "-lc",
                    f"lightpanda fetch {shlex.quote(url)}",
                ],
            )
        elif self._has_lightpanda_node_runner():
            stdout, stderr, returncode = await asyncio.to_thread(
                self._run_process,
                ["node", settings.lightpanda_node_script, url],
            )
        else:
            raise UpstreamTrackingError(
                "Lightpanda is not installed. On Windows, the official setup path is WSL2 + Ubuntu + a Lightpanda install inside WSL."
            )
        if returncode != 0:
            raise UpstreamTrackingError(stderr.strip() or "Lightpanda failed to render the page.")
        return stdout

    async def _run_chromium(self, url: str) -> str:
        settings = get_settings()
        executable = self._find_chromium_executable()
        if not executable:
            raise UpstreamTrackingError("No Chromium-based browser executable was found on this machine.")

        stdout, stderr, returncode = await asyncio.to_thread(
            self._run_process,
            ["node", settings.browser_runner_script, url, executable],
        )
        if returncode != 0:
            raise UpstreamTrackingError(stderr.strip() or "Chromium runner failed to render the page.")
        return stdout

    def _run_process(self, command: list[str]) -> tuple[str, str, int]:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        return result.stdout, result.stderr, result.returncode

    async def _run_edge(self, url: str) -> str:
        from selenium import webdriver
        from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.edge.service import Service
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        settings = get_settings()
        last_error: Exception | None = None

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        def fetch(driver_path: str) -> str:
            driver = webdriver.Edge(service=Service(driver_path), options=options)
            try:
                driver.set_page_load_timeout(int(settings.request_timeout_seconds) + 5)
                driver.get(url)
                return driver.page_source
            finally:
                driver.quit()

        driver_path = settings.edge_driver_path if os.path.exists(settings.edge_driver_path) else ""

        if driver_path:
            try:
                return await asyncio.to_thread(fetch, driver_path)
            except SessionNotCreatedException as error:
                last_error = error
            except WebDriverException as error:
                last_error = error

        try:
            auto_driver_path = await asyncio.to_thread(EdgeChromiumDriverManager().install)
            return await asyncio.to_thread(fetch, auto_driver_path)
        except Exception as error:
            details = str(error)
            if last_error:
                details = f"{last_error}; auto-download failed: {details}"
            raise UpstreamTrackingError(f"Edge fallback failed: {details}") from error
