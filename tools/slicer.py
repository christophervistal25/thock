import numpy as np, sys
sys.argv=[sys.argv[0]]
SR=48000
def env(x,ms=2):
    w=max(1,int(ms*SR/1000)); return np.sqrt(np.convolve(x**2,np.ones(w)/w,'same'))+1e-9
def transients(x, min_rise_db=12, min_dist_ms=35, above_floor_db=18):
    e=env(x,1.5); floor=np.percentile(e,20)
    db=20*np.log10(e)
    lag=int(0.008*SR); d=int(min_dist_ms*SR/1000)
    rise=np.zeros_like(db); rise[lag:]=db[lag:]-db[:-lag]
    cand=np.where((rise>min_rise_db)&(e>floor*10**(above_floor_db/20)))[0]
    ons=[]
    i=0
    while i<len(cand):
        j=cand[i]
        # peak within 6ms after the rise
        seg=e[j:j+int(0.006*SR)]; p=j+int(np.argmax(seg))
        if not ons or p-ons[-1]>d: ons.append(p)
        while i<len(cand) and cand[i]<p+d: i+=1
    return ons, e, floor
def slice_dense(x, maxms=150, pre_ms=3):
    ons,e,floor=transients(x)
    out=[]
    for k,p in enumerate(ons):
        nxt=ons[k+1] if k+1<len(ons) else len(x)
        s=max(0,p-int(pre_ms*SR/1000)-int(0.004*SR)); t=min(nxt-int(0.004*SR), p+int(maxms*SR/1000))
        # stop before any later transient that rivals this one
        a=p+int(0.012*SR)
        if a<t:
            later=np.where(e[a:t]>0.45*e[p])[0]
            if len(later):
                t=a+int(later[0])-int(0.003*SR)
        if t-s<int(0.045*SR): continue
        pre=e[max(0,p-int(0.04*SR)):max(1,p-int(0.006*SR))]
        clean=float(pre.max()/e[p]) if len(pre) else 1.0
        out.append(dict(p=p,s=s,t=t,peak=float(e[p]),clean=clean,len=(t-s)/SR))
    return out
