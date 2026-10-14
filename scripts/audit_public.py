"""Audit Git's tracked snapshot/history against local private identifiers.

Prints counts and categories only, never matching values. Private inputs are
optional and remain local. This is a review aid, not a universal secret detector.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root',type=Path)
    parser.add_argument('--include-ignored',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    values=set()
    if args.private_root:
        for name in ('diagnostics/provisioned.json','diagnostics/discovery-current.json'):
            path=args.private_root/name
            if path.exists():
                for device in json.loads(path.read_text(encoding='utf-8')).get('devices',[]):
                    for field in ('device_id','mac','ip','product_id'):
                        if isinstance(device.get(field),str):values.add(device[field])
                    did=device.get('device_id')
                    if did:values.add(did[:6]+'…'+did[-4:])
                    pid=device.get('metadata',{}).get('product_id')
                    if isinstance(pid,str):values.add(pid)
    encoded=[value.encode() for value in values if value]
    path_pattern=re.compile(rb'[A-Za-z]:[\\/]Users[\\/][^\s"\r\n]+',re.I)
    def findings(data):
        return {'known_private_identifier': any(value in data for value in encoded),
            'absolute_user_path': bool(path_pattern.search(data))}
    names=[n for n in git('ls-files','-z').decode().split('\0') if n]
    tracked=[]
    for name in names:
        path=ROOT/name
        if path.is_file():
            result=findings(path.read_bytes())
            if any(result.values()):tracked.append({'path':name,'categories':[k for k,v in result.items() if v]})
    history=[]
    for line in git('rev-list','--objects','--all').decode().splitlines():
        sha=line.split(' ',1)[0]
        if git('cat-file','-t',sha).strip()!=b'blob':continue
        result=findings(git('cat-file','blob',sha))
        if any(result.values()):history.append({'object':sha,'categories':[k for k,v in result.items() if v]})
    ignored_scanned=ignored_flagged=0
    if args.include_ignored:
        for name in git('ls-files','--others','--ignored','--exclude-standard','-z').decode().split('\0'):
            path=ROOT/name
            if not name or not path.is_file():continue
            ignored_scanned+=1
            if any(findings(path.read_bytes()).values()) or path.suffix in ('.dpapi','.env'):ignored_flagged+=1
    report={'tracked_files':len(names),'tracked_findings':tracked,'history_findings':history,
        'ignored_files_scanned':ignored_scanned,'ignored_files_flagged':ignored_flagged,
        'private_values_never_printed':True,'history_safe_to_push':not history,
        'scope_note':'Exact local identifiers and absolute user paths; manual review and credential scan also required.'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'tracked_findings':len(tracked),'history_findings':len(history),
        'ignored_files_scanned':ignored_scanned,'ignored_files_flagged':ignored_flagged,
        'history_safe_to_push':not history}))
    return 1 if tracked or history else 0


if __name__=='__main__':raise SystemExit(main())
