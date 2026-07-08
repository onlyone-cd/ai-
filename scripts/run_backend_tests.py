import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

TEST_MODES = {
    "unit": ["tests/test_matching.py", "tests/test_tag_library.py"],
    "api": ["tests/test_api.py"],
    "all": ["tests"],
}


def main():
    parser = argparse.ArgumentParser(description="Run backend tests with a clear timeout and duration report.")
    parser.add_argument("--mode", choices=sorted(TEST_MODES), default="all", help="Test slice to run.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Hard timeout for the selected test slice.")
    parser.add_argument("--durations", type=int, default=20, help="Number of slowest tests/setup phases to report.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra pytest args after --.")
    args = parser.parse_args()

    extra_args = args.pytest_args
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--durations={max(0, args.durations)}",
        *TEST_MODES[args.mode],
        *extra_args,
    ]
    env = os.environ.copy()
    env.setdefault("LLM_ENABLED", "false")

    print(f"Running backend tests: mode={args.mode}, timeout={args.timeout_seconds}s", flush=True)
    print("Command:", " ".join(command), flush=True)
    try:
        completed = subprocess.run(command, cwd=BACKEND, env=env, timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            f"Backend test slice '{args.mode}' exceeded {args.timeout_seconds}s. "
            "Run with --mode api --durations 30 to inspect slow tests.",
            file=sys.stderr,
        )
        return 124
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
