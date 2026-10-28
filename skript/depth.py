"""Gör om djupklasserna till ett kontinuerligt djup och georefererar till SWEREF 99 TM.

1. Behåll bara den största sammanhängande vattenytan (Vänern); öar blir land.
2. Rätta klassregioner som inte gränsar till en grannklass (text och symboler i sjön).
3. Djup inom klass k: 10k + 10 * dU / (dU + dD), där dU = avstånd till grundare klass/land och
   dD = avstånd till djupare klass (begränsat, så att lokala gropar inte blir för djupa).
4. Georeferering: koordinatnätets skärningspunkter (graticule.json) ger ett polynom
   (lon, Mercator-y) -> pixel. Varje cell i målrastret räknas om till lon/lat och samplas."""
import sys, json, math
import numpy as np
from scipy import ndimage as ndi
from osgeo import gdal, osr
from pyproj import Transformer

work = sys.argv[1]
RES = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
SHIFT_E = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0   # efterjustering (m) mot LM:s strandlinje
SHIFT_N = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
cls = np.load(f'{work}/classes_half.npy').astype(np.int16)
eight = np.ones((3, 3), bool)

# 1. största vattenytan
lab, n = ndi.label(cls >= 0, structure=eight)
sizes = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
main = 1 + int(np.argmax(sizes))
cls[(lab != main) & (cls >= 0)] = -1
print('vattenytor', n, 'största', int(sizes.max()))

# 2. klassregioner som saknar grannklass (k-1 eller k+1) får grannarnas vanligaste klass
for it in range(6):
    changed = 0
    for k in range(1, 11):
        lab_k, nk = ndi.label(cls == k, structure=eight)
        if nk == 0: continue
        ring = ndi.binary_dilation(cls == k, structure=eight) & (cls != k)
        ring_lab = ndi.grey_dilation(lab_k, footprint=eight)  # vilken region ringpixeln hör till
        ok = np.zeros(nk + 1, bool)
        for nb in (k - 1, k + 1):
            sel = ring & (cls == nb)
            ok[np.unique(ring_lab[sel])] = True
        bad = ~ok; bad[0] = False
        badmask = bad[lab_k]
        if not badmask.any(): continue
        # ersätt med närmaste pixel utanför de felaktiga regionerna
        idx = ndi.distance_transform_edt(badmask, return_distances=False, return_indices=True)
        cls = cls[idx[0], idx[1]]
        changed += int(badmask.sum())
    print('rättning', it, changed)
    if changed == 0: break

# 3. djup
water = cls >= 0
depth = np.full(cls.shape, np.nan, np.float32)
CAP = 40.0
for k in range(0, 11):
    m = cls == k
    if not m.any(): continue
    dU = ndi.distance_transform_edt(cls >= k)          # avstånd till pixel med klass < k (inkl. land)
    deeper = cls > k
    dD = ndi.distance_transform_edt(~deeper) if deeper.any() else np.full(cls.shape, CAP)
    dD = np.minimum(dD, CAP)
    lo, span = 10.0 * k, (6.0 if k == 10 else 10.0)
    depth[m] = (lo + span * dU / (dU + dD))[m]
# Spikfilter: små, orimligt djupa fläckar (hamnsymboler, text) jämfört med omgivningens median.
# Medianen räknas i fjärdedels upplösning (9x9 ≈ 0,8 km) för att gå snabbt.
q = np.where(water, depth, 0)[::4, ::4]
med = ndi.median_filter(q, size=9)
med = np.kron(med, np.ones((4, 4), np.float32))[:depth.shape[0], :depth.shape[1]]
spike = water & (depth > med + 15)
lab_s, ns = ndi.label(spike, structure=eight)
if ns:
    ssz = ndi.sum(np.ones_like(lab_s), lab_s, index=np.arange(1, ns + 1))
    small = np.zeros(ns + 1, bool); small[1:] = ssz < 1500
    fix = small[lab_s]
    depth[fix] = med[fix]
    print('spikar', ns, 'rättade pixlar', int(fix.sum()))
# lätt utjämning inom vattnet (normaliserad, så att stranden förblir 0 m)
w = water.astype(np.float32)
num = ndi.gaussian_filter(np.where(water, depth, 0), 1.5)
den = ndi.gaussian_filter(w, 1.5)
depth = np.where(water, num / np.maximum(den, 1e-6), np.nan).astype(np.float32)
print('djup max', float(np.nanmax(depth)), 'medel', float(np.nanmean(depth)))
np.save(f'{work}/depth_half.npy', depth)

