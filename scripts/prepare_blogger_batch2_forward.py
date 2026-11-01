"""Only after development passes: append the already captured fixed2026 tail."""
import argparse,struct,json,shutil
from pathlib import Path
from scripts.prepare_blogger_etf_data import inventory,sha,write
from scripts.prepare_blogger_batch2_data import CODE,FIELDS

def prepare(development,previous_forward,out):
    if out.exists():raise ValueError('fresh output required')
    old=development/'provider';source=previous_forward/'provider';a=(old/'calendars/day.txt').read_text().splitlines();b=(source/'calendars/day.txt').read_text().splitlines()
    if a[0]!='2022-12-01' or a[-1]!='2025-12-31' or b[-1]!='2026-10-30':raise ValueError('fixed capped histories required')
    tail=[d for d in b if d>'2025-12-31'];dates=a+tail;cut=b.index(tail[0]);provider=out/'provider';provider.mkdir(parents=True);(provider/'calendars').mkdir();(provider/'instruments').mkdir()
    (provider/'calendars/day.txt').write_text('\n'.join(dates)+'\n');(provider/'calendars/day_future.txt').write_text('\n'.join(dates+['2026-11-02'])+'\n')
    if (source/'calendars/day_future.txt').read_text().splitlines()[-1]!='2026-11-02':raise ValueError('actual next clock session required')
    (provider/'instruments/all.txt').write_text(CODE+'\t'+dates[0]+'\t'+dates[-1]+'\n');folder=provider/'features'/CODE.lower();folder.mkdir(parents=True)
    for f in FIELDS:
        original=(old/'features'/CODE.lower()/(f+'.day.bin')).read_bytes();extended=(source/'features'/CODE.lower()/(f+'.day.bin')).read_bytes()
        # Both data views use the exact2023-07-03 normalization anchor.
        warm=a.index('2023-07-03');old_shared=original[4*(warm+1):];source_shared=extended[4:4*(cut+1)]
        if old_shared!=source_shared:raise ValueError('original price versions/normalization differ')
        blob=original+extended[4*(cut+1):]
        if len(blob)!=4*(len(dates)+1):raise ValueError('full actual quote tail required')
        (folder/(f+'.day.bin')).write_bytes(blob)
    write(provider/'manifest.json',{'end':'2026-10-30','all_output_sha256':inventory(provider),'all_development_feature_prefixes_identical':True})
    write(out/'preparation.json',{'development_data_root':str(development),'development_data_sha256':inventory(development),
        'source_2026_root':str(previous_forward),'source_2026_sha256':inventory(previous_forward),'2026_portfolio_returns_computed':False})

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('development-data','previous-forward','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();prepare(Path(a.development_data).resolve(),Path(a.previous_forward).resolve(),Path(a.out).resolve())
