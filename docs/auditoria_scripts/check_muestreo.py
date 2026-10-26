"""Comprobación 3: muestreo en franjas con datos sintéticos de respuesta conocida."""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, LineString, Point, box
from src.calculo import muestreo as MU

OUT = "docs/auditoria_scripts/_trabajo/synth"; os.makedirs(OUT, exist_ok=True)
EPSG = 32618
# transectos sintéticos: P0 sobre y=0, tierra hacia +y (ux=0, uy=1), espaciado 100 m, x = 50, 150, ..., 950
n = 10
t = gpd.GeoDataFrame({"id_ivc": np.arange(1, n + 1), "x_p0": 50 + 100 * np.arange(n) + 500000.0, "y_p0": np.full(n, 1200000.0),
                      "ux": np.zeros(n), "uy": np.ones(n)}, geometry=[Point(500050 + 100 * i, 1200000) for i in range(n)], crs=f"EPSG:{EPSG}")

# --- ráster 1: z = y − y0 (gradiente de 1 m por metro en y), 5 m de resolución, nodata=-9999 en una franja
res = 5.0
x0, y1 = 499000.0, 1202000.0
W, H = 600, 800
tr = from_origin(x0, y1, res, res)
cols, rows = np.meshgrid(np.arange(W), np.arange(H))
xc = x0 + (cols + 0.5) * res; yc = y1 - (rows + 0.5) * res
z = (yc - 1200000.0).astype("float32")
z[(xc > 500300) & (xc < 500400)] = -9999  # transecto 4 (x 350..450 parcialmente) sin dato
ruta = f"{OUT}/dem.tif"
with rasterio.open(ruta, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs=f"EPSG:{EPSG}", transform=tr, nodata=-9999) as dst:
    dst.write(z, 1)

print("=== raster_estadistico ===")
med = MU.raster_estadistico(t, ruta, 0, 200, 100, "mediana", paso=10.0)
mea = MU.raster_estadistico(t, ruta, 0, 200, 100, "media", paso=10.0)
print("mediana franja 0-200 (esperado ≈100):", med.round(2).tolist())
print("media (esperado ≈100):", mea.round(2).tolist())
pct = MU.raster_estadistico(t, ruta, 0, 200, 100, "pct_bajo", umbral=50, paso=10.0)
print("pct_bajo 50 (esperado 25 %):", pct.round(2).tolist())
pnd = MU.raster_estadistico(t, ruta, 0, 200, 100, "pct_nodata", paso=10.0)
print("pct_nodata (transecto 4: franja x 350-450, nodata en 350-400 → 50 %):", pnd.round(1).tolist())
mx = MU.raster_estadistico(t, ruta, 0, 200, 100, "max", paso=10.0); mn = MU.raster_estadistico(t, ruta, 0, 200, 100, "min", paso=10.0)
print("min/max (esperado 2.5-7.5 / 192.5-197.5):", mn.round(1).tolist()[:3], mx.round(1).tolist()[:3])
print("¿-9999 se filtró? min de todos:", mn.min())
# comparación con zonal exacta (rasterio.mask) para transecto 1
from rasterio.mask import mask
fr = MU.franjas(t, 0, 200, 100)
with rasterio.open(ruta) as src:
    arr, _ = mask(src, [fr.geometry.iloc[0]], crop=True, all_touched=False, nodata=np.nan, filled=True)
vals = arr[0][np.isfinite(arr[0]) & (arr[0] != -9999)]
print("zonal exacta transecto 1: media", vals.mean().round(2), "mediana", np.median(vals).round(2), " n celdas", vals.size)

print("\n=== raster_pendiente ===")
pen = MU.raster_pendiente(t, ruta, 0, 200, 100, res=30.0)
print("pendiente (esperado 45°: dz/dy = 1):", pen.round(2).tolist())
# DEM con pendiente de 0.01 (0.573°) en x
z2 = ((xc - 499000.0) * 0.01).astype("float32"); ruta2 = f"{OUT}/dem2.tif"
with rasterio.open(ruta2, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs=f"EPSG:{EPSG}", transform=tr, nodata=-9999) as dst:
    dst.write(z2, 1)
