"""Operator-invoked official HTML extraction. Search requests never fetch URLs."""
import hashlib
import re
from html.parser import HTMLParser
from django.db import transaction
from .search_models import EULegalTextVersion


class Paragraphs(HTMLParser):
    def __init__(self):super().__init__();self.blocks=[];self.active=None;self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','head'):self.skip+=1
        if not self.skip and tag=='p':self.active=[dict(attrs),[]]
        if self.active and tag=='br':self.active[1].append(' ')
    def handle_endtag(self,tag):
        if tag=='p' and self.active:
            attrs,data=self.active;body=re.sub(r'\s+',' ',''.join(data)).strip()
            if body:self.blocks.append((body,attrs.get('id','')))
            self.active=None
        if tag in ('script','style','head'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if self.active and not self.skip:self.active[1].append(data)


def extract_articles(raw,articles):
    parser=Paragraphs();parser.feed(raw.decode('utf-8-sig'))
    groups=[];current=None
    for text,anchor in parser.blocks:
        match=re.fullmatch(r'Article\s+(\d+)',text)
        if match:
            current=None
            if not articles or int(match[1]) in articles:
                current={'section':f'Article {match[1]}','anchor':anchor,'parts':[text]};groups.append(current)
        elif current:current['parts'].append(text)
    if not groups or articles and {int(group['section'].split()[-1]) for group in groups}!=set(articles):
        raise ValueError('요청한 조항의 공식 HTML 본문을 확인할 수 없습니다. 원문 링크 또는 수동 파일을 확인하세요.')
    # Stop at the next Article; never execute embedded links, scripts, or instructions.
    return [{'section':group['section'],'anchor':group['anchor'],'text':'\n\n'.join(group['parts'])} for group in groups]


def save_text(document,raw,articles):
    sections=extract_articles(raw,articles)
    text='\n\n'.join(group['text'] for group in sections)
    content_hash=hashlib.sha256(text.encode()).hexdigest()
    with transaction.atomic():
        type(document).objects.select_for_update().get(pk=document.pk)
        existing=EULegalTextVersion.objects.filter(document=document,content_hash=content_hash).first()
        if existing:return existing,False
        previous=EULegalTextVersion.objects.filter(document=document).order_by('-version').first()
        row=EULegalTextVersion.objects.create(document=document,version=previous.version+1 if previous else 1,text=text,
            content_hash=content_hash,original_hash=hashlib.sha256(raw).hexdigest(),official_url=document.official_url,
            sections=sections,scope_description='공식 HTML에서 추출한 '+', '.join(group['section'] for group in sections))
        return row,True
