"""Klassar den skannade djupkartan i djupklasser (0-10, 10-20, ... 100-106 m) och land.
Rasterpunkterna (tryckrastret) jämnas ut med ett medelvärdesfilter. Referensfärgerna tas från
färgförklaringens rutor och från land/tätort. Pixlar som inte liknar någon klass (text, linjer,
kurvlinjer mellan klasserna) får närmaste klassade grannes värde. Arbetar i halv upplösning."""
import sys, json
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
Image.MAX_IMAGE_PIXELS = None

src, outdir = sys.argv[1], sys.argv[2]
img = np.asarray(Image.open(src).convert('RGB'), dtype=np.float32)
H, W, _ = img.shape
blur = np.stack([ndi.uniform_filter(img[..., c], size=13) for c in range(3)], axis=-1)

# Referensfärger, mätta i den utjämnade bilden (fullupplösningens pixelkoordinater)
LEG_X0, LEG_X1, LEG_Y0, LEG_STEP = 9040, 9280, 9567, 157.6
refs, names = [], []
for k in range(11):
    yc = int(LEG_Y0 + (k + 0.5) * LEG_STEP)
    refs.append(blur[yc - 40:yc + 40, LEG_X0:LEG_X1].reshape(-1, 3).mean(0)); names.append(k)
LAND = [(763, 3052), (1500, 7400), (10000, 3000), (6000, 11800)]   # orange land
TOWN = [(4880, 9930), (3330, 1870)]                                  # bruna tätorter (Lidköping, Karlstad-ish)
for (x, y) in LAND:
    refs.append(blur[y - 30:y + 30, x - 30:x + 30].reshape(-1, 3).mean(0)); names.append(-1)
for (x, y) in TOWN:
    refs.append(blur[y - 8:y + 8, x - 8:x + 8].reshape(-1, 3).mean(0)); names.append(-1)
refs = np.array(refs); names = np.array(names)
for n, r in zip(names, refs): print(n, r.round(1))

# Halv upplösning efter utjämning
b2 = blur[::2, ::2]
h2, w2, _ = b2.shape
d = np.stack([((b2 - r) ** 2).sum(-1) for r in refs], axis=0)
best = d.argmin(0)
dist = np.sqrt(d.min(0))
cls = names[best].astype(np.int8)          # -1 land, 0..10 djupklass
T = float(sys.argv[3]) if len(sys.argv) > 3 else 28.0
unknown = dist > T
print('okänd andel', unknown.mean().round(3))

# Utanför kartramen = ingen data (behandlas som land)
FRAME = (300, 330, 10380, 12020)   # x0, y0, x1, y1 i full upplösning, innanför ramens mönster
x0, y0, x1, y1 = [v // 2 for v in FRAME]
outside = np.ones_like(unknown); outside[y0:y1, x0:x1] = False
# Färgförklaringen och rubriken ligger på land och ska inte bli vatten
for (a, b_, c, e) in [(8900, 9400, 10380, 11500), (600, 700, 3700, 2700), (8900, 11500, 10380, 12020)]:
    outside[b_ // 2:e // 2, a // 2:c // 2] = True
cls[outside] = -1; unknown[outside] = False

# Fyll okända pixlar med närmaste klassade pixel
idx = ndi.distance_transform_edt(unknown, return_distances=False, return_indices=True)
cls = cls[idx[0], idx[1]]

# Majoritetsfilter mot brus (7x7)
counts = np.stack([ndi.uniform_filter((cls == k).astype(np.float32), size=7) for k in range(-1, 11)], 0)
cls = (counts.argmax(0) - 1).astype(np.int8)
np.save(f'{outdir}/classes_half.npy', cls)

pal = np.array([[245, 180, 120]] + [[255 - 22 * k, 255 - 15 * k, 255 - 5 * k] for k in range(11)], dtype=np.uint8)
Image.fromarray(pal[cls + 1]).resize((w2 // 4, h2 // 4), Image.NEAREST).save(f'{outdir}/classes_preview.png')
print('klassfördelning', {int(k): int((cls == k).sum()) for k in range(-1, 11)})
json.dump({'half_shape': [h2, w2], 'T': T}, open(f'{outdir}/classes_meta.json', 'w'))
