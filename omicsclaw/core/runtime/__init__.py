"""Skill-runner runtime helpers.

These modules were carved out of the original 634-line ``skill_runner.run_skill``
god-function (see OMI-12 evaluation, P1.4) so that each responsibility lives
in one file and can be tested in isolation:

- ``argv_builder``: build the subprocess argv and filter LLM-supplied
  ``extra_args`` against each skill's ``allowed_extra_flags`` allow-list.
- ``subprocess_driver``: spawn the subprocess, stream stdout/stderr via
  callbacks, run the orphan reaper, and honour ``cancel_event``.
- ``output_finalize``: rename auto-generated output dirs, emit the
  human-readable README, and generate the reproducibility notebook.
- ``pipeline_runner``: drive the pre-defined ``spatial-pipeline`` chain.

The ``skill_runner`` module remains the public entry point — these
submodules are implementation detail and are not part of the public
import surface.
"""
