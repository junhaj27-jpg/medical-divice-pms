"""Bounded official retrieval and explicit file imports. No source is published here."""
import hashlib,io,json,re,time,uuid
from datetime import datetime,timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit,urljoin,urlencode
from urllib.request import Request,urlopen,HTTPRedirectHandler,build_opener
from django.conf import settings
from django.db import connection,transaction
from django.utils import timezone
from pypdf import PdfReader
from .eu_legal import normalize_source
from .eu_search_text import extract_articles
from .search_models import EULegalTextVersion,EUSourceAttempt
from .market_service import require_workspace,eu_access
from .services import audit

MAX_BYTES=20*1024*1024
HOSTS={'eur-lex.europa.eu','op.europa.eu','publications.europa.eu'}

class AcquisitionError(ValueError):
    def __init__(self,status,detail):self.status=status;super().__init__(detail)

def official_url(url):
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.hostname not in HOSTS or parts.username or parts.password or parts.port not in (None,443):
        raise AcquisitionError('INVALID_URL','공식 HTTPS 호스트만 허용합니다.')
    return url

class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        official_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_official(url,headers=None):
    official_url(url)
    return build_opener(OfficialRedirect).open(Request(url,headers={'User-Agent':'MedWatch-Public-Source-Search/2.0',**(headers or {})}),timeout=25)

def lock_document(document):
    # First statement reserves a SQLite writer; PostgreSQL uses the existing source row lock.
    if connection.vendor=='sqlite':
        table=connection.ops.quote_name(type(document)._meta.db_table)
        with connection.cursor() as cursor:cursor.execute(f'UPDATE {table} SET id=id WHERE id=%s',[document.pk])
    else:type(document).objects.select_for_update().get(pk=document.pk)

def retry_delay(value,attempt,now=None):
    if value:
        try:return max(0.,float(value))
        except ValueError:
            try:return max(0.,(parsedate_to_datetime(value)-(now or datetime.now(dt_timezone.utc))).total_seconds())
            except (ValueError,TypeError,OverflowError):pass
    return min(2.**(attempt-1),8.)

def identify(document,text,raw_format,html=''):
    celex=document.celex or document.identifier
    expected=re.fullmatch(r'([03])(\d{4})([RLD])(\d{4})(?:-(\d{8}))?',celex)
    if not expected:raise AcquisitionError('IDENTITY_MISMATCH','이 CELEX 형식의 자동 판본 검증은 지원하지 않습니다.')
    lang=document.language.lower()
    if lang!='en':raise AcquisitionError('LANGUAGE_MISMATCH','현재 공식 Article 추출은 영어 원문만 지원합니다. 다른 언어는 검사된 규정 문서로 등록하세요.')
    head=text[:22000];compact=re.sub(r'\s+','',head).upper()
    number=f'{expected[2]}/{int(expected[4])}'
    if raw_format=='pdf':
        first=re.search(r'(?:REGULATION|DIRECTIVE|DECISION)\((?:EU|EC)\)(\d{4}/\d+)',compact)
        if expected[1]=='3':
            if not first or first[1]!=number or re.search(r'0\d{4}[RLD]\d{4}[—–-]',compact):
                raise AcquisitionError('IDENTITY_MISMATCH','PDF의 법령 번호 또는 원문/통합본 판본이 등록 문서와 다릅니다.')
            if 'OFFICIALJOURNAL' not in compact:raise AcquisitionError('IDENTITY_MISMATCH','관보 게재 원문의 머리말을 확인할 수 없습니다.')
        else:
            if celex[:10] not in compact or not expected[5]:raise AcquisitionError('IDENTITY_MISMATCH','통합본 CELEX 판본을 확인할 수 없습니다.')
            stamp=datetime.strptime(expected[5],'%Y%m%d').strftime('%d.%m.%Y')
            if stamp not in head:raise AcquisitionError('IDENTITY_MISMATCH','통합본 기준일이 다릅니다.')
        if not re.search(r'\bEN\b',head):raise AcquisitionError('LANGUAGE_MISMATCH','영문 PDF의 EN 표지를 확인할 수 없습니다.')
    else:
        # Positive document and language evidence, not merely a linked CELEX in references.
        if not re.search(r'(?:Document\s*|["\'>\s])'+re.escape(celex)+r'(?:["<\s]|$)',html,re.I):
            raise AcquisitionError('IDENTITY_MISMATCH','HTML에서 일치하는 CELEX를 확인할 수 없습니다.')
        if not re.search(r'(?:lang\s*=\s*["\']en(?:-[A-Za-z]+)?["\']|content\s*=\s*["\']eng?["\'])',html,re.I):
            raise AcquisitionError('LANGUAGE_MISMATCH','HTML의 영문 언어 식별자가 없습니다.')
        if expected[1]=='3' and re.search(r'\b0'+expected[2]+expected[3]+expected[4]+r'-\d{8}\b',html):
            raise AcquisitionError('IDENTITY_MISMATCH','관보 원문 대신 통합본입니다.')
    return {'celex':celex,'language':lang,'version':celex,'format':raw_format,'identity_verified':True}

