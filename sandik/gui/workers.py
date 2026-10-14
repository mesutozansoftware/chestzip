"""Uzun işlemleri arayüzü dondurmadan arka planda çalıştırma."""

from __future__ import annotations

import time
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from ..safety import CancelToken


class Task(QThread):
    """``fn(progress, cancel, ask)`` fonksiyonunu ayrı iş parçacığında çalıştırır."""

    progressed = Signal(object, object, str)
    succeeded = Signal(object)
    failed = Signal(object)
    ask_requested = Signal(str)

    def __init__(self, fn: Callable, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.fn = fn
        self.cancel = CancelToken()
        self.answer = "no"
        self._last = 0.0

    def _progress(self, done: int, total: int, name: str) -> None:
        now = time.monotonic()
        if now - self._last >= 0.05 or (total and done >= total):
            self._last = now
            self.progressed.emit(done, total, name)

    def _ask(self, path: str) -> str:
        # Ana iş parçacığındaki diyalog kapanana kadar burada beklenir.
        self.ask_requested.emit(path)
        return self.answer

    def run(self) -> None:
        try:
            result = self.fn(self._progress, self.cancel, self._ask)
        except BaseException as e:  # noqa: BLE001 — her hata arayüze iletilir
            e.__sandik_tb__ = traceback.format_exc()
            self.failed.emit(e)
        else:
            self.succeeded.emit(result)


def connect_ask(task: Task, handler: Callable[[str], str]) -> None:
    """Üzerine yazma sorusunu ana iş parçacığında sorup cevabı işçiye döndürür."""

    class _Bridge(QObject):
        @Slot(str)
        def on_ask(self, path: str) -> None:
            task.answer = handler(path)

    bridge = _Bridge()  # ana iş parçacığında oluşturulur, slot orada çalışır
    task._bridge = bridge  # referansı canlı tut
    task.ask_requested.connect(bridge.on_ask, Qt.ConnectionType.BlockingQueuedConnection)
