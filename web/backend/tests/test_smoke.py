def test_pytest_installed():
    assert 1 + 1 == 2


def test_sessions_module_importable():
    import sessions
    assert hasattr(sessions, "session_stats")