def parse_official(document,raw,articles):
    if not raw:raise AcquisitionError('EMPTY_BODY','응답 본문이 비었습니다.')
    if len(raw)>MAX_BYTES:raise AcquisitionError('BODY_TOO_LARGE','원문 크기 제한을 초과했습니다.')
    if raw.startswith(b'%PDF-'):
        try:
            reader=PdfReader(io.BytesIO(raw),strict=True)
            if reader.is_encrypted or len(reader.pages)>500:raise ValueError()
            pages=[p.extract_text() or '' for p in reader.pages]
        except Exception as exc:raise AcquisitionError('PDF_EXTRACTION_FAILED','PDF 추출 실패·암호화·페이지 제한') from exc
        if not any(p.strip() for p in pages):raise AcquisitionError('PDF_EXTRACTION_FAILED','텍스트가 없는 PDF입니다. OCR 후 공식 원문을 확인하세요.')
        verification=identify(document,'\n'.join(pages[:3]),'pdf')
        groups=[];current=None;current_article=None
        for page,text in enumerate(pages,1):
            # Only normalize the heading's kerning; retain the body's extracted words and raw PDF.
            text=re.sub(r'(?m)^\s*Ar\s*tic\s*le\s+(\d+)\s*$',r'Article \1',text)
            current=None
            for line in text.splitlines():
                heading=re.fullmatch(r'Article\s+(\d+)',line.strip())
                if heading:current_article=int(heading[1]);current=None
                if re.match(r'^\s*ANNEX\s+[IVX]+\b',line):current_article=None;current=None
                if current_article not in articles:continue
                if current is None:
                    current={'section':f'Article {current_article}','page':page,'anchor':'','parts':[]};groups.append(current)
                # Running OJ headers are not the substantive article text.
                if re.search(r'Official\s+Jour\s*nal',line):continue
                current['parts'].append(line)
        sections=[{**{k:v for k,v in g.items() if k!='parts'},'text':'\n'.join(g['parts']).strip()} for g in groups if g['parts']]
    else:
        try:html=raw.decode('utf-8-sig')
        except UnicodeError as exc:raise AcquisitionError('HTML_EXTRACTION_FAILED','UTF-8 HTML이 아닙니다.') from exc
        if re.search(r'captcha|access denied|request blocked|verify you are human|just a moment|enable javascript',html[:15000],re.I):
            raise AcquisitionError('BLOCKED_PAGE','안내·접근 차단 페이지입니다. 원문으로 저장하지 않습니다.')
        if re.search(r'temporarily unavailable|service unavailable|maintenance|please try again later',html[:15000],re.I) and not re.search(r'Article\s+\d+',html):
            raise AcquisitionError('NOTICE_PAGE','일시적 안내 페이지입니다. 원문으로 저장하지 않습니다.')
        verification=identify(document,re.sub('<[^>]+>',' ',html),'html',html)
        try:sections=extract_articles(raw,articles)
        except ValueError as exc:raise AcquisitionError('HTML_EXTRACTION_FAILED',str(exc)) from exc
    found={int(s['section'].split()[-1]) for s in sections}
    if found!=set(articles) or any(len(s['text'])<30 for s in sections):raise AcquisitionError('ARTICLE_EXTRACTION_FAILED','요청한 조항의 본문을 모두 확인할 수 없습니다.')
    return sections,verification

def stage_text(document,raw,articles,method,resolved_url):
    sections,verification=parse_official(document,raw,articles)
    text='\n\n'.join(s['text'] for s in sections);content_hash=hashlib.sha256(text.encode()).hexdigest()
    raw_hash=hashlib.sha256(raw).hexdigest();suffix='pdf' if raw.startswith(b'%PDF-') else 'html'
    relative=Path('eu_sources')/f'{raw_hash}.{suffix}';path=Path(settings.MEDIA_ROOT)/relative
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        partial=path.with_suffix('.'+uuid.uuid4().hex+'.partial');partial.write_bytes(raw);partial.replace(path)
    with transaction.atomic():
        lock_document(document)
        old=EULegalTextVersion.objects.filter(document=document,content_hash=content_hash).first()
        if old:return old,False
        last=EULegalTextVersion.objects.filter(document=document).order_by('-version').first()
        row=EULegalTextVersion.objects.create(document=document,version=(last.version+1 if last else 1),text=text,
            content_hash=content_hash,original_hash=raw_hash,official_url=document.official_url,sections=sections,
            scope_description=f'공식 {suffix.upper()} · '+', '.join(f'Article {n}' for n in articles),source_method=method,
            resolved_url=resolved_url,original_file=relative.as_posix(),verification=verification)
    return row,True

