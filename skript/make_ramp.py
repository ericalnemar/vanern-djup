"""Skapar en djupskala för QGIS: färgskala för stilhanteraren (XML) och färdig rasterstil (QML)
för vanern_djup_25m.tif, samt en provbild. Körs med QGIS Python (python-qgis.bat)."""
import sys, os
from qgis.core import (QgsApplication, QgsGradientColorRamp, QgsGradientStop, QgsStyle, QgsRasterLayer,
                       QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer,
                       QgsMapSettings, QgsMapRendererParallelJob)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize

tif, outdir = sys.argv[1], sys.argv[2]
app = QgsApplication([], False); app.initQgis()

MAXD = 106.0
# djup (m) -> färg: ljust turkos i strandkanten, mörkt marinblått i de djupaste groparna
STOPS = [(0, '#e8f6fc'), (5, '#cbeaff'), (10, '#aadaf5'), (20, '#7dc3ec'), (30, '#54a8de'),
         (40, '#348acc'), (50, '#2371b5'), (60, '#1a5a9c'), (70, '#144684'), (80, '#10366c'),
         (90, '#0c2855'), (106, '#071a3c')]

ramp = QgsGradientColorRamp(QColor(STOPS[0][1]), QColor(STOPS[-1][1]), False,
                            [QgsGradientStop(d / MAXD, QColor(c)) for d, c in STOPS[1:-1]])
style = QgsStyle(); style.createMemoryDatabase()
style.addColorRamp('Vänern djup (0–106 m)', ramp, True)
style.tagSymbol(QgsStyle.ColorrampEntity, 'Vänern djup (0–106 m)', ['djup', 'bathymetry', 'vatten'])
ok = style.exportXml(os.path.join(outdir, 'vanern_djup_fargskala.xml'))
print('XML', ok)

layer = QgsRasterLayer(tif, 'Vänerns djup')
assert layer.isValid()
items = [QgsColorRampShader.ColorRampItem(d, QColor(c), f'{d:g} m') for d, c in STOPS]
crs = QgsColorRampShader(0, MAXD)
crs.setColorRampType(QgsColorRampShader.Interpolated)
crs.setSourceColorRamp(ramp.clone())
crs.setColorRampItemList(items)
crs.setClip(False)
shader = QgsRasterShader(); shader.setRasterShaderFunction(crs)
rend = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
rend.setClassificationMin(0); rend.setClassificationMax(MAXD)
layer.setRenderer(rend)
msg, ok = layer.saveNamedStyle(os.path.join(outdir, 'vanern_djup_25m.qml'))
print('QML', ok, msg)

# provbild
ms = QgsMapSettings(); ms.setLayers([layer]); ms.setDestinationCrs(layer.crs())
ms.setExtent(layer.extent()); ms.setOutputSize(QSize(700, 780)); ms.setBackgroundColor(QColor('#f2efe6'))
job = QgsMapRendererParallelJob(ms); job.start(); job.waitForFinished()
job.renderedImage().save(os.path.join(outdir, 'prov_fargskala.png'))

# läs tillbaka XML:en för kontroll
s2 = QgsStyle(); s2.createMemoryDatabase(); print('import', s2.importXml(os.path.join(outdir, 'vanern_djup_fargskala.xml')), s2.colorRampNames())
app.exitQgis()
