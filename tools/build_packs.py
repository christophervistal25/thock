import json, os, shutil, subprocess, sys, wave, numpy as np
SR=48000; SRC='/workspace/thock-src'; OUT=SRC+'/out/packs'
def load(f, denoise=False):
    nr=denoise if isinstance(denoise,(int,float)) and not isinstance(denoise,bool) else 18
    af=['-af',f'afftdn=nr={nr}:nf=-50,agate=threshold=0.004:ratio=3:attack=0.5:release=40'] if denoise else []
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
def save_pack(pid, meta, variants, special, mouse=None, per=False):
    allys=[y for d,u in variants for y in (d,u) if y is not None]+[y for d,u in special.values() for y in (d,u) if y is not None]
    g0=norm_gain([d for d,u in variants])
    pj=dict(meta); pj['default']=[]; pj['keys']={}
    for i,(d,u) in enumerate(variants):
        g=min(TARGET*0.95/np.abs(d).max(), g0*4) if per else g0
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
sp=(finish(resamp(pd,0.84)),finish(resamp(pu,0.86)))
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
hs=[p for p in pairs_from('412926',30,False) if p[1] is not None]
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

# ------------------------------------------------------------------ v2 packs (2026-11-03)
sys.path.insert(0, SRC)
from slicer import slice_dense
def dense_pack(name, denoise=False, n_down=8, n_up=6, region=None, maxms=150, clean=0.15):
    x=load(fs(name),denoise)
    if region: x=x[int(region[0]*SR):int(region[1]*SR)]
    sl=[c for c in slice_dense(x,maxms) if c['clean']<clean and c['len']>0.07]
    if not sl: raise SystemExit('no slices '+name)
    pk=np.array([c['peak'] for c in sl]); med=np.median(pk)
    downs=sorted([c for c in sl if c['peak']>=np.percentile(pk,55)], key=lambda c:c['clean'])[:n_down]
    dmed=np.median([c['peak'] for c in downs])
    ups=sorted([c for c in sl if 0.18*dmed<=c['peak']<=0.55*dmed], key=lambda c:c['clean'])[:n_up]
    D=[finish(x[c['s']:c['t']],maxms) for c in downs]
    U=[finish(x[c['s']:c['t']],100) for c in ups]
    return [(d, U[i%len(U)] if U else None) for i,d in enumerate(D)]
import sys as _s
# Linear: Keychron K10 (linear switches), Sadiquecat + Mediasaur, CC0
lin=[p for p in pairs_from('789628',False,False) if p[1] is not None]
lin=[p for p in lin if 0.05<len(p[0])/SR<0.26]
lin=sorted(lin,key=lambda p:-np.abs(p[0]).max())[:8]
lin.append(pairs_from('788932')[0])
ent=finish(load(fs('789629')),200); spc=finish(load(fs('789630')),220)
save_pack('linear',{'name':'Smooth Linear','description':'Keychron linear switches: smooth, even, rounded bottom-out'},lin,
          {SPACE:(spc,lin[0][1]),ENTER:(ent,lin[1][1]),BKSP:(ent,lin[1][1])},per=True)
# Box Jade: Kailh Box Jade, el_boss, CC0
bj_iso=[p for p in pairs_from('643558',False,False) if p[1] is not None and len(p[0])/SR>0.05][:4]
bj=bj_iso+dense_pack('643558',False,6,4,(4.5,10.3),clean=0.3)
save_pack('box-jade',{'name':'Box Jade','description':'Kailh Box Jade: thick, loud click bar, sharp and snappy'},bj,
          {SPACE:(finish(resamp(bj[0][0],0.86)),None if bj[0][1] is None else finish(resamp(bj[0][1],0.88))),
           ENTER:(finish(resamp(bj[1][0],0.92)),bj[1][1]),BKSP:(finish(resamp(bj[1][0],0.92)),bj[1][1])},per=True)
# Vintage Alps: Apple M0118 with ALPS SKCM Orange, robni7, CC0
al=dense_pack('680714',False,8,6)
save_pack('vintage-alps',{'name':'Vintage Alps','description':'1987 Apple keyboard, ALPS SKCM Orange: crunchy, dry, retro'},al,
          {SPACE:(finish(resamp(al[0][0],0.86)),al[0][1]),ENTER:(finish(resamp(al[1][0],0.92)),al[1][1])},per=True)
# Topre: HHKB Professional Hybrid, grcekh, CC0
tp=dense_pack('546164',22,8,6)
save_pack('topre',{'name':'Topre','description':'HHKB with Topre domes: muted, rounded, cushioned thock'},tp,
          {SPACE:(finish(resamp(tp[0][0],0.85)),tp[0][1]),ENTER:(finish(resamp(tp[1][0],0.92)),tp[1][1])},per=True)
# Typewriter: BryanSaraiva Typewriter Key Press 01-06 (CC-BY 4.0); spacebar: magedu (CC-BY 4.0)
tw=[]
for n in ('820348','820349','820350','820351','820352','820353'):
    x=load(fs(n)); d,u=split_pair(x,90)
    tw.append((finish(d,200), finish(u,140) if u is not None else None))
sp=[p for p in pairs_from('319944',False,False)]
sp=sorted(sp,key=lambda p:-np.abs(p[0]).max())
twsp=sp[0] if sp else (finish(resamp(tw[0][0],0.8)),None)
save_pack('typewriter',{'name':'Typewriter','description':'Vintage manual typewriter: dry wooden tick and typebar return'},tw,
          {SPACE:twsp,ENTER:(finish(resamp(tw[2][0],0.9),200),tw[2][1])})
# Laptop: MacBook Pro 2016 butterfly keys, kijjaz, CC0; spacebar: Apple keyboard, BockelSound, CC-BY 4.0
lp=dense_pack('407514',False,8,6,None,120)
asp=[p for p in pairs_from('489383',24,False) if p[1] is not None]
asp=sorted(asp,key=lambda p:-np.abs(p[0]).max())
lspace=asp[0] if asp else (finish(resamp(lp[0][0],0.85)),lp[0][1])
save_pack('laptop',{'name':'Laptop','description':'MacBook low-travel keys: quiet, flat, papery tap'},lp,
          {SPACE:lspace,ENTER:(finish(resamp(lp[1][0],0.93)),lp[1][1])},per=True)
print(json.dumps({k:(v if isinstance(v,str) else len(v.get('variants',[])) if isinstance(v,dict) else v) for k,v in report.items()},default=str))