print("pendiente 1 % (esperado 0.573°):", MU.raster_pendiente(t, ruta2, 0, 200, 100, res=30.0).round(3).tolist()[:3])

print("\n=== ráster en EPSG:4326 (reproyección) ===")
from pyproj import Transformer
tf = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)
lon0, lat1 = tf.transform(x0, y1); lon1, lat0 = tf.transform(x0 + W * res, y1 - H * res)
Wg, Hg = 600, 800
trg = from_origin(lon0, lat1, (lon1 - lon0) / Wg, (lat1 - lat0) / Hg)
cg, rg = np.meshgrid(np.arange(Wg), np.arange(Hg))
lonc = lon0 + (cg + 0.5) * trg.a; latc = lat1 + (rg + 0.5) * trg.e
tfi = Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
xm, ym = tfi.transform(lonc, latc)
zg = (ym - 1200000.0).astype("float32"); ruta3 = f"{OUT}/dem_geo.tif"
with rasterio.open(ruta3, "w", driver="GTiff", width=Wg, height=Hg, count=1, dtype="float32", crs="EPSG:4326", transform=trg, nodata=-9999) as dst:
    dst.write(zg, 1)
print("mediana con ráster geográfico (esperado ≈100):", MU.raster_estadistico(t, ruta3, 0, 200, 100, "mediana").round(2).tolist()[:4])
a3, t3, r3 = MU.raster_a_crs(ruta3, EPSG)
print("resolución deducida (deg*111000):", r3, " forma:", a3.shape)

print("\n=== vector_categorico / vector_numerico ===")
# polígonos: y 0..100 = 'A', y 100..200 = 'B' (50/50 en franja 0-200), excepto x<500100 solo A hasta 150
polys = gpd.GeoDataFrame({"cat": ["A", "B", "A", "B"], "val": [10.0, 30.0, 10.0, 30.0]},
                         geometry=[box(500000, 1200000, 500100, 1200150), box(500000, 1200150, 500100, 1200200),
                                   box(500100, 1200000, 501000, 1200100), box(500100, 1200100, 501000, 1200200)], crs=f"EPSG:{EPSG}")
tab, dom = MU.vector_categorico(t, polys, "cat", 0, 200, 100)
print(tab.head(3).to_string()); print("dominante:", dom.tolist()[:3], " (esperado A, luego empate A/B → idxmax = primero)")
print("media por área 'val' (esperado 15 para t1; 20 resto):", MU.vector_numerico(t, polys, "val", 0, 200, 100).round(3).tolist()[:3])
# polígono con solape (duplicación de área)
polys2 = pd.concat([polys, gpd.GeoDataFrame({"cat": ["C"], "val": [100.0]}, geometry=[box(500100, 1200000, 501000, 1200200)], crs=polys.crs)])
tab2, _ = MU.vector_categorico(t, polys2, "cat", 0, 200, 100)
print("con polígonos solapados: suma % transecto 2 =", tab2.drop(columns="sin_dato").iloc[1].sum(), " sin_dato:", tab2["sin_dato"].iloc[1], " <-- > 100 %")
# cobertura parcial: polígono que solo cubre 0-100
polys3 = polys[polys.cat == "A"]
tab3, dom3 = MU.vector_categorico(t, polys3, "cat", 0, 200, 100)
print("cobertura parcial t2: A", tab3["A"].iloc[1], " sin_dato", tab3["sin_dato"].iloc[1], " dominante:", dom3.iloc[1], " (A domina aunque 50 % sin dato)")
# excluir: la exclusión compara nombres sin normalizar
tabx, domx = MU.vector_categorico(t, polys, "cat", 0, 200, 100, excluir=("a",))
print("excluir ('a',) con categoría 'A' -> dominante:", domx.tolist()[:2], " (sensible a mayúsculas)")