def discover_op_download(page,document):
    html=page.decode('utf-8','replace')
    if (document.celex or document.identifier) not in html:raise AcquisitionError('IDENTITY_MISMATCH','Publications Office 메타데이터의 CELEX가 다릅니다.')
    # Only links actually supplied by the official page; never fabricate a Cellar identifier.
    for uri in re.findall(r'data-uri=["\']([^"\']+)["\']',html):
        uri=unescape(uri)
        if f'language={document.language}' in uri and ('format=pdfa1a' in uri or 'format=pdf&' in uri):
            return official_url(urljoin('https://op.europa.eu',uri))
    raise AcquisitionError('NO_OFFICIAL_ALTERNATIVE','동일 언어의 공식 PDF 링크를 확인하지 못했습니다.')

def acquire(document,user,articles,*,input_file=None,source_url=None,op_page=None,max_attempts=3):
    require_workspace(user)
    if not eu_access(user):raise AcquisitionError('PERMISSION_DENIED','EU 접근 권한이 없습니다.')
    if not articles or len(set(articles))!=len(articles) or any(n<=0 for n in articles):raise AcquisitionError('INVALID_ARTICLES','조항 번호를 확인하세요.')
    run=uuid.uuid4();last_error=None
    def log(status,url,method,attempt=1,**kwargs):
        return EUSourceAttempt.objects.create(document=document,actor=user,run_id=run,url=url,method=method,status=status,attempt=attempt,**kwargs)
    def consume(raw,url,method,attempt=1,code=None,resolved=''):
        row,created=stage_text(document,raw,articles,method,resolved or url)
        log('SUCCESS',url,method,attempt,http_status=code,resolved_url=resolved or url,text_version=row,original_hash=row.original_hash,detail='새 본문·색인 대기' if created else '동일 본문 재사용')
        audit(user,'SOURCE_EU_STAGE',row,after={'version':row.version,'created':created,'method':method})
        return row,created
    if input_file:
        url=official_url(source_url or document.official_url);method='manual_pdf' if Path(input_file).suffix.lower()=='.pdf' else 'manual_html'
        try:
            with Path(input_file).open('rb') as file:raw=file.read(MAX_BYTES+1)
            if method=='manual_pdf' and not raw.startswith(b'%PDF-'):raise AcquisitionError('PDF_EXTRACTION_FAILED','PDF 파일 형식이 아닙니다.')
            return consume(raw,url,method)
        except Exception as exc:
            log(getattr(exc,'status','FILE_READ_FAILED'),url,method,detail=str(exc)[:500]);raise
    _,canonical,_=normalize_source(document.celex,document.official_url,document.language)
    pdf=canonical.replace('/TXT/','/TXT/PDF/')
    routes=[(canonical,'auto_html'),(pdf,'auto_pdf')]
    # CELEX content negotiation is the documented official fallback. Some environments return 404.
    routes.append((f'https://publications.europa.eu/resource/celex/{document.celex}','auto_cellar'))
    if op_page:
        official_url(op_page)
        if urlsplit(op_page).hostname!='op.europa.eu':raise AcquisitionError('INVALID_URL','OP 상세 페이지를 입력하세요.')
        try:
            with open_official(op_page) as response:body=response.read(MAX_BYTES+1)
            routes.append((discover_op_download(body,document),'auto_op_pdf'))
        except (AcquisitionError,URLError,TimeoutError,OSError) as exc:
            log(getattr(exc,'status','NETWORK_ERROR'),op_page,'op_discovery',detail=str(exc)[:500])
    for url,method in routes:
        for attempt in range(1,max(1,min(max_attempts,3))+1):
            retry=False;header=None;code=None;delay=0
            try:
                headers={'Accept':'application/pdf','Accept-Language':'eng'} if method=='auto_cellar' else {}
                with open_official(url,headers) as response:
                    code=response.status;header=response.headers.get('Retry-After');resolved=response.geturl();official_url(resolved)
                    raw=response.read(MAX_BYTES+1)
                if code==202:raise AcquisitionError('HTTP_202','HTTP 202: 본문 준비 미완료')
                if code!=200:raise AcquisitionError('HTTP_ERROR',f'HTTP {code}')
                return consume(raw,url,method,attempt,code,resolved)
            except HTTPError as exc:
                code=exc.code;header=exc.headers.get('Retry-After');last_error=AcquisitionError('HTTP_ERROR',f'HTTP {code}');retry=code in (408,429,500,502,503,504)
            except (URLError,TimeoutError,ConnectionError) as exc:last_error=AcquisitionError('NETWORK_ERROR',type(exc).__name__);retry=True
            except AcquisitionError as exc:last_error=exc;retry=exc.status in ('HTTP_202','EMPTY_BODY')
            if retry and attempt<max(1,min(max_attempts,3)):delay=retry_delay(header,attempt)
            deferred=delay>30
            log(last_error.status,url,method,attempt,http_status=code,wait_seconds=delay,
                detail=(str(last_error)+('; Retry-After 초과: 이 경로 재시도 보류' if deferred else ''))[:500])
            if not retry or deferred or attempt>=max_attempts:break
            time.sleep(delay)
    raise last_error or AcquisitionError('ACQUISITION_FAILED','공식 본문을 확보하지 못했습니다.')
