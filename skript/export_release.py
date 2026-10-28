"""Tar fram publiceringsfilerna: molnoptimerad GeoTIFF (COG) och 10 m-djupkurvor (GeoPackage)."""
import sys
from osgeo import gdal, ogr, osr
gdal.UseExceptions(); ogr.UseExceptions()
src, outdir = sys.argv[1], sys.argv[2]

gdal.Translate(f'{outdir}/vanern_djup_25m.tif', src, format='COG',
               creationOptions=['COMPRESS=DEFLATE', 'PREDICTOR=FLOATING_POINT', 'OVERVIEWS=AUTO', 'RESAMPLING=AVERAGE'])
ds = gdal.Open(f'{outdir}/vanern_djup_25m.tif')
st = ds.GetRasterBand(1).ComputeStatistics(False)
print('COG', ds.RasterXSize, ds.RasterYSize, 'min/max/medel', [round(v, 1) for v in st[:3]])

sr = osr.SpatialReference(); sr.ImportFromEPSG(3006)
out = ogr.GetDriverByName('GPKG').CreateDataSource(f'{outdir}/vanern_djupkurvor_10m.gpkg')
lyr = out.CreateLayer('djupkurvor', sr, ogr.wkbLineString)
lyr.CreateField(ogr.FieldDefn('id', ogr.OFTInteger))
f = ogr.FieldDefn('djup_m', ogr.OFTReal); lyr.CreateField(f)
gdal.ContourGenerateEx(ds.GetRasterBand(1), lyr, options=['FIXED_LEVELS=10,20,30,40,50,60,70,80,90,100',
                                                         'ID_FIELD=0', 'ELEV_FIELD=1'])
print('djupkurvor', lyr.GetFeatureCount())
out = None
