"""List a remote zip via HTTP range requests; optionally extract one member.

Usage: python zip_range_extract.py URL [MEMBER OUT]
"""
import sys, io, zipfile, urllib.request
URL = sys.argv[1]
class HttpFile:
    def __init__(s, url):
        s.url=url; s.pos=0
        r=urllib.request.urlopen(urllib.request.Request(url, method='HEAD')); s.size=int(r.headers['Content-Length'])
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.pos
    def seek(s, off, wh=0):
        s.pos = off if wh==0 else (s.pos+off if wh==1 else s.size+off); return s.pos
    def read(s, n=-1):
        if n<0: n=s.size-s.pos
        if n==0 or s.pos>=s.size: return b''
        end=min(s.pos+n, s.size)-1
        req=urllib.request.Request(s.url, headers={'Range':f'bytes={s.pos}-{end}'})
        d=urllib.request.urlopen(req).read()
        if len(d) > end-s.pos+1: raise RuntimeError('range not honoured')
        s.pos+=len(d); return d
f=HttpFile(URL)
z=zipfile.ZipFile(f)
for i in z.infolist(): print(i.filename, i.file_size, i.compress_size, i.compress_type)
if len(sys.argv)>3:
    name, out = sys.argv[2], sys.argv[3]
    with z.open(name) as src, open(out,'wb') as dst:
        while True:
            b=src.read(1<<24)
            if not b: break
            dst.write(b)
    print('extracted', name)
