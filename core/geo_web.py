# -*- coding: utf-8 -*-
"""
core/geo_web.py
Prepara capas vectoriales GRANDES para mostrarlas en el navegador: simplifica geometrías,
redondea coordenadas y genera un GeoJSON compacto que se crea UNA vez y se reutiliza.

Por qué existe: la capa nacional de vulnerabilidad (8,702 polígonos, ~1.97 millones de vértices)
se convertía a ~45 MB de JSON y se incrustaba en el HTML en cada carga. Aquí se reduce antes.

Funciones principales
- optimizar_poligonos(gdf, columnas, tolerancia, decimales) -> (gdf_optimizado, estadísticas)
- asegurar_geojson_web(fuente, destino, columnas, ...)      -> (ruta, estadísticas | None)
- asegurar_vulnerabilidad_web(carpeta_datos, ...)           -> ruta del GeoJSON listo para la web

Notas
- Tolerancia en grados (CRS EPSG:4326): 0.0005 ≈ 55 m; 4 decimales ≈ 11 m.
  A mayor tolerancia, archivo más liviano y bordes más angulosos al acercarse mucho.
- El GeoJSON generado se puede versionar en el repositorio para que Streamlit Cloud no tenga
  que regenerarlo en cada arranque (la firma incluye el tamaño del archivo de origen y los
  parámetros; si cambian, se regenera automáticamente).
"""
import json
import logging
import os
import threading
import uuid
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

COLUMNAS_VULNERABILIDAD = ["CLAVE_ACUI", "NOM_ACUIF", "VULNERABIL"]
# Súbela cuando cambie el algoritmo: invalida los archivos generados con la versión anterior.
# v2: los polígonos que se vaciaban al redondear ya NO se descartan (se conservan sin redondear).
VERSION_ALGORITMO = 2
_CANDADO = threading.Lock()

def asegurar_vulnerabilidad_web(carpeta_datos, tolerancia=0.00005, decimales=7, forzar=False):
    print(f"\n>>> EJECUTANDO con tolerancia={tolerancia}, decimales={decimales}, forzar={forzar} <<<\n")
    carpeta = Path(carpeta_datos)

def _solo_poligonos(geom):
    """Deja solo las partes poligonales de una geometría (make_valid puede devolver colecciones)."""
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        from shapely.geometry import MultiPolygon
        partes = []
        for g in geom.geoms:
            if g.geom_type == "Polygon":
                partes.append(g)
            elif g.geom_type == "MultiPolygon":
                partes.extend(g.geoms)
        return MultiPolygon(partes) if partes else None
    return None


def _completar_con_respaldo(geoms, respaldos, vacio):
    """Reemplaza los elementos "vacíos" de `geoms` por el primer respaldo que no lo esté.

    `vacio(arreglo)` devuelve un arreglo booleano. Devuelve (geoms, recuperadas, restantes).
    """
    geoms = geoms.copy()
    pendientes = vacio(geoms)
    iniciales = int(pendientes.sum())
    for respaldo in respaldos:
        if not pendientes.any():
            break
        geoms[pendientes] = respaldo[pendientes]
        pendientes = vacio(geoms)
    restantes = int(pendientes.sum())
    return geoms, iniciales - restantes, restantes


