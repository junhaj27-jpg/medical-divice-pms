"""Explicit download operation; no queries or source bodies are accepted by this command."""
import hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen
from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from pms.local_search_models import identity


class Command(BaseCommand):
    help='Download a pinned public model snapshot and verify LFS SHA-256 before local use.'
    def add_arguments(self,parser):parser.add_argument('--reranker',action='store_true')
    def handle(self,**options):
        model_id,revision=identity(options['reranker'])
        root=Path(settings.SOURCE_SEARCH_CACHE)/('models--'+model_id.replace('/','--'))/'snapshots'/revision
        root.mkdir(parents=True,exist_ok=True)
        try:
            with urlopen(Request(f'https://huggingface.co/api/models/{model_id}/revision/{revision}?blobs=true',headers={'User-Agent':'MedWatch-Local-Model-Preparation'}),timeout=30) as response:
                metadata=json.load(response)
            if metadata['sha']!=revision:raise CommandError('고정 리비전 응답 불일치')
            files={item['rfilename']:item for item in metadata['siblings']}
            weight='model.safetensors' if 'model.safetensors' in files else 'pytorch_model.bin'
            wanted=['config.json','tokenizer_config.json','tokenizer.json','special_tokens_map.json','sentencepiece.bpe.model',weight]
            manifest={'model_id':model_id,'revision':revision,'files':{}}
            for name in wanted:
                if name not in files:continue
                item=files[name];expected=item.get('lfs',{}).get('sha256');size=item.get('size')
                path=root/name
                if path.exists() and (not size or path.stat().st_size==size):
                    digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
                    if expected and digest!=expected:path=None
                else:path=None
                if path is None:
                    path=root/name;partial=root/(name+'.partial');sha=hashlib.sha256()
                    self.stdout.write(f'Downloading {model_id}@{revision} / {name}');self.stdout.flush()
                    with urlopen(Request(f'https://huggingface.co/{model_id}/resolve/{revision}/{name}',headers={'User-Agent':'MedWatch-Local-Model-Preparation'}),timeout=60) as response,partial.open('wb') as target:
                        while block:=response.read(1024*1024):sha.update(block);target.write(block)
                    digest=sha.hexdigest()
                    if expected and digest!=expected:raise CommandError(f'모델 파일 SHA-256 불일치: {name}')
                    if size and partial.stat().st_size!=size:raise CommandError(f'모델 파일 크기 불일치: {name}')
                    os.replace(partial,path)
                manifest['files'][name]={'sha256':digest,'size':path.stat().st_size}
            if weight not in manifest['files'] or 'config.json' not in manifest['files']:raise CommandError('필수 모델 파일 없음')
            (root/'medwatch-model.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            self.stdout.write(str(root.resolve()))
        except CommandError:raise
        except Exception as exc:raise CommandError(f'모델 다운로드 실패 ({type(exc).__name__}); 검색에서는 키워드 대체 실행을 사용합니다.') from exc
