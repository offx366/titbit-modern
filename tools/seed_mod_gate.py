"""Owner-only private R2 seeding. Credentials are accepted on hidden stdin only.

No assets, admin keys or Sites service credentials enter source repositories.
"""
import argparse,getpass,hashlib,json,sys,urllib.request,urllib.parse,time
from pathlib import Path
import titbit_assets as assets

def main():
    p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True);a=p.parse_args()
    if not a.origin.startswith('https://'):raise ValueError('HTTPS required')
    print('Ready for private gateway credentials (hidden input).',flush=True)
    secret=json.loads(getpass.getpass(''))
    headers={'Authorization':'Bearer '+secret['admin']}
    if secret.get('service'):headers['OAI-Sites-Authorization']='Bearer '+secret['service']
    def request(path,data=None):
        h=dict(headers)
        if data is not None:h['X-Chunk-SHA256']=hashlib.sha256(data).hexdigest()
        req=urllib.request.Request(a.origin+path,data=data,headers=h,method='GET'if data is None else'POST')
        with urllib.request.urlopen(req,timeout=180)as f:return json.load(f)
    assets.verify_install(a.data)
    status=request('/admin/status');verified={r['name']for r in status['objects']if r['verified']}
    for name,path in [(n,a.data/n)for n in assets.manifest()]+[('mod',a.package)]:
        if name in verified:print('Already verified:',name,flush=True);continue
        endpoint='/admin/objects/'+urllib.parse.quote(name,safe='')
        with path.open('rb')as file:
            i=0
            while chunk:=file.read(8*1024*1024):
                for retry in range(3):
                    try:request(endpoint+'/part?index='+str(i),chunk);break
                    except Exception:
                        if retry==2:raise
                        time.sleep(1+retry)
                i+=1
        result=request(endpoint+'/commit',b'{}')
        if not result.get('verified'):raise RuntimeError('Reference verification failed')
        print('Privately stored and verified:',name,path.stat().st_size,flush=True)
    print(json.dumps(request('/admin/status')),flush=True)
if __name__=='__main__':main()
