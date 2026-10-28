"""Bygger QGIS-filerna i qgis/ ur djupmodellen och djupkurvorna i data/:
  vanern_djup_25m.qml        djupfärg 0–106 m med utjämnad läsning (inget rutnät när man zoomar in)
  vanern_djupkurvor_10m.qml  djupkurvor: tunna var 10:e m, tjockare var 50:e, utjämnade linjer,
                             diskreta djuptal utan halo, referensskala 1:10 000
  Vänerns djup.qlr           grupp med djupkurvor, skuggning (multiplicera) och djupfärg, relativa sökvägar
  Vänerns djup (GitHub).qlr  samma grupp, men lagren läses direkt från GitHub (/vsicurl/), så att det
                             räcker att ladda ner bara QLR-filen
Färgskalan tas från qgis/vanern_djup_fargskala.xml (skapas av make_ramp.py).
Körs med QGIS Python (python-qgis.bat). Kör: python skript/make_qgis_styles.py <förrådets rot> [provbild.png]"""
import sys, os
from qgis.core import (QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsHillshadeRenderer, QgsStyle,
                       QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer, QgsLayerTreeGroup,
                       QgsLayerDefinition, QgsMapSettings, QgsMapRendererParallelJob, QgsLineSymbol,
                       QgsSimpleLineSymbolLayer, QgsGeometryGeneratorSymbolLayer, QgsRuleBasedRenderer,
                       QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling, QgsProperty, Qgis)
from qgis.PyQt.QtGui import QColor, QPainter, QFont
from qgis.PyQt.QtCore import QSize

repo = sys.argv[1]
preview = sys.argv[2] if len(sys.argv) > 2 else None
app = QgsApplication([], False); app.initQgis()
proj = QgsProject.instance()
tif = os.path.join(repo, 'data', 'vanern_djup_25m.tif')
gpkg = os.path.join(repo, 'data', 'vanern_djupkurvor_10m.gpkg')
qgisdir = os.path.join(repo, 'qgis')
RAW = 'https://raw.githubusercontent.com/ericalnemar/vanern-djup/main/data'
MAXD = 106.0
STEPS = [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 106]


def smooth_reading(layer):
    """25 m-rutorna läses med kubisk utjämning när man zoomar in; annars ritar skuggningen
    en kant vid varje ruta (rutnätsmönster)."""
    p = layer.dataProvider()
    p.enableProviderResampling(True)
    p.setZoomedInResamplingMethod(p.ResamplingMethod.CubicSpline)
    p.setZoomedOutResamplingMethod(p.ResamplingMethod.Average)
    layer.setResamplingStage(Qgis.RasterResamplingStage.Provider)


# Djupfärg
style = QgsStyle(); style.createMemoryDatabase()
assert style.importXml(os.path.join(qgisdir, 'vanern_djup_fargskala.xml'))
ramp = style.colorRamp(style.colorRampNames()[0])
depth = QgsRasterLayer(tif, 'Djup (0–106 m)')
assert depth.isValid()
crs = QgsColorRampShader(0, MAXD, ramp.clone(), QgsColorRampShader.Interpolated)
crs.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, ramp.color(v / MAXD), f'{v:g} m') for v in STEPS])
shader = QgsRasterShader(); shader.setRasterShaderFunction(crs)
rend = QgsSingleBandPseudoColorRenderer(depth.dataProvider(), 1, shader)
rend.setClassificationMin(0); rend.setClassificationMax(MAXD)
depth.setRenderer(rend)
smooth_reading(depth)
print('rasterstil', depth.saveNamedStyle(os.path.join(qgisdir, 'vanern_djup_25m.qml'))[1])

def make_shade(source):
    """Skuggning: djupet är positivt nedåt, därför negativ höjdfaktor (annars blir reliefen inverterad)."""
    shade = QgsRasterLayer(source, 'Skuggning')
    assert shade.isValid(), source
    hs = QgsHillshadeRenderer(shade.dataProvider(), 1, 315, 40)
    hs.setZFactor(-3.0)
    hs.setMultiDirectional(True)
    shade.setRenderer(hs)
    shade.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
    shade.renderer().setOpacity(0.55)
    smooth_reading(shade)
    return shade


shade = make_shade(tif)


# Djupkurvor: kurvorna kommer ur ett 25 m-rutnät och jämnas därför ut vid ritning
def curve_symbol(width, color):
    line = QgsSimpleLineSymbolLayer(QColor(*color), width)
    line.setWidthUnit(Qgis.RenderUnit.Millimeters)
    gen = QgsGeometryGeneratorSymbolLayer.create({'geometryModifier': 'smooth($geometry, 3, 0.25)', 'SymbolType': 'Line'})
    gen.setSubSymbol(QgsLineSymbol([line]))
    return QgsLineSymbol([gen])


