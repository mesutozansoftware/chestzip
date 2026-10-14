import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from chestzip.api import Archive, create_archive  # noqa: E402
from chestzip.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wait(app, cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def _window(app):
    from chestzip.gui.main_window import MainWindow
    s = Settings()
    s.save = lambda: None  # testler kullanıcı ayarlarını değiştirmesin
    return MainWindow(s, lambda: None)


def test_open_archive_async(app, tmp_path):
    src = tmp_path / "d"
    (src / "alt").mkdir(parents=True)
    (src / "alt" / "x.txt").write_text("x")
    arc = tmp_path / "a.tar.gz"
    create_archive(arc, [src])
    w = _window(app)
    w.open_archive(arc)
    assert _wait(app, lambda: w.archive is not None)
    assert [r.name for r in w.model.rows] == ["d"]
    w.navigate_inner("d/alt")
    assert [r.name for r in w.model.rows] == ["x.txt"]
    w.go_up()
    w.go_up()
    w.go_up()
    assert w.archive is None and w.fs_dir == tmp_path.resolve()
    w.close()


def test_task_overwrite_question_bridge(app, tmp_path):
    from chestzip.gui.workers import Task, connect_ask
    f = tmp_path / "a.txt"
    f.write_text("yeni")
    arc = tmp_path / "a.zip"
    create_archive(arc, [f])
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "a.txt").write_text("eski")
    asked = []
    results = []

    def work(progress, cancel, ask):
        return Archive(arc).extract(dst, overwrite="ask", ask_overwrite=ask,
                                    progress=progress, cancel=cancel)

    task = Task(work)
    connect_ask(task, lambda p: asked.append(p) or "yes")
    task.succeeded.connect(results.append)
    task.failed.connect(results.append)
    task.start()
    assert _wait(app, lambda: results)
    task.wait()
    assert asked and (dst / "a.txt").read_text() == "yeni"


def test_encrypted_7z_header_listing_needs_password(app, tmp_path):
    f = tmp_path / "gizli.txt"
    f.write_text("s")
    arc = tmp_path / "g.7z"
    create_archive(arc, [f], password="pw")
    from chestzip.gui import dialogs
    w = _window(app)
    orig = dialogs.ask_password
    dialogs.ask_password = lambda parent, name: "pw"
    try:
        w.open_archive(arc)
        assert _wait(app, lambda: w.archive is not None)
        assert [r.name for r in w.model.rows] == ["gizli.txt"]
    finally:
        dialogs.ask_password = orig
        w.close()
