"""Compare two locally available PMS revisions in isolated SQLite environments."""

import argparse
from contextlib import closing
from dataclasses import dataclass
from html import escape
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "junhaj27-jpg/medical-divice-pms"
SUITES = {"Django tests": (), "Foreign tests": ("pms.test_foreign",)}
RECORD_TABLES = ("pms_medicaldevice", "pms_customercomplaint")
RELATED_TABLES = (
    "pms_manufacturer",
    "pms_udi",
    "pms_productlot",
    "pms_softwarerelease",
    "pms_customercomplaint_affected_releases",
)


def resolve_ref(ref):
    if ref.startswith("refs/"):
        choices = [ref]
        if ref.startswith("refs/heads/"):
            choices.append("refs/remotes/origin/" + ref.removeprefix("refs/heads/"))
    else:
        choices = [f"refs/heads/{ref}", f"refs/remotes/origin/{ref}", f"refs/tags/{ref}"]
    for choice in choices:
        result = subprocess.run(
            ["git", "show-ref", "--verify", choice],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return subprocess.check_output(
                ["git", "rev-parse", "--verify", f"{choice}^{{commit}}"],
                cwd=ROOT, text=True,
            ).strip()
    if re.fullmatch(r"[0-9a-fA-F]{4,40}", ref):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    raise ValueError(f"Cannot resolve {ref!r} to a commit. Check local branches, origin branches, and tags.")


@dataclass
class Check:
    status: str
    detail: str = ""
    failures: frozenset = frozenset()

    def label(self):
        return f"{self.status} ({escape(self.detail)})" if self.detail else self.status


@dataclass
class Version:
    name: str
    sha: str
    root: Path

    @property
    def source(self):
        return self.root / "source"

    @property
    def python(self):
        relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return self.root / "venv" / relative

    def prepare(self):
        print(f"\n--- {self.name}: {self.sha} ---", flush=True)
        self.root.mkdir()
        archive = self.root / "source.tar"
        subprocess.run(
            ["git", "archive", "--format=tar", "-o", str(archive), self.sha], cwd=ROOT, check=True,
        )
        with tarfile.open(archive) as source:
            source.extractall(self.source, filter="data")
        archive.unlink()
        subprocess.run([sys.executable, "-m", "venv", str(self.root / "venv")], check=True)
        subprocess.run([self.python, "-m", "pip", "install", "-r", "requirements.txt"],
                       cwd=self.source, check=True)

    def manage(self, *args, database=None):
        env = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "DJANGO_SETTINGS_MODULE"):
            env.pop(name, None)
        env.update(
            DB_ENGINE="sqlite",
            SQLITE_PATH=str(database or self.root / "checks.sqlite3"),
            PRIVATE_MEDIA_ROOT=str(self.root / "media"),
            PMS_STATIC_ROOT=str(self.root / "static"),
            SECRET_KEY="comparison-only-secret-key",
            DEMO_PASSWORD="comparison-only-demo-password",
            DEBUG="False",
            PYTHONIOENCODING="utf-8",
            PYTHONUNBUFFERED="1",
        )
        print(f"\n[{self.name}] python manage.py {' '.join(args)}", flush=True)
        command = [self.python, "manage.py", *args]
        try:
            result = subprocess.run(
                command, cwd=self.source, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
            )
        except OSError as error:
            result = subprocess.CompletedProcess(command, 127, f"Could not start Django: {error}\n")
        print(result.stdout, end="", flush=True)
        return result


def test_result(result):
    # unittest emits this footer only after completing the suite. Import errors
    # represented as _FailedTest prevent the affected suite from being compared.
    footer = re.search(
        r"(?m)^-{70}\r?\nRan (\d+) tests? in [^\n]+\n\s*(OK|FAILED)(?: \(([^)\n]*)\))?\s*$",
        result.stdout,
    )
    if not footer:
        return Check("INCOMPLETE", f"no unittest result footer, exit {result.returncode}")

    count, outcome, counters = footer.groups()
    if result.returncode != (0 if outcome == "OK" else 1):
        return Check("INCOMPLETE", f"exit {result.returncode} conflicts with unittest result")
    failures = re.findall(
        r"(?m)^={70}\r?\n(?:FAIL|ERROR): ([^\r\n]+)",
        result.stdout[:footer.start()],
    )
    unexpected = re.search(
        r"(?m)^={70}\r?\n((?:UNEXPECTED SUCCESS: [^\r\n]+\r?\n)+)",
        result.stdout[:footer.start()],
    )
    if unexpected:
        failures.extend(line.removeprefix("UNEXPECTED SUCCESS: ")
                        for line in unexpected[1].splitlines())
    if any("unittest.loader._FailedTest" in name for name in failures):
        return Check("INCOMPLETE", "test module failed to load")
    expected = sum(int(number) for number in re.findall(
        r"(?:^|, )(?:failures|errors|unexpected successes)=(\d+)", counters or "",
    ))
    if len(failures) != expected:
        return Check("INCOMPLETE", "could not identify every reported test failure")
    detail = f"{count} run"
    if counters:
        detail += f", {counters}"
    return Check("PASS" if outcome == "OK" else "FAIL", detail, frozenset(failures))


def verify_version(version):
    checks = {}
    result = version.manage("makemigrations", "--check", "--dry-run")
    checks["Migration check"] = Check("PASS" if result.returncode == 0 else "FAIL",
                                      f"exit {result.returncode}")
    for suite, labels in SUITES.items():
        if labels and not any(
            (version.source / "pms" / name).exists() for name in ("test_foreign.py", "test_foreign")
        ):
            checks[suite] = Check("SKIPPED", "pms.test_foreign is absent")
            continue
        checks[suite] = test_result(version.manage("test", *labels, "--noinput", "--verbosity", "2"))
    return checks


