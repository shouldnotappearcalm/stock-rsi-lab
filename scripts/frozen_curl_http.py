"""Exact-resource curl opener for the immutable HTTP journal; no implicit retry."""
from email.parser import Parser
from io import BytesIO
from pathlib import Path
import re
import subprocess
from urllib.error import URLError
from urllib.parse import urlencode,urlsplit

from scripts.immutable_http_capture import digest,file_sha,need,write_once


class CurlResponse(BytesIO):
    def __init__(self,body,status,url,headers):
        super().__init__(body);self.status=status;self.url=url;self.headers=headers


class FrozenCurlOpener:
    def __init__(self,root,resources,*,max_body_bytes,runner=subprocess.run):
        need(type(max_body_bytes) is int and max_body_bytes>0,'positive explicit transport body cap')
        self.root=Path(root);self.root.mkdir();self.maximum=max_body_bytes;self.runner=runner;self.allowed={};self.attempted=set()
        for name,r in resources.items():
            u=urlsplit(r['url']);need(u.scheme=='https' and u.hostname in ('www.cninfo.com.cn','static.cninfo.com.cn')
                and u.username is None and u.password is None and not u.fragment,'registered official HTTPS transport only')
            body=None if r['payload'] is None else urlencode(r['payload']).encode()
            need(r['method'] in ('GET','POST') and (body is None)==(r['method']=='GET'),'explicit method and payload')
            key=(r['method'],r['url'],body);need(key not in self.allowed,'duplicate logical transport identity')
            self.allowed[key]=(name,r)

    def __call__(self,request,timeout):
        need(timeout==20,'fixed20second source timeout')
        key=(request.get_method(),request.full_url,request.data)
        need(key in self.allowed and key not in self.attempted,'unregistered or already attempted transport resource')
        self.attempted.add(key);name,resource=self.allowed[key]
        folder=self.root/digest({'resource':name,'identity':resource});folder.mkdir()
        write_once(folder/'request.json',{'resource':name,**resource})
        args=['curl','--proto','=https','--max-redirs','0','--max-time','20','--connect-timeout','10',
            '--max-filesize',str(self.maximum),'--silent','--show-error',
            '--dump-header',str(folder/'headers.bin'),'--output',str(folder/'body.bin'),
            '--write-out','%{http_code}\n%{url_effective}','--request',resource['method'],
            '--header','User-Agent: Mozilla/5.0','--header','Referer: https://www.cninfo.com.cn/']
        if request.data is not None:args+=['--header','Content-Type: application/x-www-form-urlencoded','--data-binary','@-']
        args.append(resource['url']);original=None;response=None
        try:response=self.runner(args,input=request.data,capture_output=True,timeout=25)
        except BaseException as exc:original=exc
        stdout=(getattr(response,'stdout',None) if response is not None else getattr(original,'stdout',None)) or b''
        stderr=(getattr(response,'stderr',None) if response is not None else getattr(original,'stderr',None)) or b''
        (folder/'stdout.bin').write_bytes(stdout);(folder/'stderr.bin').write_bytes(stderr)
        write_once(folder/'transport.json',{'resource':name,'returncode':None if response is None else response.returncode,
            'original_error':None if original is None else {'type':type(original).__name__,'message':str(original)},
            'artifact_sha256':{p.name:file_sha(p) for p in folder.iterdir() if p.is_file()},
            'automatic_retries':0,'redirects_permitted':False})
        if original is not None:raise original
        if response.returncode!=0:raise URLError('curl transport code '+str(response.returncode)+': '+stderr.decode(errors='replace')[:1000])
        lines=stdout.decode().strip().splitlines()
        need_body=(folder/'body.bin').exists() and (folder/'headers.bin').exists()
        if not need_body or len(lines)!=2 or not re.fullmatch(r'\d{3}',lines[0]) or lines[1]!=request.full_url:
            raise URLError('curl final source identity/status/body invalid')
        body=(folder/'body.bin').read_bytes()
        if len(body)>self.maximum:raise URLError('curl body cap exceeded; original bytes retained')
        blocks=[v for v in re.split(r'\r?\n\r?\n',(folder/'headers.bin').read_text(encoding='iso8859-1')) if v.startswith('HTTP/')]
        if not blocks:raise URLError('curl final response headers absent')
        status=blocks[-1].splitlines()[0].split()
        if len(status)<2 or status[1]!=lines[0]:raise URLError('curl final header/status contradiction')
        headers=Parser().parsestr('\n'.join(blocks[-1].splitlines()[1:]))
        return CurlResponse(body,int(lines[0]),lines[1],headers)