def optimizar_poligonos(gdf, columnas, tolerancia=0.000001, decimales=6):
    """Simplifica y redondea una capa de polígonos. Devuelve (GeoDataFrame, estadísticas)."""
    import geopandas as gpd
    import shapely

    cols = [c for c in columnas if c in gdf.columns and c != "geometry"]
    base = gdf[cols + ["geometry"]].copy()
    if base.crs is not None and base.crs.to_epsg() != 4326:
        base = base.to_crs(4326)

    n_inicial = len(base)
    vertices_antes = int(shapely.get_num_coordinates(base.geometry.values).sum())

    originales = np.asarray(base.geometry.values, dtype=object)
    simples = np.asarray(base.geometry.simplify(tolerancia, preserve_topology=True).values, dtype=object)
    geoms = np.asarray(shapely.transform(simples, lambda c: np.round(c, decimales)), dtype=object)

    # El redondeo puede dejar polígonos inválidos (autointersecciones mínimas): se reparan.
    invalidas = ~shapely.is_valid(geoms) & ~shapely.is_missing(geoms)
    reparadas = int(invalidas.sum())
    if reparadas:
        arreglo = shapely.make_valid(geoms[invalidas])
        geoms[invalidas] = [_solo_poligonos(g) for g in arreglo]

    # Los polígonos más pequeños que la precisión de redondeo se vacían o dejan de ser polígonos:
    # en vez de descartarlos (el acuífero perdería zonas), se conservan simplificados y sin redondear
    # y, si aun así fallan, con su geometría original. Solo se descartan los que ya venían vacíos.
    def _vacio(arreglo):
        return shapely.is_missing(arreglo) | shapely.is_empty(arreglo)

    geoms, recuperadas, descartadas = _completar_con_respaldo(geoms, [simples, originales], _vacio)
    resultado = gpd.GeoDataFrame(base[cols], geometry=gpd.GeoSeries(geoms, index=base.index, crs=base.crs))
    resultado = resultado[~_vacio(geoms)]

    vertices_despues = int(shapely.get_num_coordinates(resultado.geometry.values).sum())
    stats = {
        "elementos_antes": n_inicial, "elementos_despues": len(resultado),
        "vertices_antes": vertices_antes, "vertices_despues": vertices_despues,
        "reparadas": reparadas, "recuperadas": recuperadas, "descartadas": descartadas,
        "tolerancia": tolerancia, "decimales": decimales,
    }
    return resultado, stats


def a_geojson_compacto(gdf):
    """GeoJSON sin espacios ni ids (más liviano que gdf.to_json() por defecto)."""
    return gdf.to_json(drop_id=True, separators=(",", ":"))


def _escribir_atomico(ruta: Path, texto: str):
    tmp = ruta.with_name(f"{ruta.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)  # otra sesión nunca lee un archivo a medias


def asegurar_geojson_web(fuente, destino, columnas, tolerancia=0.000001, decimales=6, forzar=False):
    """Devuelve (ruta_geojson_web, estadisticas). estadisticas es None si se reutilizó el archivo."""
    fuente, destino = Path(fuente), Path(destino)
    meta_ruta = destino.with_name(destino.stem + ".meta.json")
    firma = {"fuente": fuente.name, "tamano": fuente.stat().st_size, "tolerancia": tolerancia,
             "decimales": decimales, "columnas": list(columnas), "version": VERSION_ALGORITMO}

    def vigente():
        if forzar or not destino.exists() or not meta_ruta.exists():
            return False
        try:
            return json.loads(meta_ruta.read_text(encoding="utf-8")).get("firma") == firma
        except (OSError, ValueError):
            return False

    if vigente():
        return destino, None
    with _CANDADO:
        if vigente():  # otra sesión lo generó mientras esperábamos
            return destino, None
        import geopandas as gpd
        gdf = gpd.read_parquet(fuente) if fuente.suffix == ".parquet" else gpd.read_file(fuente)
        optimizado, stats = optimizar_poligonos(gdf, columnas, tolerancia, decimales)
        texto = a_geojson_compacto(optimizado)
        destino.parent.mkdir(parents=True, exist_ok=True)
        _escribir_atomico(destino, texto)
        stats["tamano_mb"] = round(len(texto.encode("utf-8")) / 1024 / 1024, 2)
        _escribir_atomico(meta_ruta, json.dumps({"firma": firma, "stats": stats}, ensure_ascii=False))
        logger.info("GeoJSON web generado: %s (%s MB, %s -> %s vértices)", destino.name,
                    stats["tamano_mb"], stats["vertices_antes"], stats["vertices_despues"])
        return destino, stats


def asegurar_vulnerabilidad_web(carpeta_datos, tolerancia=0.000001, decimales=6, forzar=False):
    """GeoJSON optimizado de la capa nacional de vulnerabilidad (data/web/...)."""
    carpeta = Path(carpeta_datos)
    ruta, _ = asegurar_geojson_web(
        carpeta / "Vulnerabilidad_Nacional.parquet",
        carpeta / "web" / "Vulnerabilidad_Nacional_web.geojson",
        COLUMNAS_VULNERABILIDAD, tolerancia, decimales, forzar)
    return ruta