print("\n=== distancia_a / mas_cercano ===")
via = gpd.GeoDataFrame({"tipo": ["primaria", "secundaria"]}, geometry=[LineString([(499000, 1200300), (502000, 1200300)]), LineString([(499000, 1200050), (502000, 1200050)])], crs=f"EPSG:{EPSG}")
print("distancia sin filtro (esperado 50):", MU.distancia_a(t, via).tolist()[:2], " con filtro tipo=='primaria' (esperado 300):", MU.distancia_a(t, via, "tipo == 'primaria'").tolist()[:2])
try:
    MU.distancia_a(t, via, "tipo == 'terciaria'")
except Exception as e:
    print("filtro sin entidades ->", type(e).__name__, e)
pts = gpd.GeoDataFrame({"v": [1.0, 2.0]}, geometry=[Point(500000, 1200000), Point(500600, 1200000)], crs=f"EPSG:{EPSG}")
print("mas_cercano (esperado 1,1,1,2,...):", MU.mas_cercano(t, pts, "v").tolist()[:6])

print("\n=== tabla_por_id ===")
pd.DataFrame({"id_ivc": [1, 2, 2, 3], "v": [1, 2, 3, 4]}).to_csv(f"{OUT}/dup.csv", index=False)
try:
    MU.tabla_por_id(t, f"{OUT}/dup.csv", "id_ivc", "v")
except Exception as e:
    print("ids duplicados ->", type(e).__name__, ":", e)
pd.DataFrame({"id_ivc": [1, 2, 3], "v": ["playa", "duna", "3"]}).to_csv(f"{OUT}/cat.csv", index=False)
print("columna mixta (2 texto, 1 número):", MU.tabla_por_id(t, f"{OUT}/cat.csv", "id_ivc", "v").tolist()[:3])
pd.DataFrame({"id_ivc": [1, 2, 3, 4], "v": ["1", "2", "x", "4"]}).to_csv(f"{OUT}/mix.csv", index=False)
print("columna 3 números + 1 texto -> numérica con NaN:", MU.tabla_por_id(t, f"{OUT}/mix.csv", "id_ivc", "v").tolist()[:4])

print("\n=== ancho_barra ===")
# DEM: tierra (z=1) de y 0..300 m, agua (nodata) a partir de 300 m; transecto 2: agua estrecha 150-180 (30 m < 60 m), tierra, luego agua desde 400
z4 = np.ones_like(z); z4[yc > 1200300] = -9999
z4[(xc > 500100) & (xc < 500200) & (yc > 1200150) & (yc < 1200180)] = -9999
z4[(xc > 500100) & (xc < 500200) & (yc > 1200300) & (yc < 1200400)] = 1  # tierra prolongada hasta 400
ruta4 = f"{OUT}/dem4.tif"
with rasterio.open(ruta4, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs=f"EPSG:{EPSG}", transform=tr, nodata=-9999) as dst:
    dst.write(z4, 1)
ab = MU.ancho_barra(t, dem=ruta4, rayo_max_m=3000, agua_continua_m=60, paso=10, res=5)
print(ab.head(4).to_string(), "\n(esperado: t1 ≈300, t2 ≈400 (ignora agua de 30 m), censura '')")
# P0 en el agua (mar): primeros 50 m nodata
z5 = z4.copy(); z5[yc < 1200050] = -9999; ruta5 = f"{OUT}/dem5.tif"
with rasterio.open(ruta5, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs=f"EPSG:{EPSG}", transform=tr, nodata=-9999) as dst:
    dst.write(z5, 1)
print("P0 50 m dentro del mar: ancho t1 =", MU.ancho_barra(t, dem=ruta5, rayo_max_m=3000, paso=10, res=5)["valor"].iloc[0], " (300 desde P0; 250 desde la orilla)")
