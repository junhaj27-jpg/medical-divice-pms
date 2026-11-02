from pathlib import Path
p=Path('config/settings.py');s=p.read_text(encoding='utf-8').replace('STATIC_ROOT=BASE_DIR/"staticfiles"','STATIC_ROOT=Path(os.getenv("STATIC_ROOT",str(BASE_DIR/"staticfiles")))');p.write_text(s,encoding='utf-8')
