"""Pure model, time, curves and undo.

This package must import neither Qt nor any audio device library. That is
requirement N-5, and it is enforced by tests/test_layering.py — it is what
keeps the model testable headless.
"""
