"""Stop: optional real build/lint/test layer with graceful degradation.

Off by default to keep Stop fast. Enabled via GIGACODE_DEV_RUN_BUILD=1 or a
'build-check: on' line in the latest plan. Missing tooling or timeouts never
block; the limitation is recorded instead (same policy as repomix/graphify).
"""

from __future__ import annotations

import os
import subprocess

from checks.stop_final import should_validate
from hooklib import buildsystem, plandoc
from hooklib.event import Result, last_message


COMMAND_TIMEOUT = 300
OUTPUT_TAIL_LINES = 40


def enabled() -> bool:
    if os.environ.get("GIGACODE_DEV_RUN_BUILD") == "1":
        return True
    plan = plandoc.find_latest_plan()
    return plan is not None and plandoc.build_check_enabled(plan)


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    if not should_validate(last_message(event)):
        return Result(decision="allow", reason="")
    if not enabled():
        return Result(decision="allow", reason="Build layer disabled; static checks only.")

    info = buildsystem.detect()
    command_set = buildsystem.commands(info)
    if not command_set:
        return Result(
            decision="allow",
            reason="Build layer enabled but no usable build tool found.",
            stop_reason=(
                "Limitation: real build/test checks were not executed "
                "(no Gradle/Maven wrapper or binary). Static checks only."
            ),
        )

    for stage in ("compile", "test", "lint"):
        argv = command_set.get(stage)
        if not argv:
            continue
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return Result(
                decision="allow",
                reason=f"Build stage '{stage}' could not run.",
                stop_reason=(
                    f"Limitation: real build/test checks were not executed ({error}). "
                    "Static checks only."
                ),
            )
        if completed.returncode != 0:
            tail = "\n".join(
                (completed.stdout + "\n" + completed.stderr).strip().splitlines()[-OUTPUT_TAIL_LINES:]
            )
            return Result(
                decision="block",
                reason=f"Build stage '{stage}' failed ({' '.join(argv)}).",
                stop_reason=tail,
            )

    return Result(decision="allow", reason="Build, tests and lint passed.")
