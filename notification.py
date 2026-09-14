from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys

LOGGER = logging.getLogger(__name__)

APP_NAME = "OpenCost"


def notify(title: str, message: str, *, sound: bool = True) -> bool:
    shown = _show_windows_notification(title, message) if sys.platform == "win32" else False
    if sound:
        _play_sound()
    return shown


def notify_completion(summary: str) -> bool:
    return notify(f"{APP_NAME} - session terminee", summary)


def _show_windows_notification(title: str, message: str) -> bool:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        return False

    script = r"""
$ErrorActionPreference = "Stop"
$title = [Environment]::GetEnvironmentVariable("OPENCOST_NOTIFICATION_TITLE", "Process")
$message = [Environment]::GetEnvironmentVariable("OPENCOST_NOTIFICATION_MESSAGE", "Process")
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $template.GetElementsByTagName("text")
    $texts.Item(0).AppendChild($template.CreateTextNode($title)) | Out-Null
    $texts.Item(1).AppendChild($template.CreateTextNode($message)) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    $toast.Tag = "OpenCost"
    $toast.Group = "OpenCost"
    $toast.ExpirationTime = [DateTimeOffset]::Now.AddMinutes(1)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier().Show($toast)
    exit 0
} catch {
    exit 1
}
""".strip()
    env = os.environ.copy()
    env["OPENCOST_NOTIFICATION_TITLE"] = title[:200]
    env["OPENCOST_NOTIFICATION_MESSAGE"] = message[:1000]
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.warning("Notification Windows indisponible: %s", result.stderr.strip())
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        LOGGER.warning("Impossible d'afficher la notification Windows", exc_info=True)
        return False


def _play_sound() -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONINFORMATION)
    except (ImportError, RuntimeError):
        LOGGER.warning("Impossible de jouer le son de notification", exc_info=True)
