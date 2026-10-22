"""Anonymous file-possession challenge client. No service keys or asset uploads."""
from __future__ import annotations
import hashlib,json,os,re,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
import titbit_assets as assets

HEX=re.compile(r'^[a-f0-9]{64}$')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def origin_url(value):
    p=urllib.parse.urlsplit(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.path not in('','/') or p.query or p.fragment:
        raise ValueError('Шлюз должен быть HTTPS origin без пути или учётных данных')
    return value.rstrip('/')

def proof_digest(challenge,base,record):
    expected=assets.manifest();samples=challenge.get('samples')
    if (challenge.get('protocol')!=1 or not HEX.fullmatch(challenge.get('id','')) or
        not HEX.fullmatch(challenge.get('nonce','')) or challenge.get('packageSha256')!=record['sha256'] or
        not isinstance(challenge.get('expires'),int) or not time.time()-10<challenge['expires']<time.time()+360 or
        not isinstance(samples,list) or not 19<=len(samples)<=64):
        raise ValueError('Некорректный запрос проверки от сервера')
    if {s.get('name')for s in samples}!=set(expected):raise ValueError('Запрос должен проверять все 19 файлов игры')
    h=hashlib.sha256(f'titbit-possession-v1\n{challenge["id"]}\n{challenge["nonce"]}\n{record["sha256"]}\n'.encode())
    total=0
    for sample in samples:
        name=sample['name'];offset=sample.get('offset');length=sample.get('length')
        if (not isinstance(offset,int) or isinstance(offset,bool) or not isinstance(length,int) or isinstance(length,bool)
            or offset<0 or length!=min(4096,expected[name]['size']) or offset+length>expected[name]['size']):
            raise ValueError('Некорректные границы проверки файла')
        total+=length
        if total>256*1024:raise ValueError('Слишком большой запрос проверки')
        path=Path(base)/name
        if path.is_symlink():raise ValueError('Файл игры является ссылкой: '+name)
        with path.open('rb')as file:
            file.seek(offset);raw=file.read(length)
        if len(raw)!=length:raise ValueError('Файл игры изменился: '+name)
        h.update(f'{name}\0{offset}\0{length}\0'.encode());h.update(raw)
    return h.hexdigest()

def post(opener,url,data):
    request=urllib.request.Request(url,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','User-Agent':'TitbitLauncher/1.1'})
    try:
        with opener.open(request,timeout=60)as response:
            if response.url!=url:raise ValueError('Шлюз перенаправил запрос')
            raw=response.read(16385)
            if len(raw)>16384:raise ValueError('Слишком большой ответ шлюза')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code==429:raise ValueError('Слишком много проверок. Повторите через минуту.')from None
        if exc.code in(401,403):raise ValueError('Сервер не подтвердил файлы игры. Повторите проверку.')from None
        raise ValueError('Шлюз проверки недоступен (HTTP '+str(exc.code)+').')from None

def obtain(record,base,cache,progress=None,cancel=None):
    assets.verify_install(base,progress,cancel)
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    size,checksum=record['size'],record['sha256']
    if not HEX.fullmatch(checksum) or not isinstance(size,int)or not 0<size<180*1024*1024:raise ValueError('Некорректный каталог мода')
    target=cache/(checksum+'.titbitmod')
    if target.is_file()and target.stat().st_size==size and assets.hash_file(target,cancel=cancel)==checksum:return target
    origin=origin_url(record.get('gateway',''));opener=urllib.request.build_opener(NoRedirect())
    if progress:progress('Серверная проверка наличия оригинальных файлов',0,0)
    assets.check_cancel(cancel)
    challenge=post(opener,origin+'/v1/challenge',dict(mod='widescreen',version=record['version']))
    digest=proof_digest(challenge,base,record)
    assets.check_cancel(cancel)
    ticket=post(opener,origin+'/v1/prove',dict(id=challenge['id'],proof=digest))
    if (not HEX.fullmatch(ticket.get('token',''))or ticket.get('sha256')!=checksum or ticket.get('size')!=size or
        not isinstance(ticket.get('expires'),int)or not time.time()-10<ticket['expires']<time.time()+300):raise ValueError('Некорректный доступ к пакету')
    assets.check_cancel(cancel)
    partial=cache/(checksum+'.partial')
    try:
        request=urllib.request.Request(origin+'/v1/download',headers={'Authorization':'Bearer '+ticket['token'],'User-Agent':'TitbitLauncher/1.1'})
        with opener.open(request,timeout=60)as response,partial.open('wb')as output:
            if response.url!=origin+'/v1/download':raise ValueError('Перенаправление скачивания запрещено')
            if response.headers.get('Content-Length')and int(response.headers['Content-Length'])!=size:raise ValueError('Размер ответа не совпал с каталогом')
            done=0;digest=hashlib.sha256()
            while chunk:=response.read(256*1024):
                assets.check_cancel(cancel);done+=len(chunk)
                if done>size:raise ValueError('Сервер прислал слишком большой пакет')
                output.write(chunk);digest.update(chunk)
                if progress:progress('Закрытое скачивание готовых widescreen-фонов',done,size)
        if done!=size or digest.hexdigest()!=checksum:raise ValueError('Пакет не прошёл проверку SHA256')
        assets.check_cancel(cancel);os.replace(partial,target)
        return target
    finally:partial.unlink(missing_ok=True)
