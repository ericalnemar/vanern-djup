"""3D: sänker Vänerns botten i de befintliga terrängrutorna (terrarium-PNG, z12-16).

Steg 'prep':  djup för 3D = utfyllt djup, bara inom LM:s Vänern-ytor, och utjämnat mot 0 de sista
              1 500 m mot kommungränsen (terrängdatan slutar där, annars blir det en vägg).
              Skriver vanern_djup_3d.tif och tiles.json (de rutor som berör Vänern).
Steg 'apply': läser hämtade rutor (indir/z/x/y.png), drar av djupet och skriver till utdir.
Kör: python terrain3d.py prep <work>   |   python terrain3d.py apply <work> <indir> <utdir>"""
import sys, os, json, math
import numpy as np
from osgeo import gdal, ogr
from scipy import ndimage as ndi
from PIL import Image
gdal.UseExceptions(); ogr.UseExceptions()
WM = 20037508.342789244
TS = 256
TAPER_M = 1500.0

def tile_bounds(z, x, y):
    n = 2 ** z; s = 2 * WM / n
    return (x * s - WM, WM - (y + 1) * s, (x + 1) * s - WM, WM - y * s)

def rasterize(vec_path, like, burn=1, srs=None):
    m = gdal.GetDriverByName('MEM').Create('', like.RasterXSize, like.RasterYSize, 1, gdal.GDT_Byte)
    m.SetGeoTransform(like.GetGeoTransform()); m.SetProjection(like.GetProjection())
    v = gdal.VectorTranslate('', vec_path, format='Memory', dstSRS=like.GetProjection())
    gdal.RasterizeLayer(m, [1], v.GetLayer(), burn_values=[burn])
    return m.GetRasterBand(1).ReadAsArray().astype(bool)

mode, work = sys.argv[1], sys.argv[2]
if mode == 'prep':
    ds = gdal.Open(f'{work}/vanern_djup_25m_fylld.tif')
    d = ds.GetRasterBand(1).ReadAsArray()
    lake = rasterize(f'{work}/vanern_lm.geojson', ds)
    outside = rasterize(f'{work}/kommun-mask.geojson', ds)
    dist = ndi.distance_transform_edt(~outside) * ds.GetGeoTransform()[1]
    t = np.clip(dist / TAPER_M, 0, 1); taper = t * t * (3 - 2 * t)
    d3 = np.where(lake & np.isfinite(d), d, 0.0) * taper
    out = gdal.GetDriverByName('GTiff').CreateCopy(f'{work}/vanern_djup_3d.tif', ds, options=['COMPRESS=DEFLATE', 'PREDICTOR=3'])
    out.GetRasterBand(1).SetNoDataValue(-9999); out.GetRasterBand(1).WriteArray(d3.astype(np.float32)); out = None
    print('3D-djup max', float(d3.max()), 'celler > 0', int((d3 > 0).sum()))
    # rutor som berör sjön: rastrera sjön i rutnätet (en pixel per ruta), med marginal 1 ruta
    v = gdal.VectorTranslate('', f'{work}/vanern_lm.geojson', format='Memory', dstSRS='EPSG:3857')
    L, R, B, T = v.GetLayer().GetExtent()
    tiles = []
    for z in range(12, 17):
        n = 2 ** z; s = 2 * WM / n
        x0, x1 = int((L + WM) / s), int((R + WM) / s); y0, y1 = int((WM - T) / s), int((WM - B) / s)
        m = gdal.GetDriverByName('MEM').Create('', x1 - x0 + 1, y1 - y0 + 1, 1, gdal.GDT_Byte)
        m.SetGeoTransform((x0 * s - WM, s, 0, WM - y0 * s, 0, -s)); m.SetProjection(v.GetLayer().GetSpatialRef().ExportToWkt())
        gdal.RasterizeLayer(m, [1], v.GetLayer(), burn_values=[1], options=['ALL_TOUCHED=TRUE'])
        a = ndi.binary_dilation(m.GetRasterBand(1).ReadAsArray().astype(bool), iterations=1)
        ys, xs = np.where(a)
        tiles += [[z, int(x0 + i), int(y0 + j)] for j, i in zip(ys, xs)]
        print(f'z{z}: {len(xs)} rutor')
    json.dump(tiles, open(f'{work}/tiles.json', 'w'))
    print('totalt', len(tiles))
elif mode == 'apply':
    indir, outdir = sys.argv[3], sys.argv[4]
    ds = gdal.Open(f'{work}/vanern_djup_3d.tif')
    tiles = json.load(open(f'{work}/tiles.json'))
    done = changed = missing = 0; maxdrop = 0.0
    for z, x, y in tiles:
        p = os.path.join(indir, str(z), str(x), f'{y}.png')
        if not os.path.exists(p): missing += 1; continue
        rgb = np.asarray(Image.open(p).convert('RGB'), dtype=np.float64)
        elev = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
        w = gdal.Warp('', ds, format='MEM', dstSRS='EPSG:3857', outputBounds=tile_bounds(z, x, y), width=TS, height=TS,
                      resampleAlg='bilinear' if z >= 13 else 'average', srcNodata=-9999, dstNodata=0)
        dep = w.GetRasterBand(1).ReadAsArray().astype(np.float64); w = None
        done += 1
        if dep.max() <= 0.01: continue
        new = elev - dep
        v = new + 32768.0
        r = np.floor(v / 256.0); g = np.floor(v - r * 256.0); b = np.floor((v - np.floor(v)) * 256.0)
        enc = np.dstack([r, g, b]).clip(0, 255).astype(np.uint8)
        q = os.path.join(outdir, str(z), str(x)); os.makedirs(q, exist_ok=True)
        Image.fromarray(enc, 'RGB').save(os.path.join(q, f'{y}.png'), compress_level=6)
        changed += 1; maxdrop = max(maxdrop, float(dep.max()))
    print('lästa', done, 'ändrade', changed, 'saknades', missing, 'största sänkning', round(maxdrop, 1))
