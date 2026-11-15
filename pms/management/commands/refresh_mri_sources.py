import io
from urllib.request import Request, urlopen
from pypdf import PdfReader
from django.core.management.base import BaseCommand
from pms.fda_library import record_reference
from pms.mri_catalog import catalog


class Command(BaseCommand):
    help = "Register verified MRI sources idempotently; --fetch attempts only the two fixed FDA PDF URLs."

    def add_arguments(self, parser):
        parser.add_argument("--fetch", action="store_true")

    def handle(self, *args, **options):
        for values in catalog():
            if options["fetch"] and values["pdf_url"]:
                try:
                    with urlopen(Request(values["pdf_url"], headers={"User-Agent":"MedWatch-PMS/1.0"}), timeout=15) as response:
                        raw = response.read(10_000_001)
                    if len(raw) > 10_000_000 or not raw.startswith(b"%PDF-"):
                        raise ValueError("Invalid PDF or size limit")
                    pages = {str(i+1):p.extract_text() or "" for i,p in enumerate(PdfReader(io.BytesIO(raw)).pages)}
                    import hashlib
                    values.update(pages=pages,retrieval_status="pdf_text",failure_reason="")
                    values["metadata"]["pdf_sha256"] = hashlib.sha256(raw).hexdigest()
                except Exception as exc:
                    # Keep verified text; never replace it with an empty response or 'no new documents'.
                    self.stderr.write(f'{values["key"]}: PDF lookup failed ({type(exc).__name__}); verified source retained')
            source, created = record_reference(values)
            self.stdout.write(f'{source.key} v{source.version}: {"created" if created else "existing"}')
