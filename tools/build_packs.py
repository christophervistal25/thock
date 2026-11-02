import json, os, shutil, subprocess, wave, numpy as np
SR=48000; SRC='/workspace/thock-src'; OUT=SRC+'/out/packs'
def load(f, denoise=False):
    af=['-af','afftdn=nr=18:nf=-50'] if denoise else []
    raw=subprocess.run(['ffmpeg','-v','error','-i',f,*af,'-ac','1','-ar',str(SR),'-f','f32le','-'],capture_output=True,check=True).stdout
    return np.frombuffer(raw,dtype=np.float32).astype(np.float64)
def env(x,ms=2):
    w=max(1,int(ms*SR/1000)); return np.sqrt(np.convolve(x**2,np.ones(w)/w,'same'))+1e-9
def finish(x, maxms=260):
    e=env(x); pk=e.max(); floor=np.percentile(e,10)
    # start: first point where env rises above 10% of peak, back off 1 ms
    i0=int(np.argmax(e>pk*0.2)); i0=max(0,i0-int(0.0015*SR))
    p=int(np.argmax(e))
    thr=max(floor*1.6,pk*0.012)
    tail=np.where(e[p:]>thr)[0]; i1=p+(tail[-1] if len(tail) else 0)+int(0.004*SR)
    i1=min(len(x),i1,i0+int(maxms*SR/1000))
    y=x[i0:i1].copy(); n=len(y)
    fi=min(int(0.0005*SR),n); y[:fi]*=np.linspace(0,1,fi)
    fo=min(int(0.012*SR),n//2); y[-fo:]*=np.linspace(1,0,fo)**2
    return y
def split_pair(x, min_gap_ms=45):
    e=env(x); pk=e.max(); p=int(np.argmax(e))
    a=p+int(min_gap_ms*SR/1000)
    if a>=len(x)-int(0.01*SR): return x,None
    q=a+int(np.argmax(e[a:]))
    lo=max(p+int(0.02*SR),q-int(0.07*SR)); hi=q-int(0.002*SR)
    if hi<=lo: return x,None
    m=lo+int(np.argmin(e[lo:hi]))
    if e[q]<pk*0.05 or e[m]>e[q]*0.55: return x,None
    return x[:m], x[m-int(0.001*SR):]
def groups(x, gap_ms=220, thr_rel=0.05):
    e=env(x,3); pk=np.percentile(e,99.9); act=e>pk*thr_rel
    idx=np.where(act)[0]; out=[]
    if not len(idx): return out
    s=idx[0]; last=idx[0]
    for i in idx[1:]:
        if (i-last)>gap_ms*SR/1000:
            out.append((s,last)); s=i
        last=i
    out.append((s,last))
    res=[]
    for s,t in out:
        s0=max(0,s-int(0.01*SR)); t0=min(len(x),t+int(0.12*SR))
        if (t-s)/SR<0.5: res.append(x[s0:t0])
    return res
def write(path,y,gain):
    y=np.clip(y*gain,-1,1); os.makedirs(os.path.dirname(path),exist_ok=True)
    with wave.open(path,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((y*32767).astype('<i2').tobytes())
def resamp(y,f):  # pitch-derived variant
    n=int(len(y)/f); return np.interp(np.arange(n)*f,np.arange(len(y)),y)
TARGET=0.5
def norm_gain(ys): return TARGET/max(np.abs(y).max() for y in ys if y is not None)
def main(): pass
if os.path.exists(OUT): shutil.rmtree(OUT)
fs=lambda n:f'{SRC}/fs/{n}.mp3'
report={}
def pairs_from(name, denoise=False, single=True, at=None, gap=45):
    x=load(fs(name),denoise)
    segs=[x] if single else groups(x)
    out=[]
    for s in segs:
        d,u=(s[:int(at*SR)],s[int(at*SR)-48:]) if at else split_pair(s,gap); out.append((finish(d), finish(u) if u is not None else None))
    return out
def save_pack(pid, meta, variants, special, mouse=None):
    allys=[y for d,u in variants for y in (d,u) if y is not None]+[y for d,u in special.values() for y in (d,u) if y is not None]
    g0=norm_gain([d for d,u in variants])
    pj=dict(meta); pj['default']=[]; pj['keys']={}
    for i,(d,u) in enumerate(variants):
        g=g0
        write(f'{OUT}/{pid}/v{i}-down.wav',d,g); ent={'down':f'v{i}-down.wav'}
        if u is not None: write(f'{OUT}/{pid}/v{i}-up.wav',u,g); ent['up']=f'v{i}-up.wav'
        pj['default'].append(ent)
    for code,(d,u) in special.items():
        g=TARGET*1.05/np.abs(d).max()
        write(f'{OUT}/{pid}/k{code}-down.wav',d,g); ent={'down':f'k{code}-down.wav'}
        if u is not None: write(f'{OUT}/{pid}/k{code}-up.wav',u,g); ent['up']=f'k{code}-up.wav'
        pj['keys'][str(code)]=ent
    json.dump(pj,open(f'{OUT}/{pid}/pack.json','w'),indent=1)
    report[pid]=dict(variants=[(len(d)/SR, None if u is None else len(u)/SR) for d,u in variants], special={k:(len(d)/SR,None if u is None else len(u)/SR) for k,(d,u) in special.items()})
SPACE,ENTER,BKSP=57,28,14
MODS=[42,54,29,97,56,100,15,58,125]
# 1 Buckling spring (bucklespring, GPL-2.0)
bdir=SRC+'/bucklespring/wav'; codes=sorted({f.split('-')[0] for f in os.listdir(bdir)})
data={}
for c in codes:
    if c=='ff': continue
    # bucklespring naming: XX-1.wav = key press, XX-0.wav = key release
    if not os.path.exists(f'{bdir}/{c}-1.wav'): continue
    d=finish(load(f'{bdir}/{c}-1.wav'),400); u=finish(load(f'{bdir}/{c}-0.wav'),400) if os.path.exists(f'{bdir}/{c}-0.wav') else None
    data[int(c,16)]=(d,u)
g=norm_gain([d for d,u in data.values()]); pj={'name':'Buckling Spring','description':'IBM Model M buckling-spring keyboard, every key sampled','default':[],'keys':{}}
for code,(d,u) in data.items():
    write(f'{OUT}/buckling/k{code}-down.wav',d,g); ent={'down':f'k{code}-down.wav'}
    if u is not None: write(f'{OUT}/buckling/k{code}-up.wav',u,g); ent['up']=f'k{code}-up.wav'
    pj['keys'][str(code)]=ent
pj['default']=[pj['keys'][str(c)] for c in (30,31,32,33,34,35,36,37,38)]  # fallback: home-row keys
json.dump(pj,open(f'{OUT}/buckling/pack.json','w'),indent=1); report['buckling']=f'{len(data)} keys'
# 2 Clicky Blue (Professor-Syntax MX Blue + UberBosser spacebar, CC0)
ps=pairs_from('523768')[0]; raw=load(fs('523768'))
pd,pu=split_pair(raw)
v=[ps]+[(finish(resamp(pd,f)),finish(resamp(pu,f))) for f in (1.035,0.97)]
big=(finish(resamp(pd,0.9)),finish(resamp(pu,0.92)))
sp=pairs_from('421582',True,at=0.09)[0]
special={SPACE:sp, ENTER:big, BKSP:big}; special.update({m:big for m in MODS})
save_pack('clicky-blue',{'name':'Clicky Blue','description':'Cherry MX Blue: sharp click on press, crisp release'},v,special)
# 3 Tactile Brown (Foxfire- press+release, Capt.Jack large key; CC0)
fd=finish(load(fs('570754'))); fu=finish(load(fs('570755')))
big=pairs_from('813210')[0]
variants=[(fd,fu),(finish(resamp(load(fs('570754')),1.04)),fu),(finish(resamp(load(fs('570754')),0.965)),fu)]
special={SPACE:big,ENTER:big,BKSP:big}
save_pack('tactile-brown',{'name':'Tactile Brown','description':'Cherry MX Brown, studio-clean press and release'},variants,special)
# 4 Soft Tactile (Xemptful, CC0)
xs=pairs_from('660387',False,False)
xs=[p for p in xs if p[1] is not None and len(p[1])/SR>0.05]
lowest=xs[0]
special={SPACE:(finish(resamp(lowest[0],0.88)),finish(resamp(lowest[1],0.9))),ENTER:(finish(resamp(xs[1][0],0.93)),finish(resamp(xs[1][1],0.95))),BKSP:(finish(resamp(xs[2][0],0.95)),xs[2][1])}
save_pack('soft-tactile',{'name':'Soft Tactile','description':'Softer, deeper tactile board with clear release'},xs,special)
# 5 Deep Clear (humi74 MX Clear, CC0)
hs=[p for p in pairs_from('412926',True,False) if p[1] is not None]
hs=[p for p in hs if 0.06<len(p[0])/SR<0.25 and len(p[1])/SR<0.25]
hs=sorted(hs,key=lambda p:-np.abs(p[0]).max())[:8]
special={SPACE:(finish(resamp(hs[0][0],0.9)),finish(resamp(hs[0][1],0.92)))}
save_pack('deep-clear',{'name':'Deep Clear','description':'Cherry MX Clear, stiff tactile, deeper thock'},hs,special)
# mouse (florianreichelt, CC0)
md,mu=split_pair(load(fs('683099')),22); md=finish(md); mu=finish(mu) if mu is not None else None
gm=0.42/np.abs(md).max()
write(f'{OUT}/_mouse/down.wav',md,gm)
if mu is not None: write(f'{OUT}/_mouse/up.wav',mu,gm)
report['mouse']=(len(md)/SR, None if mu is None else len(mu)/SR)
print(json.dumps(report,indent=0,default=str))
