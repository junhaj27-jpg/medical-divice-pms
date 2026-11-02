from pathlib import Path
p=Path('work/package_deliverables.py');s=p.read_text(encoding='utf-8').replace("Path(d).name/p.name","Path(Path(d).name)/p.name").replace("'diff-check.log']", "'diff-check.log','final-exits.json']");p.write_text(s,encoding='utf-8')
