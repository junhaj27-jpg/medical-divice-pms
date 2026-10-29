"""Synthetic adapter fixtures, never a real provider integration."""
def echo(**kwargs):
    c=kwargs["evidence"][0]
    return dict(items=[dict(chunk_id=c["chunk_id"],quote=c["text"])],missing=[],conflicts=[])

def timeout(**kwargs):
    import time
    time.sleep(2)

def error(**kwargs):
    raise RuntimeError("sensitive provider details must not escape")

def wrong_json_type(**kwargs):
    return "not an object"
