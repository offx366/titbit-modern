import hashlib,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import titbit_gate as gate

class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.files={f'f{i}.avi':{'size':8192}for i in range(19)}
        for i,name in enumerate(self.files):(self.base/name).write_bytes(bytes([i])*8192)
        self.record={'sha256':'a'*64}
        self.c=dict(protocol=1,id='1'*64,nonce='2'*64,expires=int(time.time())+120,packageSha256='a'*64,
                    samples=[dict(name=n,offset=42,length=4096)for n in self.files])
        self.patch=patch.object(gate.assets,'manifest',return_value=self.files);self.patch.start();self.addCleanup(self.patch.stop)
    def test_answer_uses_file_bytes_and_fresh_nonce(self):
        a=gate.proof_digest(self.c,self.base,self.record);self.c['nonce']='3'*64
        self.assertNotEqual(a,gate.proof_digest(self.c,self.base,self.record));self.assertNotEqual(a,'a'*64)
    def test_unknown_path_and_out_of_bounds_samples_rejected(self):
        for key,value in [('name','../outside'),('offset',-1),('offset',8190),('length',999999)]:
            c=json.loads(json.dumps(self.c));c['samples'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):gate.proof_digest(c,self.base,self.record)
    def test_expired_or_incomplete_or_oversized_proof_rejected(self):
        for change in [{'expires':0},{'samples':self.c['samples'][:-1]},{'samples':self.c['samples']*5}]:
            with self.assertRaises(ValueError):gate.proof_digest({**self.c,**change},self.base,self.record)
    def test_origin_disallows_http_credentials_and_url_paths(self):
        for url in ['http://example.com','https://u:p@example.com','https://example.com/path','https://example.com?token=secret']:
            with self.assertRaises(ValueError):gate.origin_url(url)
        self.assertEqual(gate.origin_url('https://example.com/'),'https://example.com')
if __name__=='__main__':unittest.main()
