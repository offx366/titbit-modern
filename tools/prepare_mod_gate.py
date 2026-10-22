"""Prepare a Sites Worker checkout. Only source + public metadata are copied."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('checkout',type=Path);a=p.parse_args();folder=a.checkout.resolve()
    manifest=folder/'.openai/hosting.json'
    if not manifest.is_file()or not json.loads(manifest.read_text()).get('project_id'):raise ValueError('Register and persist the Sites project first')
    files=json.loads((ROOT/'config/assets.json').read_text(encoding='utf8'))['files']
    catalog=json.loads((ROOT/'config/mods.json').read_text(encoding='utf8'))['mods']['widescreen']
    pack={k:catalog[k]for k in('version','size','sha256')};pack['id']='widescreen'
    code=(ROOT/'server/mod-gateway/gateway.mjs').read_text(encoding='utf8')
    code+='\nexport default createGateway('+json.dumps(files,sort_keys=True)+','+json.dumps(pack,sort_keys=True)+');\n'
    (folder/'worker/index.js').write_text(code,encoding='utf8')
    build="""import {mkdirSync,copyFileSync} from 'node:fs';
mkdirSync('dist/server',{recursive:true});mkdirSync('dist/.openai',{recursive:true});
copyFileSync('worker/index.js','dist/server/index.js');copyFileSync('.openai/hosting.json','dist/.openai/hosting.json');
console.log('Built private mod gateway');
"""
    (folder/'scripts/build.mjs').write_text(build,encoding='utf8')
    (folder/'README.md').write_text('Private R2 file availability gateway. No artwork or reference assets in source. Runtime secret: GATE_ADMIN_TOKEN. R2: BUCKET.\n',encoding='utf8')
    print('Prepared source-only gateway:',folder)
if __name__=='__main__':main()
