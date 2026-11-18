# -*- coding: utf-8 -*-
"""
Constructor de Teselas Vectoriales PMTiles sin simplificación destructiva
directo desde los GeoJSON crudos de `data/vulnerabilidad/`.

Características:
- Preserva 100 % de los vértices de origen antes de proyectar a la rejilla entera
  común MVT (4096 × 4096) con buffer de borde de tesela (sin huecos entre polígonos).
- Incluye líneas de costa (`costa_1km` y `costa_10km`) en el mismo archivo PMTiles.
- Sanea registros corruptos (`VULNERABIL` fuera de 1..5 y geometrías vacías/inválidas).
- Calcula un índice ligero JSON (`data/web/vulnerabilidad_index.json`) con bbox exacto,
  conteo de polígonos y área real (EPSG:6372) desglosada por clase 1..5 para cada acuífero.

Uso:
    python data/convertidor_vulnerabilidad_pmtiles.py
"""

import argparse
import gzip
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import mapbox_vector_tile
import numpy as np
import pandas as pd
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from shapely import STRtree, clip_by_rect, make_valid
from shapely.errors import GEOSException
from shapely.geometry import MultiLineString, MultiPolygon, box
from shapely.ops import transform

CLASES_VALIDAS = (1, 2, 3, 4, 5)


def _to_merc_norm(x, y, z=None):
    """Convierte lon/lat EPSG:4326 a coordenadas WebMercator normalizadas [0, 1]."""
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    gx = (x_arr + 180.0) / 360.0
    lat_r = np.radians(np.clip(y_arr, -85.05112878, 85.05112878))
    gy = (1.0 - np.arcsinh(np.tan(lat_r)) / np.pi) / 2.0
    return gx, gy


def _extraer_poligonos(geom):
    """Mantiene exclusivamente partes poligonales no vacías."""
    if geom is None or geom.is_empty:
        return None
    gtype = geom.geom_type
    if gtype in ("Polygon", "MultiPolygon"):
        return geom
    if gtype == "GeometryCollection":
        partes = []
        for g in geom.geoms:
            if g.is_empty:
                continue
            if g.geom_type == "Polygon":
                partes.append(g)
            elif g.geom_type == "MultiPolygon":
                partes.extend(g.geoms)
        if not partes:
            return None
        return partes[0] if len(partes) == 1 else MultiPolygon(partes)
    return None


def _extraer_lineas_o_poligonos(geom):
    """Mantiene geometrías lineales o poligonales válidas para franjas/líneas de costa."""
    if geom is None or geom.is_empty:
        return None
    gtype = geom.geom_type
    if gtype in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
        return geom
    if gtype == "GeometryCollection":
        polys = _extraer_poligonos(geom)
        if polys is not None:
            return polys
        partes = [g for g in geom.geoms if not g.is_empty and g.geom_type in ("LineString", "MultiLineString")]
        if not partes:
            return None
        return partes[0] if len(partes) == 1 else MultiLineString(partes)
    return None


def _recortar_seguro(geom, x0, y0, x1, y1):
    """Recorta por rectángulo con respaldo por intersección ante anillos degenerados."""
    try:
        return clip_by_rect(geom, x0, y0, x1, y1)
    except GEOSException:
        try:
            g_fix = make_valid(geom)
            return g_fix.intersection(box(x0, y0, x1, y1))
        except Exception:
            return None


