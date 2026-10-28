"""Bygger rasterrutor (RGBA PNG) med Vänerns djup: djupfärg + skuggning av sjöbotten.

Färgen räknas så att grunt vatten blir exakt stilens vattenfärg (#cbeaff) och djupare vatten
gradvis mörkare blått. Skuggningen räknas en gång per zoomnivå på hela området (inga skarvar).
Rutorna täcker bara Lantmäteriets vattenytor i Vänern (vanern_lm.geojson), så strandlinjen
följer Topografi 10 och inte den grövre djupkartan.
Kör: python build_tiles.py <djup_fylld.tif> <vanern_lm.geojson> <utmapp> [minzoom maxzoom]"""
import sys, os, math
import numpy as np
from osgeo import gdal, ogr
from PIL import Image
gdal.UseExceptions(); ogr.UseExceptions()

src, lmfile, out = sys.argv[1], sys.argv[2], sys.argv[3]
ZMIN, ZMAX = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (9, 15)
WM = 20037508.342789244
TS = 256
BASE = np.array([203, 234, 255], np.float32)   # vattnet i Topografi 10 ljus
DEEP = np.array([38, 92, 158], np.float32)
ZF = {9: 8, 10: 7, 11: 6, 12: 5, 13: 4, 14: 3.5, 15: 3}   # lodrät överdrift per zoom
ALT, AZ = math.radians(40), math.radians(335)

def res_of(z): return 2 * WM / (TS * 2 ** z)

ds = gdal.Open(src)
lm = gdal.VectorTranslate('', lmfile, format='Memory', dstSRS='EPSG:3857')
lyr = lm.GetLayer()
L, R, B, T = lyr.GetExtent()
total = 0
for z in range(ZMIN, ZMAX + 1):
    r = res_of(z); n = 2 ** z
    x0 = int((L + WM) / (2 * WM) * n); x1 = int((R + WM) / (2 * WM) * n)
    y0 = int((WM - T) / (2 * WM) * n); y1 = int((WM - B) / (2 * WM) * n)
    M = 2   # marginal (px) för gradienten
    bl = x0 * TS * r - WM - M * r; bt = WM - y0 * TS * r + M * r
    W_ = (x1 - x0 + 1) * TS + 2 * M; H_ = (y1 - y0 + 1) * TS + 2 * M
    bounds = (bl, bt - H_ * r, bl + W_ * r, bt)
    alg = 'average' if r > 25 else 'bilinear'
    m = gdal.Warp('', ds, format='MEM', dstSRS='EPSG:3857', outputBounds=bounds, width=W_, height=H_,
                  resampleAlg=alg, dstNodata=float('nan'))
    d = m.GetRasterBand(1).ReadAsArray().astype(np.float32); m = None
    # LM:s vattenyta som mask, rastrerad i 2x upplösning och medelvärdesbildad (mjuk kant)
    mk = gdal.GetDriverByName('MEM').Create('', W_ * 2, H_ * 2, 1, gdal.GDT_Byte)
    mk.SetGeoTransform((bounds[0], r / 2, 0, bounds[3], 0, -r / 2)); mk.SetProjection(lyr.GetSpatialRef().ExportToWkt())
    gdal.RasterizeLayer(mk, [1], lyr, burn_values=[255])
    mask = mk.GetRasterBand(1).ReadAsArray().astype(np.float32).reshape(H_, 2, W_, 2).mean((1, 3)); mk = None
    dz = np.where(np.isfinite(d), d, 0.0)
    zz = -dz * ZF[z]
    gy, gx = np.gradient(zz, r)
    slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    hs = np.sin(ALT) * np.cos(slope) + np.cos(ALT) * np.sin(slope) * np.cos(AZ - aspect)
    shade = np.clip(1 + 0.9 * (hs - math.sin(ALT)), 0.6, 1.25)
    t = np.clip(dz / 106.0, 0, 1) ** 0.8
    col = BASE * (1 - 0.85 * t[..., None]) + DEEP * (0.85 * t[..., None])
    col = np.clip(col * shade[..., None], 0, 255)
    rgba = np.dstack([col, mask]).astype(np.uint8)[M:-M, M:-M]
    cnt = 0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tile = rgba[(y - y0) * TS:(y - y0 + 1) * TS, (x - x0) * TS:(x - x0 + 1) * TS]
            if tile[..., 3].max() == 0: continue
            p = os.path.join(out, str(z), str(x)); os.makedirs(p, exist_ok=True)
            Image.fromarray(tile, 'RGBA').save(os.path.join(p, f'{y}.png'), optimize=True)
            cnt += 1
    total += cnt
    print(f'z{z}: {cnt} rutor', flush=True)
print('KLAR', total)
