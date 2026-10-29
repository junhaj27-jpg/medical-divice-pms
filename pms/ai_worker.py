"""Trusted adapter only. Document text is passed as data, never evaluated."""
import contextlib
import json
import sys
import django

def main():
    data=json.load(sys.stdin)
    # Suppress accidental provider prints, including secrets, in the JSON channel.
    with contextlib.redirect_stdout(sys.stderr):
        django.setup()
        from django.utils.module_loading import import_string
        response=import_string(data["adapter"])(system=data["system"],request=data["request"],evidence=data["evidence"])
    json.dump(response,sys.stdout,ensure_ascii=False)

if __name__=="__main__":
    try: main()
    except Exception: sys.exit(1)
