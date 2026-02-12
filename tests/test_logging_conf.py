"""Tests for copilot_echo.logging_conf."""

import logging

from copilot_echo.logging_conf import configure_logging


def test_configure_logging_sets_root_level():
    # Clear existing handlers so basicConfig takes effect
    logging.root.handlers.clear()
    configure_logging("DEBUG")
    assert logging.root.level == logging.DEBUG


def test_configure_logging_info_level():
    logging.root.handlers.clear()
    configure_logging("INFO")
    assert logging.root.level == logging.INFO


def test_configure_logging_suppresses_noisy_loggers():
    logging.root.handlers.clear()
    configure_logging("DEBUG")
    assert logging.getLogger("faster_whisper").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("comtypes").level == logging.WARNING