# 4. georeferering
g = json.load(open(f'{work}/graticule.json'))
def merc(lat): return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
gcp = []
for v in g['vertical']:
    for h in g['horizontal']:
        # x = av + bv*y ; y = ah + bh*x
        y = (h['a'] + h['b'] * v['a']) / (1 - h['b'] * v['b'])
        x = v['a'] + v['b'] * y
        gcp.append((v['lon'], merc(h['lat']), x, y))
gcp = np.array(gcp)
def design(lon, my):
    lon = np.asarray(lon); my = np.asarray(my)
    return np.stack([np.ones_like(lon), lon, my, lon * my, lon ** 2, my ** 2], -1)
A = design(gcp[:, 0], gcp[:, 1])
cx, *_ = np.linalg.lstsq(A, gcp[:, 2], rcond=None)
cy, *_ = np.linalg.lstsq(A, gcp[:, 3], rcond=None)
rx = A @ cx - gcp[:, 2]; ry = A @ cy - gcp[:, 3]
print('GCP', len(gcp), 'rms px', float(np.sqrt((rx ** 2 + ry ** 2).mean())), 'max', float(np.hypot(rx, ry).max()))

to_ll = Transformer.from_crs(3006, 4326, always_xy=True)
to_tm = Transformer.from_crs(4326, 3006, always_xy=True)
e0, n0 = to_tm.transform(12.30, 58.33); e1, n1 = to_tm.transform(14.05, 59.40)
E0, N1 = math.floor(min(e0, e1) / RES) * RES, math.ceil(max(n0, n1) / RES) * RES
E1, N0 = math.ceil(max(e0, e1) / RES) * RES, math.floor(min(n0, n1) / RES) * RES
nx, ny = int((E1 - E0) / RES), int((N1 - N0) / RES)
ee, nn = np.meshgrid(E0 + (np.arange(nx) + 0.5) * RES - SHIFT_E, N1 - (np.arange(ny) + 0.5) * RES - SHIFT_N)
lon, lat = to_ll.transform(ee, nn)
my = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
D = design(lon, my)
px = (D @ cx) / 2.0; py = (D @ cy) / 2.0       # halv upplösning
h2, w2 = depth.shape
valid = (px >= 0) & (py >= 0) & (px < w2 - 1) & (py < h2 - 1)
out = np.full((ny, nx), np.nan, np.float32)
# bilinjär sampling, med närmaste granne nära strand (NaN)
x0 = np.clip(np.floor(px).astype(int), 0, w2 - 2); y0 = np.clip(np.floor(py).astype(int), 0, h2 - 2)
fx = px - x0; fy = py - y0
v00 = depth[y0, x0]; v10 = depth[y0, x0 + 1]; v01 = depth[y0 + 1, x0]; v11 = depth[y0 + 1, x0 + 1]
bil = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
near = depth[np.clip(np.rint(py).astype(int), 0, h2 - 1), np.clip(np.rint(px).astype(int), 0, w2 - 1)]
out = np.where(np.isnan(bil), near, bil)
out[~valid] = np.nan
drv = gdal.GetDriverByName('GTiff')
ds = drv.Create(f'{work}/vanern_djup_{int(RES)}m.tif', nx, ny, 1, gdal.GDT_Float32, ['COMPRESS=DEFLATE', 'PREDICTOR=3', 'TILED=YES'])
ds.SetGeoTransform((E0, RES, 0, N1, 0, -RES))
sr = osr.SpatialReference(); sr.ImportFromEPSG(3006); ds.SetProjection(sr.ExportToWkt())
b = ds.GetRasterBand(1); b.SetNoDataValue(float('nan')); b.WriteArray(out)
b.SetDescription('Djup i meter under medelvattenstånd')
ds.SetMetadata({'SOURCE': 'SMHI Vattenwebb (SVAR) 647666-129906, Liber Kartor 1977 djupkarta 1:180 000 (L. Håkanson), CC BY 4.0',
                'METHOD': 'Färgklassning av 10 m-djupklasser + avståndsinterpolering; georefererad mot kartans gradnät',
                'SHIFT_E_N': f'{SHIFT_E} {SHIFT_N}'})
ds = None
print('skrev', nx, ny, 'celler', int(np.isfinite(out).sum()), 'bbox', E0, N0, E1, N1)