def columns(connection, table):
    return tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{table}")'))


def records(connection, table, fields):
    # Quote column identifiers, including names read from SQLite's schema.
    identifiers = ", ".join('"' + name.replace('"', '""') + '"' for name in fields)
    return dict((row[0], row[1:]) for row in connection.execute(
        f'SELECT "id", {identifiers} FROM "{table}"'
    ))


def verify_upgrade(baseline, candidate):
    original = baseline.root / "demo.sqlite3"
    upgraded = candidate.root / "upgraded.sqlite3"
    for args in (("migrate", "--noinput"), ("seed_demo",)):
        result = baseline.manage(*args, database=original)
        if result.returncode:
            return Check("FAIL", f"baseline {args[0]} exited {result.returncode}")

    with closing(sqlite3.connect(original)) as before, closing(sqlite3.connect(upgraded)) as after:
        before.backup(after)

    result = candidate.manage("migrate", "--noinput", database=upgraded)
    if result.returncode:
        return Check("FAIL", f"candidate migrate exited {result.returncode}")

    counts = {}
    differences = []
    with closing(sqlite3.connect(original)) as before, closing(sqlite3.connect(upgraded)) as after:
        for table in (*RECORD_TABLES, *RELATED_TABLES):
            fields = columns(before, table)
            if not fields and table in RELATED_TABLES:
                continue
            if "id" not in fields:
                differences.append(f"{table} has no baseline ID column")
                continue
            missing = set(fields) - set(columns(after, table))
            if missing:
                differences.append(f"{table} lost columns {', '.join(sorted(missing))}")
                continue
            fields = tuple(field for field in fields if field != "id")
            old, new = records(before, table, fields), records(after, table, fields)
            counts[table] = len(old)
            if table in RECORD_TABLES and not old:
                differences.append(f"seed_demo produced no rows in {table}")
            removed, added = old.keys() - new.keys(), new.keys() - old.keys()
            changed = [key for key in old.keys() & new.keys() if old[key] != new[key]]
            if removed or added or changed:
                differences.append(f"{table}: IDs removed {sorted(removed)}, "
                                   f"added {sorted(added)}, changed {sorted(changed)}")
        if after.execute("PRAGMA foreign_key_check").fetchone():
            differences.append("upgraded database has invalid foreign keys")
    if differences:
        return Check("FAIL", ". ".join(differences))
    return Check("PASS", f"{counts[RECORD_TABLES[0]]} devices, {counts[RECORD_TABLES[1]]} complaints, "
                         f"{sum(counts[table] for table in RELATED_TABLES if table in counts)} related rows preserved")


def write_summary(lines):
    summary = "\n".join(lines) + "\n"
    print("\n" + summary, flush=True)
    if path := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as file:
            file.write(summary)


def summarize(versions, results, upgrade):
    baseline, candidate = versions
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repository = os.getenv("GITHUB_REPOSITORY", REPOSITORY)
    url = f"{server}/{repository}/compare/{baseline.sha}...{candidate.sha}"
    lines = [
        "## PMS version comparison", "",
        f"- Baseline: `{baseline.sha}`",
        f"- Candidate: `{candidate.sha}`",
        f"- [GitHub Compare]({url})", "",
        "| Check | Baseline | Candidate |",
        "| --- | --- | --- |",
    ]
    for name in ("Migration check", *SUITES):
        first, second = (result[name].label().replace("|", "&#124;") for result in results)
        lines.append(f"| {name} | {first} | {second} |")
    lines.extend(["", f"**SQLite upgrade:** {upgrade.label()}"])
    for name in SUITES:
        first, second = (result[name] for result in results)
        lines.extend(["", f"### {name} failure comparison", ""])
        if any(check.status not in {"PASS", "FAIL"} for check in (first, second)):
            lines.append(f"Unavailable. Baseline: {first.label()}. Candidate: {second.label()}.")
            continue
        groups = {
            "New failures": second.failures - first.failures,
            "Existing failures still present": second.failures & first.failures,
            "Baseline failures absent from candidate failures": first.failures - second.failures,
        }
        for title, failures in groups.items():
            lines.append(f"- {title}: {len(failures)}")
            lines.extend(f"  - <code>{escape(name)}</code>" for name in sorted(failures))
    write_summary(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="5d730ff")
    parser.add_argument("--candidate", default="main")
    args = parser.parse_args()
    try:
        shas = [resolve_ref(ref) for ref in (args.baseline, args.candidate)]
    except (ValueError, subprocess.CalledProcessError) as error:
        write_summary(["## PMS version comparison", "", f"**INCOMPLETE:** {escape(str(error))}"])
        return 1

    with tempfile.TemporaryDirectory(prefix="pms-compare-") as directory:
        versions = [Version(name, sha, Path(directory) / name)
                    for name, sha in zip(("baseline", "candidate"), shas)]
        results = []
        ready = []
        for version in versions:
            try:
                version.prepare()
            except (OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
                print(error, file=sys.stderr)
                results.append({name: Check("INCOMPLETE", "source export or environment setup failed")
                                for name in ("Migration check", *SUITES)})
                continue
            ready.append(version)
            results.append(verify_version(version))

        if len(ready) == 2:
            try:
                upgrade = verify_upgrade(*versions)
            except (OSError, sqlite3.Error) as error:
                upgrade = Check("FAIL", str(error))
        else:
            upgrade = Check("SKIPPED", "one or both version environments could not be prepared")
        summarize(versions, results, upgrade)
        return int(upgrade.status != "PASS" or any(
            check.status not in {"PASS", "SKIPPED"} for result in results for check in result.values()
        ))


if __name__ == "__main__":
    raise SystemExit(main())
