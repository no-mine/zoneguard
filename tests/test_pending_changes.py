from zoneguard.gui.pending_changes import PendingChanges


def test_starts_empty():
    pending = PendingChanges(on_change=lambda: None)
    assert len(pending) == 0


def test_add_appends_and_fires_on_change():
    calls = []
    pending = PendingChanges(on_change=lambda: calls.append(len(pending)))
    pending.add(["--zone", "home", "--add-service", "ssh"])
    assert len(pending) == 1
    assert calls == [1]


def test_add_accepts_multiple_commands_in_one_call():
    pending = PendingChanges(on_change=lambda: None)
    pending.add(["cmd1"], ["cmd2"])
    assert len(pending) == 2


def test_take_returns_and_clears_the_queue():
    calls = []
    pending = PendingChanges(on_change=lambda: calls.append(len(pending)))
    pending.add(["cmd1"])
    pending.add(["cmd2"])

    commands = pending.take()

    assert commands == [["cmd1"], ["cmd2"]]
    assert len(pending) == 0
    assert calls == [1, 2, 0]  # fires on_change for each add() and the take()


def test_take_on_empty_queue_returns_empty_list():
    pending = PendingChanges(on_change=lambda: None)
    assert pending.take() == []
