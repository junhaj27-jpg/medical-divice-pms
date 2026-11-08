"""Measure JSON round trips and evaluation separately on the same synthetic batches."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

import pms_rule_batch
from reference import evaluate, prepare


def ms_since(start):
    return (perf_counter_ns() - start) / 1_000_000


def python_roundtrip(text):
    prepared = prepare(json.loads(text))
    start = perf_counter_ns()
    result = evaluate(prepared)
    compute = ms_since(start)
    return json.dumps(result, separators=(",", ":")), compute


def cli_roundtrip(cli, text):
    process = subprocess.run([str(cli), "--timings", "-"], input=text, encoding="utf-8",
                             capture_output=True, check=True)
    return process.stdout, json.loads(process.stderr)["compute_ms"]


def timed(engine, request):
    start = perf_counter_ns()
    output, compute = engine(json.dumps(request, separators=(",", ":")))
    decoded = json.loads(output)
    return decoded, compute, ms_since(start)


def benchmark(cli, repeats):
    sample = json.loads((HERE / "fixtures/cli-example.json").read_text(encoding="utf-8"))
    engines = {
        "Python": python_roundtrip,
        "C++ CLI": lambda text: cli_roundtrip(cli, text),
        "pybind11": pms_rule_batch.run_timed,
    }
    print(f"{platform.platform()} | CPython {platform.python_version()} | {repeats} repeats, one warm-up per engine")
    print("| Cases | Engine | Median compute ms | Median total ms |")
    print("| ---: | --- | ---: | ---: |")
    for count in (100, 1_000, 10_000):
        cases = sample["cases"]
        request = {**sample, "cases": [{**cases[i % len(cases)], "id": f"EX-BENCH-{i}"} for i in range(count)]}
        warmups = [timed(engine, request)[0] for engine in engines.values()]
        assert all(result == warmups[0] for result in warmups[1:])
        times = {name: [] for name in engines}
        names = list(engines)
        for iteration in range(repeats):
            for index in range(len(names)):
                name = names[(index + iteration) % len(names)]
                _, compute, total = timed(engines[name], request)
                times[name].append((compute, total))
        for name, results in times.items():
            compute, total = map(median, zip(*results))
            print(f"| {count:,} | {name} | {compute:.3f} | {total:.3f} |")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    benchmark(args.cli.resolve(), args.repeats)
