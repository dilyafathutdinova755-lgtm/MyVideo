"""Процедурные SFX (лицензионно чисто) по точкам моушн-хитов, уровни — CLAUDE.md §4.5.2."""
import numpy as np, wave
SR=48000; DUR=14.98
rng=np.random.default_rng(7)
def pop():
    t=np.arange(int(.07*SR))/SR; f=900*np.exp(-t*40)+260
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*55)
def ping():
    t=np.arange(int(.45*SR))/SR
    return (np.sin(2*np.pi*1760*t)+.35*np.sin(2*np.pi*2640*t))/1.35*np.exp(-t*9)*np.minimum(1,t*400)
def whoosh():
    n=int(.32*SR); x=rng.standard_normal(n); t=np.arange(n)/n
    # простой резонансный фильтр с плавающей частотой
    y=np.zeros(n); a=0; b=0
    for i in range(n):
        f=.02+.10*np.sin(np.pi*t[i]); a+=f*(x[i]-a-b*.6); b+=f*a; y[i]=a
    return y/np.abs(y).max()*np.sin(np.pi*t)**2
out=np.zeros(int(DUR*SR)+SR)
def put(sig,t,lvl):
    s=sig/np.abs(sig).max()*lvl; i=int(t*SR); out[i:i+len(s)]+=s
def chime():
    t=np.arange(int(.7*SR))/SR
    return sum(np.sin(2*np.pi*f*t)*np.exp(-t*k) for f,k in ((1318,6),(1975,7),(2637,9)))*np.minimum(1,t*300)
for t in (1.62,3.96,6.66,8.16,9.84,11.10,12.78): put(pop(),t,.13)   # карточки
put(pop(),3.72,.12)       # глаза
put(ping(),8.46,.10)      # иконка приложения
put(ping(),13.92,.10)     # иконка ссылки
put(chime(),12.40,.13)    # замок открылся
for t in (1.86,2.72,6.94,13.62): put(whoosh(),t,.11)   # лист: вход и переворот, стрелки
out=out[:int(DUR*SR)]
st=np.repeat((out*32767).astype(np.int16)[:,None],2,1)
w=wave.open("sfx.wav","wb");w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(st.tobytes())
