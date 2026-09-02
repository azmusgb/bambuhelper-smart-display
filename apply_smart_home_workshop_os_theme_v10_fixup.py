#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

class PatchError(RuntimeError):
    pass

def remove_second_function(text: str, signature: str) -> str:
    starts=[]
    pos=0
    while True:
        i=text.find(signature,pos)
        if i<0: break
        starts.append(i); pos=i+len(signature)
    if len(starts)!=2:
        raise PatchError(f'{signature}: expected 2 definitions before fixup, found {len(starts)}')
    start=starts[1]
    brace=text.find('{',start)
    if brace<0: raise PatchError('second uiActionButton opening brace missing')
    depth=0; end=None
    for i in range(brace,len(text)):
        c=text[i]
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0:
                end=i+1
                break
    if end is None: raise PatchError('second uiActionButton closing brace missing')
    while end<len(text) and text[end] in ' \t': end+=1
    if end<len(text) and text[end]=='\n': end+=1
    return text[:start]+text[end:]

def apply(repo: Path) -> None:
    p=repo/'src'/'smart_hub.cpp'
    text=p.read_text()
    text=remove_second_function(text,'static void uiActionButton(')
    if text.count('static void uiActionButton(')!=1:
        raise PatchError('uiActionButton deduplication failed')
    # Make sure the retained definition is the v10 one.
    a=text.index('static void uiActionButton(')
    b=text.find('\nstatic void ',a+1)
    body=text[a:b if b>0 else len(text)]
    for needle in ['primary=filled || accent==UI_ORANGE','UI_PANEL_2','UI_GLOW']:
        if needle not in body: raise PatchError('retained action theme missing: '+needle)
    p.write_text(text)

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default='.'); ap.add_argument('--apply',action='store_true'); args=ap.parse_args()
    if not args.apply:
        print('Smart Home v10 theme compile fixup ready. Use --apply.'); return 0
    apply(Path(args.repo).resolve()); print('Smart Home v10 action-button dedupe applied'); return 0

if __name__=='__main__': raise SystemExit(main())