curves = QgsVectorLayer(f'{gpkg}|layername=djupkurvor', 'Djupkurvor 10 m', 'ogr')
assert curves.isValid()
root = QgsRuleBasedRenderer.Rule(None)
root.appendChild(QgsRuleBasedRenderer.Rule(curve_symbol(0.15, (50, 90, 140, 130)), 0, 0, '"djup_m" % 50 <> 0', 'Djupkurva 10 m'))
root.appendChild(QgsRuleBasedRenderer.Rule(curve_symbol(0.35, (30, 70, 125, 200)), 0, 0, '"djup_m" % 50 = 0', 'Djupkurva 50 m'))
renderer = QgsRuleBasedRenderer(root)
# Fast referensskala 1:10 000 (som Lantmäteriets Topografi 10): linjer och text krymper utzoomat
renderer.setReferenceScale(10000)
curves.setRenderer(renderer)

# Diskreta djuptal: små, dämpat blå, ingen halo, längs kurvan, bara på längre kurvor
pal = QgsPalLayerSettings()
pal.fieldName = 'format_number("djup_m", 0)'
pal.isExpression = True
pal.placement = Qgis.LabelPlacement.Curved
fmt = QgsTextFormat(); fmt.setFont(QFont('Open Sans')); fmt.setSize(6); fmt.setColor(QColor('#3d6f9f'))
fmt.setOpacity(0.8)
pal.setFormat(fmt)
pal.repeatDistance = 120; pal.repeatDistanceUnit = Qgis.RenderUnit.Millimeters
pal.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.Show, QgsProperty.fromExpression('$length > 2500'))
pal.scaleVisibility = True; pal.maximumScale = 1; pal.minimumScale = 60000
curves.setLabeling(QgsVectorLayerSimpleLabeling(pal)); curves.setLabelsEnabled(True)
print('kurvstil', curves.saveNamedStyle(os.path.join(qgisdir, 'vanern_djupkurvor_10m.qml'))[1])

def export_qlr(layers, path):
    for l in layers: proj.addMapLayer(l, False)
    group = QgsLayerTreeGroup('Vänerns djup')
    for l in layers: group.addLayer(l)
    print('QLR', os.path.basename(path), QgsLayerDefinition.exportLayerDefinition(path, [group]))


def check_qlr(path, image=None):
    """Provläsning i tom projektinstans (och provbild om den efterfrågas)."""
    proj.clear()
    ok, err = QgsLayerDefinition.loadLayerDefinition(path, proj, proj.layerTreeRoot())
    nodes = proj.layerTreeRoot().findLayers()
    print('inläst', os.path.basename(path), ok, err, [(n.name(), n.layer().isValid()) for n in nodes])
    if image:
        ms = QgsMapSettings(); ms.setLayers([n.layer() for n in nodes]); ms.setDestinationCrs(nodes[-1].layer().crs())
        ms.setBackgroundColor(QColor('#f2efe6')); ms.setExtent(nodes[-1].layer().extent()); ms.setOutputSize(QSize(700, 780))
        job = QgsMapRendererParallelJob(ms); job.start(); job.waitForFinished(); job.renderedImage().save(image)


# Lokal QLR (relativa sökvägar till data/)
qlr = os.path.join(qgisdir, 'Vänerns djup.qlr')
export_qlr([curves, shade, depth], qlr)
check_qlr(qlr, preview)

# GitHub-QLR: samma lager och stilar, men data läses direkt från GitHub. Djupmodellen är en
# molnoptimerad GeoTIFF, så bara de delar som syns hämtas.
proj.clear()
r_depth = QgsRasterLayer(f'/vsicurl/{RAW}/vanern_djup_25m.tif', 'Djup (0–106 m)')
assert r_depth.isValid()
r_depth.loadNamedStyle(os.path.join(qgisdir, 'vanern_djup_25m.qml'))
smooth_reading(r_depth)
r_shade = make_shade(f'/vsicurl/{RAW}/vanern_djup_25m.tif')
r_curves = QgsVectorLayer(f'/vsicurl/{RAW}/vanern_djupkurvor_10m.gpkg|layername=djupkurvor', 'Djupkurvor 10 m', 'ogr')
assert r_curves.isValid()
r_curves.loadNamedStyle(os.path.join(qgisdir, 'vanern_djupkurvor_10m.qml'))
remote = os.path.join(qgisdir, 'Vänerns djup (GitHub).qlr')
export_qlr([r_curves, r_shade, r_depth], remote)
check_qlr(remote)
app.exitQgis()
