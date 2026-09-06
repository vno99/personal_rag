import admin.app as admin_app


def test_start_steps():
    assert "get_docs" in admin_app.START_STEPS.values()


def test_terminal_states():
    assert {"done", "failed", "cancelled"} == admin_app.TERMINAL
