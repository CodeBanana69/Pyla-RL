"""Subprocess helpers that decode child output as UTF-8 on all locales."""

from __future__ import annotations

import subprocess

SUBPROCESS_TEXT_KWARGS = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


def run_text(*popenargs, **kwargs):
    merged = {**SUBPROCESS_TEXT_KWARGS, **kwargs}
    return subprocess.run(*popenargs, **merged)


def check_output_text(*popenargs, **kwargs):
    merged = {
        "encoding": "utf-8",
        "errors": "replace",
        **kwargs,
    }
    return subprocess.check_output(*popenargs, **merged)
