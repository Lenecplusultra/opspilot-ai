"""Run the eval suite.

    python -m app.evals --scripted                 # harness self-test, no API key
    python -m app.evals --model gpt-4o-mini -k 3   # real model, 3 repeats per case

Exits non-zero if any run fails or any safety check is violated.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

from app.agents.llm import ScriptedChatModel, make_openai_llm
from app.core.config import BACKEND_DIR, settings
from app.evals.harness import load_cases, run_suite, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scripted", action="store_true", help="replay each case's reference trajectory")
    mode.add_argument("--model", default=None, help=f"OpenAI model (default {settings.openai_model})")
    parser.add_argument("-k", "--repeats", type=int, default=1, help="runs per case")
    parser.add_argument("--cases", default="", help="comma-separated case ids (default all)")
    parser.add_argument("--out", type=Path, default=BACKEND_DIR / "eval-reports")
    args = parser.parse_args()

    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c.id in wanted]
    if not cases:
        sys.exit("no matching cases")

    if args.scripted:
        label = "scripted reference trajectories"
        factory = lambda case: ScriptedChatModel(script=case.reference)  # noqa: E731
    else:
        model = args.model or settings.openai_model
        label = f"{model}, k={args.repeats}"
        make_openai_llm(model)  # fail fast if the key is missing
        factory = lambda case: make_openai_llm(model)  # noqa: E731

    def progress(r):
        mark = "PASS" if r.passed else "FAIL"
        failed = ", ".join(c.name for c in r.checks if not c.passed)
        print(f"[{mark}] {r.case_id} #{r.repeat + 1}  score={r.score}  tools={r.steps}  {r.latency_s}s"
              + (f"  failed: {failed}" if failed else ""), flush=True)

    summaries = run_suite(cases, factory, args.repeats, on_result=progress)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = "scripted" if args.scripted else (args.model or settings.openai_model)
    report, totals = write_report(summaries, label, args.out / f"{stamp}-{slug}")
    print(f"\npass rate {totals['pass_rate']:.0%} | pass^k {totals['pass_all_repeats']:.0%} | "
          f"safety violations {totals['safety_violations']}\nreport: {report}")
    return 0 if totals["pass_rate"] == 1.0 and totals["safety_violations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
