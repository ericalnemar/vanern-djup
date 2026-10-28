"""Väljer ut Lantmäteriets vattenytor som hör till Vänern (minst hälften av ytan har djupvärde)
och fyller ut djupmodellen så att den täcker hela LM-ytan (närmaste värde, högst 1 km bort).
Ut: vanern_lm.geojson (EPSG:3006) och vanern_djup_25m_fylld.tif."""
import sys
import numpy as np
from osgeo import gdal, ogr, osr
gdal.UseExceptions(); ogr.UseExceptions()
work = sys.argv[1]
ds = gdal.Open(f'{work}/vanern_djup_25m.tif')
gt, proj = ds.GetGeoTransform(), ds.GetProjection()
depth = ds.GetRasterBand(1).ReadAsArray()
src = ogr.Open(f'{work}/lm_sjo.geojson'); lyr = src.GetLayer()
mem = gdal.GetDriverByName('MEM').Create('', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Int32)
mem.SetGeoTransform(gt); mem.SetProjection(proj)
# bränn in radnummer per objekt
mem.GetRasterBand(1).Fill(-1)
drv = ogr.GetDriverByName('Memory'); tmp = drv.CreateDataSource('t')
tl = tmp.CreateLayer('t', lyr.GetSpatialRef(), ogr.wkbMultiPolygon)
tl.CreateField(ogr.FieldDefn('k', ogr.OFTInteger))
feats = []
for i, f in enumerate(lyr):
    g = f.GetGeometryRef().Clone(); feats.append(g)
    nf = ogr.Feature(tl.GetLayerDefn()); nf.SetField('k', i); nf.SetGeometry(g); tl.CreateFeature(nf)
gdal.RasterizeLayer(mem, [1], tl, options=['ATTRIBUTE=k'])
lab = mem.GetRasterBand(1).ReadAsArray()
ok = lab >= 0
n = len(feats)
tot = np.bincount(lab[ok], minlength=n)
fin = np.bincount(lab[ok & np.isfinite(depth)], minlength=n)
keep = [i for i in range(n) if tot[i] >= 4 and fin[i] / tot[i] >= 0.5]
print('LM-ytor', n, 'Vänern-delar', len(keep), 'yta km2', round(sum(feats[i].GetArea() for i in keep) / 1e6, 1))
out = ogr.GetDriverByName('GeoJSON').CreateDataSource(f'{work}/vanern_lm.geojson')
ol = out.CreateLayer('vanern', lyr.GetSpatialRef(), ogr.wkbMultiPolygon)
for i in keep:
    nf = ogr.Feature(ol.GetLayerDefn()); nf.SetGeometry(feats[i]); ol.CreateFeature(nf)
out = None
# utfyllnad
fill = gdal.GetDriverByName('GTiff').CreateCopy(f'{work}/vanern_djup_25m_fylld.tif', ds, options=['COMPRESS=DEFLATE', 'PREDICTOR=3', 'TILED=YES'])
b = fill.GetRasterBand(1)
mask = gdal.GetDriverByName('MEM').Create('', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
mask.GetRasterBand(1).WriteArray(np.isfinite(depth).astype(np.uint8))
gdal.FillNodata(b, mask.GetRasterBand(1), maxSearchDist=40, smoothingIterations=0)
a = b.ReadAsArray()
inlm = np.isin(lab, keep)
print('LM-Vänern-celler', int(inlm.sum()), 'utan djup före', int((inlm & ~np.isfinite(depth)).sum()), 'efter', int((inlm & ~np.isfinite(a)).sum()))
fill = None
