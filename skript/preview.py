"""Förhandsbild av djupmodellen: djupfärg + terrängskuggning (för okulär kontroll)."""
import sys
import numpy as np
from osgeo import gdal
from PIL import Image
gdal.UseExceptions()
src, out = sys.argv[1], sys.argv[2]
step = int(sys.argv[3]) if len(sys.argv) > 3 else 4
win = [int(v) for v in sys.argv[4:8]] if len(sys.argv) > 7 else None   # x0 y0 w h (celler)
ds = gdal.Open(src); a = ds.GetRasterBand(1).ReadAsArray()
if win: a = a[win[1]:win[1] + win[3], win[0]:win[0] + win[2]]
a = a[::step, ::step]
res = ds.GetGeoTransform()[1] * step
water = np.isfinite(a)
z = -np.where(water, a, 0)
gy, gx = np.gradient(z * 6, res)            # 6x överdrivning
az, alt = np.radians(315), np.radians(45)
slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
t = np.clip(np.nan_to_num(a) / 100, 0, 1)[..., None]
light, deep = np.array([200, 230, 250]), np.array([10, 40, 110])
rgb = (light * (1 - t) + deep * t) * (0.55 + 0.45 * hs[..., None])
rgb[~water] = [235, 228, 210]
Image.fromarray(rgb.astype(np.uint8)).save(out)
print(a.shape)
