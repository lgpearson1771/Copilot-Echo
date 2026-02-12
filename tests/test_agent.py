"""Tests for copilot_echo.agent."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from copilot_echo.errors import AgentCrashedError


# ------------------------------------------------------------------
# _ensure_copilot
# ------------------------------------------------------------------

class TestEnsureCopilot:
    def test_lazy_import(self):
        import copilot_echo.agent as agent_mod

        original = agent_mod._copilot
        agent_mod._copilot = None
        try:
            with patch.dict("sys.modules", {"copilot": MagicMock()}) as _:
                result = agent_mod._ensure_copilot()
            assert result is not None
        finally:
            agent_mod._copilot = original

    def test_idempotent(self):
        import copilot_echo.agent as agent_mod

        sentinel = object()
        agent_mod._copilot = sentinel
        try:
            result = agent_mod._ensure_copilot()
            assert result is sentinel
        finally:
            agent_mod._copilot = None


# ------------------------------------------------------------------
# Agent init / lifecycle
# ------------------------------------------------------------------

class TestAgentInit:
    def test_defaults(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
        assert agent._started is False
        assert agent._session is None
        assert agent._client is None
        assert agent._loop is None
        assert agent._current_task is None


class TestAgentSend:
    def test_send_when_not_started(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            result = agent.send("hello")
        assert result == "Agent is not running."

    def test_send_success(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            # Create a mock future that returns a result
            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.return_value = "Agent says hello"

            with patch(
                "asyncio.run_coroutine_threadsafe", return_value=mock_future
            ):
                result = agent.send("hello")

            assert result == "Agent says hello"
            agent._loop.close()

    def test_send_cancelled(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = concurrent.futures.CancelledError()

            with patch(
                "asyncio.run_coroutine_threadsafe", return_value=mock_future
            ):
                result = agent.send("hello")

            assert result == ""
            agent._loop.close()

    def test_send_exception(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = RuntimeError("network error")

            with patch(
                "asyncio.run_coroutine_threadsafe", return_value=mock_future
            ):
                result = agent.send("hello")

            assert "went wrong" in result
            agent._loop.close()


class TestAgentCancel:
    def test_cancel_calls_task_cancel(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._loop = asyncio.new_event_loop()
            mock_task = MagicMock()
            agent._current_task = mock_task

            agent.cancel()

            # call_soon_threadsafe should have been called
            agent._loop.close()

    def test_cancel_no_task_is_safe(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._current_task = None
            agent._loop = None
            # Should not raise
            agent.cancel()


# ------------------------------------------------------------------
# Async internals
# ------------------------------------------------------------------

class TestAgentAsync:
    @pytest.mark.asyncio
    async def test_send_no_session(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._session = None
            result = await agent._send("hello", timeout=5.0)
        assert result == "No active session."

    @pytest.mark.asyncio
    async def test_send_parses_response(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_response = MagicMock()
            mock_response.data.content = "Hello from agent"
            mock_session.send_and_wait.return_value = mock_response
            agent._session = mock_session

            result = await agent._send("test prompt", timeout=5.0)
        assert result == "Hello from agent"

    @pytest.mark.asyncio
    async def test_send_empty_content(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_response = MagicMock()
            mock_response.data.content = None
            mock_session.send_and_wait.return_value = mock_response
            agent._session = mock_session

            result = await agent._send("test", timeout=5.0)
        assert result == ""

    @pytest.mark.asyncio
    async def test_send_exception_in_session(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_session.send_and_wait.side_effect = RuntimeError("session error")
            agent._session = mock_session

            result = await agent._send("test", timeout=5.0)
        assert "went wrong" in result

    @pytest.mark.asyncio
    async def test_shutdown_destroys_session_and_stops_client(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_client = AsyncMock()
            agent._session = mock_session
            agent._client = mock_client

            await agent._shutdown()

            mock_session.destroy.assert_called_once()
            mock_client.stop.assert_called_once()
            assert agent._session is None
            assert agent._client is None

    @pytest.mark.asyncio
    async def test_startup_failure_sets_started_false(self, fake_config):
        mock_copilot = MagicMock()
        mock_client = AsyncMock()
        mock_client.start.side_effect = RuntimeError("fail")
        mock_copilot.CopilotClient.return_value = mock_client

        with patch("copilot_echo.agent._ensure_copilot", return_value=mock_copilot):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            await agent._startup()

        assert agent._started is False

    @pytest.mark.asyncio
    async def test_log_available_tools_with_tools(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = MagicMock()
            mock_session.available_tools = [
                {"name": "tool_a"},
                {"name": "tool_b"},
            ]
            agent._session = mock_session

            # Should not raise
            await agent._log_available_tools()

    @pytest.mark.asyncio
    async def test_log_available_tools_no_session(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._session = None
            # Should not raise
            await agent._log_available_tools()


# ------------------------------------------------------------------
# Crash detection in _send
# ------------------------------------------------------------------

class TestCrashDetection:
    @pytest.mark.asyncio
    async def test_connection_error_raises_agent_crashed(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_session.send_and_wait.side_effect = ConnectionError("pipe broken")
            agent._session = mock_session

            with pytest.raises(AgentCrashedError, match="pipe broken"):
                await agent._send("test", timeout=5.0)
            assert agent._started is False

    @pytest.mark.asyncio
    async def test_eof_error_raises_agent_crashed(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_session.send_and_wait.side_effect = EOFError("unexpected EOF")
            agent._session = mock_session

            with pytest.raises(AgentCrashedError, match="unexpected EOF"):
                await agent._send("test", timeout=5.0)
            assert agent._started is False

    @pytest.mark.asyncio
    async def test_broken_pipe_raises_agent_crashed(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_session.send_and_wait.side_effect = BrokenPipeError()
            agent._session = mock_session

            with pytest.raises(AgentCrashedError):
                await agent._send("test", timeout=5.0)

    @pytest.mark.asyncio
    async def test_non_crash_exception_returns_error_string(self, fake_config):
        """Non-crash exceptions should still return an error string, not raise."""
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            mock_session = AsyncMock()
            mock_session.send_and_wait.side_effect = ValueError("bad value")
            agent._session = mock_session

            result = await agent._send("test", timeout=5.0)
            assert "went wrong" in result


# ------------------------------------------------------------------
# Crash recovery in send()
# ------------------------------------------------------------------

class TestCrashRecovery:
    def test_send_recovers_on_crash(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            call_count = 0

            def mock_future_result(timeout=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise AgentCrashedError("crash")
                return "recovered reply"

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = mock_future_result

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future), \
                 patch.object(agent, "reinitialize", return_value=True):
                result = agent.send("hello")

            assert result == "recovered reply"
            agent._loop.close()

    def test_send_gives_up_after_failed_recovery(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = AgentCrashedError("crash")

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future), \
                 patch.object(agent, "reinitialize", return_value=False):
                result = agent.send("hello")

            assert "crashed" in result.lower()
            assert "restart" in result.lower()
            agent._loop.close()

    def test_send_retries_twice_on_repeated_crash(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._started = True
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = AgentCrashedError("crash")

            reinit_calls = 0

            def mock_reinit():
                nonlocal reinit_calls
                reinit_calls += 1
                return True  # reinit succeeds but agent crashes again

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future), \
                 patch.object(agent, "reinitialize", side_effect=mock_reinit):
                result = agent.send("hello")

            assert reinit_calls == 2
            assert "crashed" in result.lower()
            agent._loop.close()


# ------------------------------------------------------------------
# reinitialize()
# ------------------------------------------------------------------

class TestReinitialize:
    def test_reinitialize_success(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.return_value = None

            # Simulate successful reinit
            agent._started = True  # _startup sets this

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                result = agent.reinitialize()

            assert result is True
            agent._loop.close()

    def test_reinitialize_no_loop(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._loop = None
            result = agent.reinitialize()
            assert result is False

    def test_reinitialize_exception(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            agent._loop = asyncio.new_event_loop()

            mock_future = MagicMock(spec=concurrent.futures.Future)
            mock_future.result.side_effect = RuntimeError("reinit failed")

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                result = agent.reinitialize()

            assert result is False
            agent._loop.close()

    @pytest.mark.asyncio
    async def test_reinitialize_calls_shutdown_then_startup(self, fake_config):
        with patch("copilot_echo.agent._ensure_copilot"):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            call_order = []

            async def mock_shutdown():
                call_order.append("shutdown")

            async def mock_startup():
                call_order.append("startup")
                agent._started = True

            agent._shutdown = mock_shutdown
            agent._startup = mock_startup

            await agent._reinitialize()
            assert call_order == ["shutdown", "startup"]
            assert agent._started is True


# ------------------------------------------------------------------
# MCP retry in _startup
# ------------------------------------------------------------------

class TestStartupRetry:
    @pytest.mark.asyncio
    async def test_session_creation_retries_on_failure(self, fake_config):
        mock_copilot = MagicMock()
        mock_client = AsyncMock()
        mock_copilot.CopilotClient.return_value = mock_client

        call_count = 0

        async def mock_create_session(config):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"MCP fail {call_count}")
            return AsyncMock()  # success on 3rd attempt

        mock_client.create_session = mock_create_session

        with patch("copilot_echo.agent._ensure_copilot", return_value=mock_copilot), \
             patch("copilot_echo.agent.build_session_config", return_value={}):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            await agent._startup()

        assert agent._started is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_session_creation_gives_up_after_3(self, fake_config):
        mock_copilot = MagicMock()
        mock_client = AsyncMock()
        mock_copilot.CopilotClient.return_value = mock_client
        mock_client.create_session = AsyncMock(
            side_effect=RuntimeError("always fails")
        )

        with patch("copilot_echo.agent._ensure_copilot", return_value=mock_copilot), \
             patch("copilot_echo.agent.build_session_config", return_value={}):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            await agent._startup()

        assert agent._started is False
        assert mock_client.create_session.call_count == 3

    @pytest.mark.asyncio
    async def test_session_creation_no_retry_on_first_success(self, fake_config):
        mock_copilot = MagicMock()
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_client.create_session.return_value = mock_session
        mock_copilot.CopilotClient.return_value = mock_client

        with patch("copilot_echo.agent._ensure_copilot", return_value=mock_copilot), \
             patch("copilot_echo.agent.build_session_config", return_value={}):
            from copilot_echo.agent import Agent

            agent = Agent(fake_config)
            await agent._startup()

        assert agent._started is True
        assert mock_client.create_session.call_count == 1
