"""Tests for copilot_echo.errors."""

from copilot_echo.errors import AgentCrashedError, DeviceDisconnectedError


class TestAgentCrashedError:
    def test_is_exception(self):
        assert issubclass(AgentCrashedError, Exception)

    def test_message(self):
        exc = AgentCrashedError("pipe broken")
        assert str(exc) == "pipe broken"

    def test_raise_and_catch(self):
        try:
            raise AgentCrashedError("crash")
        except AgentCrashedError as e:
            assert str(e) == "crash"


class TestDeviceDisconnectedError:
    def test_is_exception(self):
        assert issubclass(DeviceDisconnectedError, Exception)

    def test_message(self):
        exc = DeviceDisconnectedError("device unavailable")
        assert str(exc) == "device unavailable"

    def test_raise_and_catch(self):
        try:
            raise DeviceDisconnectedError("gone")
        except DeviceDisconnectedError as e:
            assert str(e) == "gone"
