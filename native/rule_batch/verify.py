"""Cross-engine parity, fixed expected examples and CLI I/O checks."""
import argparse
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

import pms_rule_batch
from reference import evaluate, prepare


def verify(cli, wasm, node):
    examples = json.loads((HERE / "fixtures/examples.json").read_text(encoding="utf-8"))
    batches = [
        {"schema_version": 1, **sample, "rules": [left, right]}
        for sample in examples["markets"]
        for left, right in itertools.product(sample["rules"], repeat=2)
    ]
    wasm_results = json.loads(subprocess.run(
        [node, str(HERE / "wasm_runner.cjs"), str(wasm.resolve())], input=json.dumps(batches),
        text=True, capture_output=True, check=True,
    ).stdout)
    count = 0
    for batch, wasm_result in zip(batches, wasm_results, strict=True):
        data = json.dumps(batch)
        python_result = evaluate(prepare(batch))
        cli_result = subprocess.run([str(cli.resolve()), "-"], input=data, text=True,
                                    capture_output=True, check=True)
        assert not cli_result.stderr
        outputs = (json.loads(cli_result.stdout), json.loads(pms_rule_batch.run_json(data)), wasm_result)
        for engine, result in zip(("CLI", "pybind11", "WASM"), outputs):
            assert result == python_result, (engine, batch["market"], [r["id"] for r in batch["rules"]])
        count += len(batch["cases"])

    fixture = HERE / "fixtures/cli-example.json"
    file_result = json.loads(subprocess.run([str(cli.resolve()), str(fixture)], text=True,
                                           capture_output=True, check=True).stdout)
    # On Windows the fixture can be under a non-ASCII parent path. Relative CLI
    # paths are also part of the documented invocation.
    assert file_result == evaluate(prepare(json.loads(fixture.read_text(encoding="utf-8"))))
    rows = {r["case_id"]: r for r in file_result["results"]}
    assert rows["EX-KR-LEAP"]["baseline"]["due_at"] == "2024-03-01T18:00:00+09:00"
    assert rows["EX-KR-MONTH"]["baseline"]["due_date"] == "2024-02-02"
    assert rows["EX-KR-YEAR"]["baseline"]["due_date"] == "2025-01-02"
    assert rows["EX-KR-HOLIDAYS"]["proposed"]["due_date"] == "2024-05-30"
    assert rows["EX-KR-HOLIDAYS"]["delta_days"] == 4
    assert rows["EX-KR-MISSING"]["baseline"]["reason"] == "missing_input"
    assert rows["EX-KR-MISMATCH"]["baseline"]["reason"] == "date_mismatch"
    assert rows["EX-KR-COVERAGE"]["proposed"]["reason"] == "calculation_unverified"
    assert rows["EX-KR-SOURCE"]["baseline"]["reason"] == "source_unverified"
    us = next(b for b in batches if b["market"] == "US" and [r["version"] for r in b["rules"]] == [1, 2])
    us_result = evaluate(prepare(us))["results"]
    assert us_result[0]["baseline"]["due_date"] == "2024-05-29"
    assert us_result[1]["baseline"]["reason"] == "unsupported_timestamp"
    mismatch = next(b for b in batches if b["market"] == "KR" and [r["version"] for r in b["rules"]] == [1, 3])
    assert evaluate(prepare(mismatch))["results"][0]["changes"] == ["decision_changed", "deadline_removed"]
    same = next(b for b in batches if b["market"] == "DE" and [r["version"] for r in b["rules"]] == [1, 1])
    assert evaluate(prepare(same))["results"][0]["changes"] == ["unchanged"]

    for payload in ("{", '{"schema_version":2}', json.dumps({**batches[0], "cases": [batches[0]["cases"][0]] * 2})):
        process = subprocess.run([str(cli.resolve())], input=payload, text=True, capture_output=True)
        assert process.returncode == 2 and not process.stdout
        assert json.loads(process.stderr)["error"]["code"] == "invalid_input"
        try:
            pms_rule_batch.run_json(payload)
        except ValueError:
            pass
        else:
            raise AssertionError("binding accepted malformed input")
    process = subprocess.run([str(cli.resolve()), "nonexistent-pms-batch-example.json"], text=True, capture_output=True)
    assert process.returncode == 3 and not process.stdout
    assert json.loads(process.stderr)["error"]["code"] == "io_error"
    print(f"Python = CLI = pybind11 = WASM: {len(batches)} batches, {count} case comparisons; CLI file/stdin/errors passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--wasm", type=Path, required=True)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    verify(args.cli, args.wasm, args.node)
