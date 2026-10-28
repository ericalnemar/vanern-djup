"""Hittar koordinatnätets linjer (meridianer och parallellcirklar) i den skannade djupkartan.
Linjerna är tunna, grönaktiga och syns tydligast mot den orange landytan. För varje linje mäts
läget i block längs linjen och en rät linje anpassas robust (x = a + b*y respektive y = a + b*x)."""
import sys, json
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

src, out = sys.argv[1], sys.argv[2]
a = np.asarray(Image.open(src).convert('RGB'), dtype=np.int16)
R, G, B = a[..., 0], a[..., 1], a[..., 2]
H, W = R.shape
# Linjefärg: mörkare rött än orange land och vitt/ljusblått vatten, men inte svart text
line = (R < 150) & (G > 70) & (G > R + 5) & (B < G + 15)
print('bild', W, H, 'linjepixlar', int(line.sum()))
# Förväntade lägen (från gradmärkningen i ramen, uppmätt på en förminskad bild):
# meridianer 12°20' .. 14°00' var 20', parallellcirklar 59°20' .. 58°20' var 10'.
LON = [12 + 20/60, 12 + 40/60, 13.0, 13 + 20/60, 13 + 40/60, 14.0]
LAT = [59 + 20/60, 59 + 10/60, 59.0, 58 + 50/60, 58 + 40/60, 58 + 30/60, 58 + 20/60]
GUESS_X = [862, 2540, 4211, 5885, 7557, 9230]
GUESS_Y = [1946, 3570, 5213, 6825, 8430, 10035, 11637]

def peaks(profile, min_dist, k):
    p = profile.astype(float).copy()
    found = []
    for _ in range(k):
        i = int(p.argmax())
        if p[i] <= 0: break
        found.append(i)
        p[max(0, i - min_dist):i + min_dist] = 0
    return sorted(found)

# kartans innerområde (utan ram)
x0, x1, y0, y1 = 300, W - 300, 300, H - 450
inner = line[y0:y1, x0:x1]
def refine(guess, prof):
    lo = max(0, guess - 60)
    return lo + int(prof[lo:guess + 60].argmax())
vx = [refine(g, inner.sum(axis=0)) + 0 for g in [g - x0 for g in GUESS_X]]
hy = [refine(g, inner.sum(axis=1)) + 0 for g in [g - y0 for g in GUESS_Y]]
vx = [x + x0 for x in vx]; hy = [y + y0 for y in hy]
print('kandidater vertikala', vx, [int(line[y0:y1, x].sum()) for x in vx])
print('kandidater horisontella', hy, [int(line[y, x0:x1].sum()) for y in hy])

def fit(positions, along, get_slice):
    """positions: grovt läge; along: (start, stop) längs linjen; get_slice(p, lo, hi) -> profil tvärs linjen."""
    res = []
    for p in positions:
        pts = []
        for s in range(along[0], along[1], 150):
            prof = get_slice(p, s, s + 150)  # summa över blocket, index = offset -20..20
            if prof.max() < 40: continue
            off = int(prof.argmax()) - 20
            # sub-pixel tyngdpunkt
            idx = np.arange(prof.size) - 20
            w = prof * (np.abs(idx - off) <= 3)
            pts.append((s + 75, p + (w * idx).sum() / w.sum()))
        pts = np.array(pts)
        if len(pts) < 5:
            res.append(None); continue
        for _ in range(3):  # iterativ bortrensning av avvikare
            A = np.c_[np.ones(len(pts)), pts[:, 0]]
            coef, *_ = np.linalg.lstsq(A, pts[:, 1], rcond=None)
            r = pts[:, 1] - A @ coef
            keep = np.abs(r) < max(2.5, 2.5 * r.std())
            if keep.all(): break
            pts = pts[keep]
        res.append({'a': float(coef[0]), 'b': float(coef[1]), 'n': int(len(pts)), 'rms': float(r[keep].std())})
    return res

vfit = fit(vx, (y0, y1), lambda p, lo, hi: line[lo:hi, p - 20:p + 21].sum(axis=0))
hfit = fit(hy, (x0, x1), lambda p, lo, hi: line[p - 20:p + 21, lo:hi].sum(axis=1))
for p, f in zip(vx, vfit): print('V', p, f)
for p, f in zip(hy, hfit): print('H', p, f)
json.dump({'size': [W, H], 'vertical': [dict(f, guess=p, lon=L) for p, f, L in zip(vx, vfit, LON) if f],
           'horizontal': [dict(f, guess=p, lat=L) for p, f, L in zip(hy, hfit, LAT) if f]}, open(out, 'w'), indent=1)
