"""Redraws the Learjet model paint to approximate N722BD (white, black belly sweep, gold pinstripe, black fin, gold registration).
Usage: put the original Sketchfab textures in ./tex_orig/ and a copy of the model in ./model/, then run this file.
Also set the painted materials to non-metallic in scene.gltf (metallicFactor 0, baseColorFactor 1) - see CREDITS.md."""
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import numpy as np

from scipy import ndimage as ndi
_im=np.array(Image.open('tex_orig/material17_baseColor.jpeg').convert('RGB')).astype(int)
_bg=(abs(_im-np.array([101,103,110])).max(axis=2)<22)
for _n,(_a,_b) in {'top':(5,290),'bot':(735,1022)}.items():
    _l,_k=ndi.label(_bg[_a:_b]);_e=set(_l[0])|set(_l[-1])|set(_l[:,0])|set(_l[:,-1]);_e.discard(0)
    np.save(f'mask_{_n}.npy',ndi.binary_opening(~np.isin(_l,list(_e)),iterations=1))
O='tex_orig/';T='model/textures/'
WHITE=np.array([238,238,234]);BLACK=np.array([14,14,16]);GOLD=np.array([222,168,40])
def whiten(f,thr=75,soft=45,col=WHITE):
    im=np.array(Image.open(O+f).convert('RGB')).astype(float);lum=im.mean(axis=2)
    a=np.clip((thr-lum)/soft,0,1)[...,None]
    out=im*(1-a)+col*a;Image.fromarray(out.clip(0,255).astype('uint8')).save(T+f,quality=95)
whiten('material25_baseColor.jpeg');whiten('material39_baseColor.jpeg')
# nacelles: whiten black panels only on the left 3/4
im=np.array(Image.open(O+'material16_baseColor.jpeg').convert('RGB')).astype(float);lum=im.mean(axis=2)
a=np.clip((75-lum)/45,0,1);a[:,225:]=0;a=a[...,None];out=im*(1-a)+np.array([232,232,230])*a
Image.fromarray(out.clip(0,255).astype('uint8')).save(T+'material16_baseColor.jpeg',quality=95)
# fuselage atlas
src=Image.open(O+'material17_baseColor.jpeg').convert('RGB');A=np.array(src).astype(float)
out=A.copy()
# middle rectangles (fins, engine support, tall, purple) -> white
for (x0,y0,x1,y1) in [(502,311,725,465),(502,479,725,633),(759,311,981,465),(759,479,981,633),(165,311,352,708),(358,548,494,684)]:
    blk=A[y0:y1,x0:x1].mean(axis=2)<60; sub=out[y0:y1,x0:x1];sub[blk]=WHITE
def strip(name,y0,y1,nose_right,textbox,door):
    m=np.load(f'mask_{name}.npy');H,W=m.shape
    yy,xx=np.mgrid[0:H,0:W]
    ybot=np.array([ (np.where(m[:,x])[0].max() if m[:,x].any() else -1) for x in range(W)])
    u=(1020-np.arange(W))/830.0 if nose_right else (np.arange(W)-4)/830.0   # 0 nose .. 1 tail root
    u=np.clip(u,0,1.2)
    knots=[(0,.20),(.06,.27),(.15,.28),(.3,.19),(.5,.20),(.62,.25),(.74,.34),(.84,.48),(.9,.75),(.94,1.5),(2,1.5)]
    d=np.interp(u,[k[0] for k in knots],[k[1] for k in knots])*123
    yb=ybot[None,:]-d[None,:]
    canvas=np.zeros((H,W,3));canvas[:]=WHITE
    black=yy>=yb
    gold=(yy<yb-6)&(yy>=yb-10)&(u[None,:]<0.9)
    thin=(yy<yb-14)&(yy>=yb-16)&(u[None,:]<0.9)&(u[None,:]>0.30)
    canvas[black]=BLACK;canvas[gold]=GOLD;canvas[thin]=BLACK
    # fin + tail cone black: region beyond u>0.88 handled by d; make everything above body top in fin zone black
    finzone=(u[None,:]>0.90)
    canvas[finzone&m]=BLACK
    # keep door/ windshield line work from the original
    sub=A[y0:y1].copy();lum=sub.mean(axis=2)
    keep=np.zeros((H,W),bool)
    for (x0,ya,x1,yb2) in door: keep[ya-y0:yb2-y0,x0:x1]=True
    line=(lum>120)&(lum<250)&keep
    canvas[line]=np.array([120,120,124])
    # gold registration on the fin
    img=Image.fromarray(canvas.astype('uint8'))
    sh=Image.new('L',(W,H),0);d2=ImageDraw.Draw(sh)
    font=ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',textbox[4])
    d2.text((textbox[0],textbox[1]-y0),'N722BD',font=font,fill=255)
    gimg=Image.new('RGB',(W,H),tuple(GOLD));img.paste(gimg,(0,0),sh)
    res=np.array(img).astype(float);res[~m]=A[y0:y1][~m]   # keep grey background outside silhouette
    out[y0:y1]=res
strip('top',5,290,True,(60,126,0,0,28),[(522,164,570,236)])
strip('bot',735,1022,False,(856,855,0,0,28),[(238,893,284,998)])
Image.fromarray(out.clip(0,255).astype('uint8')).save(T+'material17_baseColor.jpeg',quality=95)