def _cargar_vulnerabilidad_cruda(carpeta_vuln: Path):
    """Carga y consolida todos los GeoJSON crudos de acuíferos (sin simplificación)."""
    archivos = sorted(
        f for f in carpeta_vuln.glob("*.geojson")
        if "Linea_Costa" not in f.name
    )
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos GeoJSON en {carpeta_vuln}")

    marcos = []
    for arch in archivos:
        gdf = gpd.read_file(arch)
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        faltantes = [c for c in ("CLAVE_ACUI", "NOM_ACUIF", "VULNERABIL") if c not in gdf.columns]
        if faltantes:
            raise ValueError(f"{arch.name} no contiene columnas requeridas: {faltantes}")
        marcos.append(gdf[["CLAVE_ACUI", "NOM_ACUIF", "VULNERABIL", "geometry"]])

    df = gpd.GeoDataFrame(pd.concat(marcos, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    total_raw = len(df)

    # Quitar geometrías vacías/nulas
    mask_geom = (~df.geometry.is_empty) & df.geometry.notnull()
    descartadas_vacias = int((~mask_geom).sum())
    df = df[mask_geom].copy()

    # Normalizar clase VULNERABIL a entero 1..5
    v_num = pd.to_numeric(df["VULNERABIL"], errors="coerce")
    mask_clase = v_num.isin(CLASES_VALIDAS)
    anomalas = []
    if (~mask_clase).any():
        for _, r in df[~mask_clase].iterrows():
            anomalas.append({
                "clave": str(r["CLAVE_ACUI"]).strip().zfill(4),
                "valor": None if pd.isna(r["VULNERABIL"]) else str(r["VULNERABIL"]),
            })
    df = df[mask_clase].copy()
    df["v_int"] = v_num[mask_clase].astype(int)
    df["clave"] = df["CLAVE_ACUI"].astype(str).str.strip().str.zfill(4)
    df["nombre"] = df["NOM_ACUIF"].astype(str).str.strip()

    # Reparar anillos inválidos sin simplificar vértices
    geoms_limpias = []
    reparadas = 0
    for g in df.geometry:
        if not g.is_valid:
            g = make_valid(g)
            reparadas += 1
        g = _extraer_poligonos(g)
        geoms_limpias.append(g)

    df["geometry"] = geoms_limpias
    df = df[df.geometry.notna() & (~df.geometry.is_empty)].copy().reset_index(drop=True)
    df["fid"] = np.arange(1, len(df) + 1, dtype=np.int64)

    stats_carga = {
        "archivos_geojson": len(archivos),
        "registros_origen": total_raw,
        "descartadas_vacias": descartadas_vacias,
        "descartadas_clase_anomala": len(anomalas),
        "detalle_anomalas": anomalas,
        "geometrias_reparadas": reparadas,
        "poligonos_validos": len(df),
    }
    return df, stats_carga


def _construir_indice_acuiferos(df: gpd.GeoDataFrame):
    """Construye catálogo liviano de acuíferos con bbox real y desglose de área por clase."""
    df_m = df.to_crs(epsg=6372)
    areas_km2 = df_m.geometry.area.values / 1e6
    bounds_arr = df.geometry.bounds  # minx, miny, maxx, maxy

    grupos = defaultdict(lambda: {
        "clave": "",
        "nombre": "",
        "bounds": [180.0, 90.0, -180.0, -90.0],
        "poligonos": 0,
        "area_km2": 0.0,
        "clases": {str(c): {"count": 0, "area_km2": 0.0, "pct": 0.0} for c in CLASES_VALIDAS},
    })

    for i, row in enumerate(df.itertuples()):
        key = f"{row.clave} - {row.nombre}"
        g = grupos[key]
        g["clave"] = row.clave
        g["nombre"] = row.nombre
        b = bounds_arr.iloc[i]
        g["bounds"] = [
            round(min(g["bounds"][0], float(b["minx"])), 6),
            round(min(g["bounds"][1], float(b["miny"])), 6),
            round(max(g["bounds"][2], float(b["maxx"])), 6),
            round(max(g["bounds"][3], float(b["maxy"])), 6),
        ]
        area = float(areas_km2[i])
        cls_key = str(row.v_int)
        g["poligonos"] += 1
        g["area_km2"] += area
        g["clases"][cls_key]["count"] += 1
        g["clases"][cls_key]["area_km2"] += area

    acuiferos = {}
    for key in sorted(grupos.keys()):
        g = grupos[key]
        total_a = g["area_km2"]
        clases_limpias = {}
        clase_predom = None
        max_area = -1.0
        for c in CLASES_VALIDAS:
            ck = str(c)
            info = g["clases"][ck]
            if info["count"] > 0:
                pct = round((info["area_km2"] / total_a) * 100.0, 2) if total_a > 0 else 0.0
                clases_limpias[ck] = {
                    "count": info["count"],
                    "area_km2": round(info["area_km2"], 3),
                    "pct": pct,
                }
                if info["area_km2"] > max_area:
                    max_area = info["area_km2"]
                    clase_predom = ck
        acuiferos[key] = {
            "clave": g["clave"],
            "nombre": g["nombre"],
            "bounds": g["bounds"],
            "poligonos": g["poligonos"],
            "area_km2": round(total_a, 2),
            "clase_predominante": clase_predom,
            "clases": clases_limpias,
        }
    return acuiferos


def _cargar_lineas_costa(carpeta_vuln: Path, carpeta_datos: Path):
    """Carga líneas de costa 1km y 10km (GeoJSON o Parquet) y las proyecta a Mercator [0, 1]."""
    resultado = {}
    for tag, nombre_base in (("costa_10km", "Linea_Costa_10km"), ("costa_1km", "Linea_Costa_1km")):
        ruta_gj = carpeta_vuln / f"{nombre_base}.geojson"
        ruta_pq = carpeta_datos / f"{nombre_base}.parquet"
        gdf = None
        if ruta_gj.exists():
            gdf = gpd.read_file(ruta_gj)
        elif ruta_pq.exists():
            gdf = gpd.read_parquet(ruta_pq)
        if gdf is None or gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        norm_lines = []
        for g in gdf.geometry:
            if g is None or g.is_empty:
                continue
            if not g.is_valid:
                g = make_valid(g)
            # Convertir polígonos de franja costera a su contorno lineal para evitar bordes de cierre por tesela
            if g.geom_type in ("Polygon", "MultiPolygon"):
                g = g.boundary
            elif g.geom_type == "GeometryCollection":
                g = _extraer_poligonos(g)
                if g is not None:
                    g = g.boundary
            ng = _extraer_lineas_o_poligonos(transform(_to_merc_norm, g))
            if ng is not None and not ng.is_empty:
                norm_lines.append(ng)
        if norm_lines:
            resultado[tag] = (norm_lines, STRtree(norm_lines))
    return resultado


def construir_pmtiles_vulnerabilidad(
    carpeta_datos="data",
    output_pmtiles="static/vulnerabilidad_nacional.pmtiles",
    output_index="data/web/vulnerabilidad_index.json",
    min_zoom=3,
    max_zoom=11,
    extent=4096,
    buffer_px=128,
):
    t0 = time.time()
    raiz = Path(__file__).resolve().parent.parent
    dir_datos = (raiz / carpeta_datos) if not Path(carpeta_datos).is_absolute() else Path(carpeta_datos)
    dir_vuln = dir_datos / "vulnerabilidad"
    ruta_pmtiles = (raiz / output_pmtiles) if not Path(output_pmtiles).is_absolute() else Path(output_pmtiles)
    ruta_index = (raiz / output_index) if not Path(output_index).is_absolute() else Path(output_index)

    print("1. Leyendo GeoJSON crudos de vulnerabilidad...")
    df, stats_carga = _cargar_vulnerabilidad_cruda(dir_vuln)
    print(f"   Cargados {stats_carga['poligonos_validos']:,} polígonos válidos de {stats_carga['archivos_geojson']} acuíferos.")

    print("2. Calculando catálogo de acuíferos y áreas oficiales (EPSG:6372)...")
    acuiferos_idx = _construir_indice_acuiferos(df)

    print("3. Proyectando geometrías al plano normalizado WebMercator...")
    norm_geoms = []
    meta_rows = []
    for row in df.itertuples():
        ng = _extraer_poligonos(transform(_to_merc_norm, row.geometry))
        if ng is not None and not ng.is_valid:
            ng = _extraer_poligonos(make_valid(ng))
        if ng is not None and not ng.is_empty:
            norm_geoms.append(ng)
            meta_rows.append((int(row.fid), row.clave, row.nombre, int(row.v_int)))

    tree_vuln = STRtree(norm_geoms)
    minx = min(g.bounds[0] for g in norm_geoms)
    miny = min(g.bounds[1] for g in norm_geoms)
    maxx = max(g.bounds[2] for g in norm_geoms)
    maxy = max(g.bounds[3] for g in norm_geoms)

    costas = _cargar_lineas_costa(dir_vuln, dir_datos)
    print(f"   Capas de costa detectadas: {list(costas.keys())}")

    print(f"4. Construyendo teselas vectoriales MVT (z={min_zoom}..{max_zoom}, extent={extent}, buffer={buffer_px})...")
    tiles_gz = {}
    for z in range(min_zoom, max_zoom + 1):
        tz = time.time()
        n = 2.0 ** z
        tx0, tx1 = int(math.floor(minx * n)), int(math.floor(maxx * n))
        ty0, ty1 = int(math.floor(miny * n)), int(math.floor(maxy * n))
        count_z = 0

        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                bx0 = (tx - buffer_px / extent) / n
                by0 = (ty - buffer_px / extent) / n
                bx1 = (tx + 1 + buffer_px / extent) / n
                by1 = (ty + 1 + buffer_px / extent) / n

                capas_mvt = []

                hits = tree_vuln.query(box(bx0, by0, bx1, by1), predicate="intersects")
                feats_v = []
                for h in hits:
                    cg = _recortar_seguro(norm_geoms[h], bx0, by0, bx1, by1)
                    if cg is None or cg.is_empty:
                        continue
                    tg = transform(
                        lambda px, py, pz=None, _tx=tx, _ty=ty, _n=n: (
                            np.round((np.asarray(px) * _n - _tx) * extent),
                            np.round((np.asarray(py) * _n - _ty) * extent),
                        ),
                        cg,
                    )
                    if not tg.is_valid:
                        tg = make_valid(tg)
                    tg = _extraer_poligonos(tg)
                    if tg is not None and not tg.is_empty and tg.area >= 0.5:
                        fid, clave, nombre, v_int = meta_rows[h]
                        feats_v.append({
                            "id": fid,
                            "geometry": tg,
                            "properties": {
                                "fid": fid,
                                "c": clave,
                                "n": nombre,
                                "v": v_int,
                            },
                        })

                if feats_v:
                    capas_mvt.append({"name": "vulnerabilidad", "features": feats_v})

                for tag_costa, (lines_list, tree_costa) in costas.items():
                    c_hits = tree_costa.query(box(bx0, by0, bx1, by1), predicate="intersects")
                    feats_c = []
                    for ch in c_hits:
                        cg = _recortar_seguro(lines_list[ch], bx0, by0, bx1, by1)
                        if cg is None or cg.is_empty:
                            continue
                        tg = transform(
                            lambda px, py, pz=None, _tx=tx, _ty=ty, _n=n: (
                                np.round((np.asarray(px) * _n - _tx) * extent),
                                np.round((np.asarray(py) * _n - _ty) * extent),
                            ),
                            cg,
                        )
                        if not tg.is_valid:
                            tg = make_valid(tg)
                        tg = _extraer_lineas_o_poligonos(tg)
                        if tg is not None and not tg.is_empty and (tg.area >= 0.5 or tg.length >= 0.5):
                            feats_c.append({"geometry": tg, "properties": {}})
                    if feats_c:
                        capas_mvt.append({"name": tag_costa, "features": feats_c})

                if capas_mvt:
                    mvt_bytes = mapbox_vector_tile.encode(
                        capas_mvt,
                        default_options={"y_coord_down": True, "extents": extent},
                    )
                    tid = zxy_to_tileid(z, tx, ty)
                    tiles_gz[tid] = gzip.compress(mvt_bytes, compresslevel=6)
                    count_z += 1

        print(f"   Zoom {z:2d}: {count_z:4d} teselas ({time.time() - tz:.2f} s)")

    print("5. Empaquetando archivo PMTiles...")
    ruta_pmtiles.parent.mkdir(parents=True, exist_ok=True)
    total_bounds = df.total_bounds  # min_lon, min_lat, max_lon, max_lat
    with open(ruta_pmtiles, "wb") as f_out:
        writer = Writer(f_out)
        for tid in sorted(tiles_gz.keys()):
            writer.write_tile(tid, tiles_gz[tid])

        header = {
            "root_dir_offset": 0,
            "root_dir_bytes": 0,
            "json_metadata_offset": 0,
            "json_metadata_bytes": 0,
            "leaf_dirs_offset": 0,
            "leaf_dirs_bytes": 0,
            "tile_data_offset": 0,
            "tile_data_bytes": 0,
            "addressed_tiles_count": len(tiles_gz),
            "tile_entries_count": len(tiles_gz),
            "tile_contents_count": len(tiles_gz),
            "clustered": True,
            "internal_compression": Compression.GZIP,
            "tile_compression": Compression.GZIP,
            "tile_type": TileType.MVT,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "min_lon_e7": int(round(float(total_bounds[0]) * 1e7)),
            "min_lat_e7": int(round(float(total_bounds[1]) * 1e7)),
            "max_lon_e7": int(round(float(total_bounds[2]) * 1e7)),
            "max_lat_e7": int(round(float(total_bounds[3]) * 1e7)),
            "center_zoom": 5,
            "center_lon_e7": int(-102.0 * 1e7),
            "center_lat_e7": int(23.5 * 1e7),
        }
        metadata = {
            "name": "Vulnerabilidad Nacional Acuíferos CONAGUA",
            "description": "Teselas vectoriales MVT generadas directo desde GeoJSON crudos sin pérdida de bordes",
            "version": "1.0",
            "type": "overlay",
            "vector_layers": [
                {
                    "id": "vulnerabilidad",
                    "description": "Polígonos de vulnerabilidad intrínseca (SEAG-INDEX 1..5)",
                    "fields": {"fid": "ID único", "c": "Clave Acuífero", "n": "Nombre Acuífero", "v": "Clase 1..5"},
                },
                {"id": "costa_10km", "description": "Franja línea de costa 10 km", "fields": {}},
                {"id": "costa_1km", "description": "Franja línea de costa 1 km", "fields": {}},
            ],
        }
        writer.finalize(header, metadata)

    ruta_index.parent.mkdir(parents=True, exist_ok=True)
    indice_payload = {
        "version": 1,
        "bounds_nacional": [round(float(x), 6) for x in total_bounds],
        "stats": stats_carga,
        "has_costa_10km": "costa_10km" in costas,
        "has_costa_1km": "costa_1km" in costas,
        "acuiferos": acuiferos_idx,
    }
    ruta_index.write_text(json.dumps(indice_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    size_mb = ruta_pmtiles.stat().st_size / (1024 * 1024)
    idx_kb = ruta_index.stat().st_size / 1024
    print(f"\nPMTiles generado exitosamente en {time.time() - t0:.2f} s:")
    print(f" -> {ruta_pmtiles} ({size_mb:.2f} MB)")
    print(f" -> {ruta_index} ({idx_kb:.1f} KB, {len(acuiferos_idx)} acuíferos)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de PMTiles para Geovisor de Vulnerabilidad")
    parser.add_argument("--max-zoom", type=int, default=11)
    parser.add_argument("--min-zoom", type=int, default=3)
    args = parser.parse_args()
    construir_pmtiles_vulnerabilidad(min_zoom=args.min_zoom, max_zoom=args.max_zoom)
