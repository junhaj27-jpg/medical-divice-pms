"""No inference endpoints, remote code, runtime downloads, or document-provided instructions."""
import math
import re
import json
import threading
from functools import lru_cache
from pathlib import Path
from django.conf import settings


class ModelUnavailable(RuntimeError):pass


def identity(reranker=False):
    model_id=settings.SOURCE_SEARCH_RERANKER_ID if reranker else settings.SOURCE_SEARCH_MODEL_ID
    revision=settings.SOURCE_SEARCH_RERANKER_REVISION if reranker else settings.SOURCE_SEARCH_REVISION
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',model_id) or not re.fullmatch('[a-f0-9]{40}',revision):
        raise ModelUnavailable('model_revision_invalid')
    return model_id,revision


def profile():return f'cls-l2:v1:{settings.SOURCE_SEARCH_MAX_TOKENS}'


def local_snapshot(model_id,revision):
    root=Path(settings.SOURCE_SEARCH_CACHE).resolve()
    folder=root/('models--'+model_id.replace('/','--'))/'snapshots'/revision
    try:
        manifest=json.loads((folder/'medwatch-model.json').read_text(encoding='utf-8'))
        if manifest['model_id']!=model_id or manifest['revision']!=revision:raise ValueError()
        for name,metadata in manifest['files'].items():
            if Path(name).name!=name or (folder/name).stat().st_size!=metadata['size']:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):raise ModelUnavailable('model_not_cached') from None
    return folder


def token_windows(tokens,budget,overlap=32):
    if budget<32:raise ModelUnavailable('token_budget_exceeded')
    step=max(1,budget-min(overlap,budget//4))
    for start in range(0,len(tokens) or 1,step):
        yield tokens[start:start+budget]
        if start+budget>=len(tokens):break


class LocalModel:
    def __init__(self,model_id,revision,cache,max_tokens,threads,device,reranker=False):
        # Resolve cache before importing optional ML packages; app and fallback need no torch.
        folder=local_snapshot(model_id,revision)
        try:
            import torch
            from transformers import AutoTokenizer,AutoModel,AutoModelForSequenceClassification
            torch.set_num_threads(max(1,threads))
            if device.startswith('cuda') and not torch.cuda.is_available():raise ModelUnavailable('device_unavailable')
            self.torch=torch;self.max_tokens=max_tokens;self.lock=threading.RLock()
            self.device=device
            self.tokenizer=AutoTokenizer.from_pretrained(str(folder),local_files_only=True,trust_remote_code=False)
            cls=AutoModelForSequenceClassification if reranker else AutoModel
            self.model=cls.from_pretrained(str(folder),local_files_only=True,trust_remote_code=False,weights_only=True)
            self.model.to(device);self.model.eval()
        except (ImportError,OSError,RuntimeError,ValueError) as exc:
            raise ModelUnavailable('model_load_failed') from exc

    def encode(self,texts):
        with self.lock,self.torch.inference_mode():
            lengths=self.tokenizer(texts,truncation=False,return_length=True)['length']
            if any(length>self.max_tokens for length in lengths):raise ModelUnavailable('token_budget_exceeded')
            inputs=self.tokenizer(texts,padding=True,truncation=False,return_tensors='pt').to(self.device)
            embeddings=self.model(**inputs).last_hidden_state[:,0]
            embeddings=self.torch.nn.functional.normalize(embeddings,p=2,dim=1)
            return embeddings.cpu().tolist()

    def rerank_with_info(self,query,texts):
        with self.lock:
            scores=self.rerank(query,texts)
            return scores,dict(self.last_rerank)

    def rerank(self,query,texts):
        with self.lock,self.torch.inference_mode():
            query_ids=self.tokenizer.encode(query,add_special_tokens=False)
            budget=self.max_tokens-len(query_ids)-self.tokenizer.num_special_tokens_to_add(pair=True)
            prepared=[];owners=[];counts=[]
            for owner,text in enumerate(texts):
                ids=self.tokenizer.encode(text,add_special_tokens=False);count=0
                for window in token_windows(ids,budget):
                    prepared.append(self.tokenizer.prepare_for_model(query_ids,pair_ids=window,add_special_tokens=True,truncation=False,return_attention_mask=True))
                    owners.append(owner);count+=1
                counts.append(count)
            scores=[float('-inf')]*len(texts);batch=max(1,min(settings.SOURCE_SEARCH_RERANK_BATCH_SIZE,8))
            for offset in range(0,len(prepared),batch):
                inputs=self.tokenizer.pad(prepared[offset:offset+batch],padding=True,return_tensors='pt').to(self.device)
                values=self.model(**inputs).logits.view(-1).float().cpu().tolist()
                for owner,value in zip(owners[offset:offset+batch],values):scores[owner]=max(scores[owner],value)
            self.last_rerank={'window_counts':counts,'truncated':False,'batch_size':batch,'device':self.device}
            return scores


@lru_cache(maxsize=2)
def _load(model_id,revision,cache,max_tokens,threads,device,reranker):
    return LocalModel(model_id,revision,cache,max_tokens,threads,device,reranker)


def load(reranker=False):
    model_id,revision=identity(reranker)
    return _load(model_id,revision,str(settings.SOURCE_SEARCH_CACHE),settings.SOURCE_SEARCH_MAX_TOKENS,settings.SOURCE_SEARCH_TORCH_THREADS,settings.SOURCE_SEARCH_DEVICE,reranker)


def valid_vector(vector,dimension=None):
    return (isinstance(vector,list) and len(vector)>0 and (dimension is None or len(vector)==dimension)
            and all(type(x) in (int,float) and math.isfinite(x) for x in vector)
            and abs(sum(x*x for x in vector)-1)<.02)
