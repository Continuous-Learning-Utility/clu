"""Tests for orchestrator/resilience.py and daemon/alerts.py."""

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from orchestrator.providers.base import LLMProvider, LLMResponse
from orchestrator.resilience import (
    ExponentialBackoff,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    ResilientProvider,
)
from daemon.alerts import AlertManager, AlertLevel


# ---- ExponentialBackoff ----

class TestExponentialBackoff(unittest.TestCase):

    def test_delay_increases(self):
        bo = ExponentialBackoff(base=1.0, jitter=0)
        self.assertAlmostEqual(bo.delay(0), 1.0)
        self.assertAlmostEqual(bo.delay(1), 2.0)
        self.assertAlmostEqual(bo.delay(2), 4.0)

    def test_delay_capped(self):
        bo = ExponentialBackoff(base=1.0, max_delay=5.0, jitter=0)
        self.assertAlmostEqual(bo.delay(10), 5.0)

    def test_jitter_adds_randomness(self):
        bo = ExponentialBackoff(base=1.0, jitter=0.5)
        delays = [bo.delay(0) for _ in range(20)]
        # With jitter, not all delays should be identical
        self.assertTrue(len(set(delays)) > 1)


# ---- CircuitBreaker ----

class TestCircuitBreaker(unittest.TestCase):

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allows_request)

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allows_request)

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_success_resets_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        self.assertEqual(cb._failure_count, 0)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allows_request)

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state  # trigger transition to HALF_OPEN
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state
        cb.record_failure()
        self.assertEqual(cb._state, CircuitState.OPEN)

    def test_status_dict(self):
        cb = CircuitBreaker()
        status = cb.status
        self.assertIn("state", status)
        self.assertIn("failure_count", status)
        self.assertIn("total_trips", status)


# ---- ResilientProvider ----

class MockProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0
        self.should_fail = 0  # Number of times to fail before succeeding

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat_completion(self, messages, tools=None, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self.call_count <= self.should_fail:
            raise ConnectionError("Connection refused")
        return LLMResponse(content="ok", prompt_tokens=10, completion_tokens=5)

    def test_connection(self) -> dict:
        return {"ok": True}


class TestResilientProvider(unittest.TestCase):

    def test_success_passes_through(self):
        mock = MockProvider()
        rp = ResilientProvider(mock, max_retries=3)
        resp = rp.chat_completion(messages=[])
        self.assertEqual(resp.content, "ok")
        self.assertEqual(mock.call_count, 1)

    def test_retries_on_transient_error(self):
        mock = MockProvider()
        mock.should_fail = 2  # Fail first 2, succeed on 3rd

        rp = ResilientProvider(
            mock, max_retries=3,
            backoff=ExponentialBackoff(base=0.01, jitter=0),
        )
        resp = rp.chat_completion(messages=[])
        self.assertEqual(resp.content, "ok")
        self.assertEqual(mock.call_count, 3)
        self.assertEqual(rp._total_retries, 2)

    def test_gives_up_after_max_retries(self):
        mock = MockProvider()
        mock.should_fail = 999

        rp = ResilientProvider(
            mock, max_retries=2,
            backoff=ExponentialBackoff(base=0.01, jitter=0),
        )
        with self.assertRaises(ConnectionError):
            rp.chat_completion(messages=[])
        self.assertEqual(mock.call_count, 3)  # initial + 2 retries
        self.assertEqual(rp._total_failures, 1)

    def test_circuit_breaker_opens(self):
        mock = MockProvider()
        mock.should_fail = 999

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=999)
        rp = ResilientProvider(
            mock, max_retries=0,
            circuit_breaker=cb,
        )

        # First two calls fail and open the circuit
        for _ in range(2):
            with self.assertRaises(ConnectionError):
                rp.chat_completion(messages=[])

        # Third call should be rejected by circuit breaker
        with self.assertRaises(CircuitOpenError):
            rp.chat_completion(messages=[])

    def test_provider_name_passthrough(self):
        mock = MockProvider()
        rp = ResilientProvider(mock)
        self.assertEqual(rp.provider_name, "mock")
        self.assertEqual(rp.model_name, "mock-model")

    def test_status(self):
        mock = MockProvider()
        rp = ResilientProvider(mock)
        rp.chat_completion(messages=[])
        status = rp.status
        self.assertEqual(status["total_calls"], 1)
        self.assertEqual(status["total_retries"], 0)

    def test_non_retryable_error_not_retried(self):
        """ValueError is not retryable — should fail immediately."""
        mock = MockProvider()
        mock.chat_completion = MagicMock(side_effect=ValueError("bad input"))

        rp = ResilientProvider(
            mock, max_retries=3,
            backoff=ExponentialBackoff(base=0.01, jitter=0),
        )
        with self.assertRaises(ValueError):
            rp.chat_completion(messages=[])
        # Only called once (no retries for non-retryable errors)
        self.assertEqual(mock.chat_completion.call_count, 1)


# ---- AlertManager ----

class TestAlertManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "alerts.json")
        self.am = AlertManager(path=self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_list(self):
        self.am.add("info", "test", "Hello")
        self.am.add("warning", "test", "Warning!")
        alerts = self.am.list_alerts()
        self.assertEqual(len(alerts), 2)
        # Newest first
        self.assertEqual(alerts[0]["level"], "warning")

    def test_mark_read(self):
        aid = self.am.add("info", "test", "msg")
        self.assertTrue(self.am.mark_read(aid))
        alerts = self.am.list_alerts(unread_only=True)
        self.assertEqual(len(alerts), 0)

    def test_mark_all_read(self):
        self.am.add("info", "a", "1")
        self.am.add("info", "b", "2")
        count = self.am.mark_all_read()
        self.assertEqual(count, 2)
        self.assertEqual(self.am.unread_count(), 0)

    def test_delete(self):
        aid = self.am.add("error", "test", "bad")
        self.assertTrue(self.am.delete(aid))
        self.assertEqual(len(self.am.list_alerts()), 0)

    def test_clear(self):
        self.am.add("info", "a", "1")
        self.am.add("info", "b", "2")
        count = self.am.clear()
        self.assertEqual(count, 2)
        self.assertEqual(len(self.am.list_alerts()), 0)

    def test_filter_by_level(self):
        self.am.add("info", "a", "info msg")
        self.am.add("error", "b", "error msg")
        errors = self.am.list_alerts(level="error")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["message"], "error msg")

    def test_stats(self):
        self.am.add("info", "a", "1")
        self.am.add("warning", "b", "2")
        self.am.add("error", "c", "3")
        stats = self.am.stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["unread"], 3)
        self.assertEqual(stats["by_level"]["error"], 1)

    def test_max_alerts_trimming(self):
        am = AlertManager(path=self.path, max_alerts=5)
        for i in range(10):
            am.add("info", "test", f"msg {i}")
        alerts = am.list_alerts(limit=100)
        self.assertEqual(len(alerts), 5)

    def test_unread_count(self):
        self.am.add("info", "a", "1")
        self.am.add("info", "b", "2")
        self.assertEqual(self.am.unread_count(), 2)
        self.am.mark_all_read()
        self.assertEqual(self.am.unread_count(), 0)


if __name__ == "__main__":
    unittest.main()
