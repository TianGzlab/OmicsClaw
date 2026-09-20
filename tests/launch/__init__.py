"""Tests for ``omicsclaw/launch/`` — plan 0037, scheme C.

Six files, one per property the plan asks this layer to hold:

``test_grammar.py``
    The entry points are three, they are enumerable, and a command line
    is cut at ``--`` with the two halves going to different owners.

``test_cli_command.py``
    The CLI surface run as a **command**, in a subprocess, through the
    real ``__main__``. Plan 0031 §9-10 asked for one such test and got a
    green suite next to a crashing command anyway, because the provider
    double was wider than the protocol; that lesson is why the shim here
    is itself checked against ``LLMProvider``'s published surface.

``test_channel_command.py``
    The Channel surface, likewise as a real process —— and the one that
    receives a real signal. It replaces plan 0037 §8-4's original
    channel smoke, ``oc channel -- --list``, which returned before
    anything was assembled: a command that ran and started nothing.

``test_launch_is_above_entry.py``
    The arrow points one way, the two globals are read in one place, and
    this shell names no deployment flag.

``test_the_environment_is_read_in_known_places.py``
    The inventory that replaced plan 0037 §3-1's claim that
    ``resolve_app_config`` had exactly one exception. It had four more.

``test_surfaces.py``
    The three starters' own branches. Written after the review measured
    83 of ``_surfaces.py``'s 297 statements as never executed —— and
    then read them and found them correct. A correct branch with no test
    is a bug's future address.

**No ``pytest-asyncio`` on this machine**, and no ``pytest-timeout``
either — so nothing here is allowed to be written as "this must hang".
Every subprocess carries an explicit ``timeout=``.
"""
