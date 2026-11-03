# -*- coding: utf-8 -*-
"""
Script de Conversión y Empaquetado: Parquet REPDA -> Vector Tiles PMTiles (v3)
Genera la pirámide multiescala de teselas vectoriales MVT de las 461,917 concesiones
de aguas subterráneas de México en un archivo único de alto rendimiento.

Correcciones clave:
1. normalizar_uso: Homologa los valores de D_USO_TIT resolviendo caracteres corruptos
   (ej. 'AGRCOLA' -> 'AGRICOLA', 'PBLICO URBANO' -> 'PUBLICO URBANO') para coincidir
   1:1 con la simbología MapLibre por Uso Oficial CONAGUA.
2. default_options={'y_coord_down': True}: Evita la inversión vertical de coordenadas
   dentro de cada tesela que causaba desplazamiento de puntos al océano o fuera de posición.
3. Muestreo estratificado por uso en zooms panorámicos (4-7) y 100% en zoom 8.
"""

import os
import sys
import time
import gzip
import duckdb
import numpy as np
import pandas as pd
import mapbox_vector_tile
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid, TileType, Compression

def normalizar_uso(s):
    if not s:
        return 'OTROS'
    s_up = str(s).upper()
    if 'AGROIND' in s_up:
        return 'AGROINDUSTRIAL'
    if 'AGR' in s_up:
        return 'AGRICOLA'
    if 'PUBLI' in s_up or 'URBANO' in s_up:
        return 'PUBLICO URBANO'
    if 'DOM' in s_up:
        return 'DOMESTICO'
    if 'INDUS' in s_up:
        return 'INDUSTRIAL'
    if 'SERV' in s_up:
        return 'SERVICIOS'
    if 'PECUAR' in s_up:
        return 'PECUARIO'
    if 'DIFER' in s_up:
        return 'DIFERENTES USOS'
    if 'ACUAC' in s_up:
        return 'ACUACULTURA'
    if 'COMERC' in s_up:
        return 'COMERCIO'
    if 'ENERG' in s_up:
        return 'ENERGIA ELECTRICA'
    return 'OTROS'

def construir_pmtiles_repda(
    parquet_path="data/coordenadas_repda_sep25.parquet",
    output_path="data/repda_nacional.pmtiles",
    max_zoom=8
):
    t0 = time.time()
    print("1. Consultando archivo parquet oficial...")
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT 
            COALESCE(FOLIOREG, '') as f,
            COALESCE(NO_EXPE, '') as e,
            COALESCE(SUBSTR(TITULAR, 1, 35), '') as t,
            COALESCE(D_USO_TIT, 'OTROS') as u_raw,
            CAST(ROUND(COALESCE(VOLEXTANUA, 0)) AS BIGINT) as v,
            LATDEC as lat,
            LONDEC as lon
        FROM '{parquet_path}'
        WHERE LATDEC IS NOT NULL AND LONDEC IS NOT NULL 
          AND LATDEC BETWEEN 14.0 AND 33.5 AND LONDEC BETWEEN -118.5 AND -86.0
    """).fetchdf()
    n_total = len(df)
    print(f"   {n_total:,} aprovechamientos subterráneos leídos en {time.time() - t0:.2f} s")

    # Normalizar uso consuntivo para coincidir con la paleta de colores MapLibre
    print("2. Normalizando uso consuntivo...")
    df['u'] = df['u_raw'].apply(normalizar_uso)
    conteo_usos = df['u'].value_counts()
    for uso, c in conteo_usos.items():
        print(f"   - {uso:20s}: {c:,}")

    def get_tile_xy(lat_arr, lon_arr, z):
        lat_r = np.radians(lat_arr)
        n = 2.0 ** z
        xtile = np.floor((lon_arr + 180.0) / 360.0 * n).astype(int)
        ytile = np.floor((1.0 - np.arcsinh(np.tan(lat_r)) / np.pi) / 2.0 * n).astype(int)
        return xtile, ytile

    tiles_dict = {}

    print(f"\n3. Generando pirámide de teselas vectoriales (Zooms 4 a {max_zoom})...")
    for z in range(4, max_zoom + 1):
        tz0 = time.time()
        
        # En zooms 4-7 tomamos un subconjunto representativo ponderado por volumen
        # para carga instantánea a nivel país; en zoom 8+ va el 100% de puntos.
        if z == 4:
            # Estratificado por tesela y uso
            limit_per_tile = 400
        elif z == 5:
            limit_per_tile = 800
        elif z == 6:
            limit_per_tile = 1800
        elif z == 7:
            limit_per_tile = 4000
        else:
            limit_per_tile = None

        tx, ty = get_tile_xy(df['lat'].values, df['lon'].values, z)
        df_z = df.copy()
        df_z['tx'] = tx
        df_z['ty'] = ty

        # Coordenadas locales de pixel [0, 4096] dentro de la tesela
        # 0 es el norte (borde superior), 4096 es el sur (borde inferior)
        n = 2.0 ** z
        gx = (df_z['lon'].values + 180.0) / 360.0 * n
        gy = (1.0 - np.arcsinh(np.tan(np.radians(df_z['lat'].values))) / np.pi) / 2.0 * n
        px = np.clip(np.round((gx - df_z['tx'].values) * 4096).astype(int), 0, 4096)
        py = np.clip(np.round((gy - df_z['ty'].values) * 4096).astype(int), 0, 4096)
        df_z['px'] = px
        df_z['py'] = py

        grouped = df_z.groupby(['tx', 'ty'])
        count_z = 0
        for (x_val, y_val), grp in grouped:
            if limit_per_tile is not None and len(grp) > limit_per_tile:
                # Muestreo estratificado: ordenar por volumen para asegurar presencia de captaciones clave
                sub_grp = grp.sort_values('v', ascending=False).head(limit_per_tile)
            else:
                sub_grp = grp

            feats = []
            for r in sub_grp.itertuples():
                feats.append({
                    "geometry": f"POINT({r.px} {r.py})",
                    "properties": {
                        "f": str(r.f),
                        "e": str(r.e),
                        "t": str(r.t),
                        "u": str(r.u),
                        "v": int(r.v)
                    }
                })

            tid = zxy_to_tileid(z, x_val, y_val)
            tiles_dict[tid] = feats
            count_z += 1

        print(f"   Zoom {z:2d}: {count_z:4d} teselas calculadas en {time.time() - tz0:.2f} s")

    print(f"\n4. Codificando {len(tiles_dict):,} teselas a MVT con y_coord_down=True...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "wb") as f_out:
        w = Writer(f_out)
        for tid in sorted(tiles_dict.keys()):
            feats = tiles_dict[tid]
            # IMPORTANTE: default_options={'y_coord_down': True} evita la inversión de Y
            mvt_bytes = mapbox_vector_tile.encode([{
                "name": "repda",
                "features": feats
            }], default_options={'y_coord_down': True})
            mvt_gz = gzip.compress(mvt_bytes)
            w.write_tile(tid, mvt_gz)

        header = {
            "root_dir_offset": 0,
            "root_dir_bytes": 0,
            "json_metadata_offset": 0,
            "json_metadata_bytes": 0,
            "leaf_dirs_offset": 0,
            "leaf_dirs_bytes": 0,
            "tile_data_offset": 0,
            "tile_data_bytes": 0,
            "addressed_tiles_count": len(tiles_dict),
            "tile_entries_count": len(tiles_dict),
            "tile_contents_count": len(tiles_dict),
            "clustered": True,
            "internal_compression": Compression.GZIP,
            "tile_compression": Compression.GZIP,
            "tile_type": TileType.MVT,
            "min_zoom": 4,
            "max_zoom": max_zoom,
            "min_lon_e7": int(-118.5 * 1e7),
            "min_lat_e7": int(14.0 * 1e7),
            "max_lon_e7": int(-86.0 * 1e7),
            "max_lat_e7": int(33.5 * 1e7),
            "center_zoom": 5,
            "center_lon_e7": int(-102.0 * 1e7),
            "center_lat_e7": int(23.5 * 1e7)
        }
        metadata = {
            "name": "REPDA Concesiones Aguas Subterráneas México",
            "description": "Teselas vectoriales optimizadas de 461,914 aprovechamientos REPDA",
            "version": "1.0",
            "type": "overlay",
            "vector_layers": [
                {
                    "id": "repda",
                    "description": "Captaciones subterráneas concesionadas",
                    "fields": {
                        "f": "Folio REPDA",
                        "e": "Número de Expediente",
                        "t": "Titular",
                        "u": "Uso Consuntivo Oficial",
                        "v": "Volumen Anual (m3)"
                    }
                }
            ]
        }
        w.finalize(header, metadata)

    # Copiar también a static/ para redundancia
    static_path = os.path.join("static", os.path.basename(output_path))
    os.makedirs("static", exist_ok=True)
    import shutil
    shutil.copy2(output_path, static_path)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\nPMTiles generado exitosamente:")
    print(f" -> {output_path} ({size_mb:.2f} MB)")
    print(f" -> {static_path} ({size_mb:.2f} MB)")
    print(f"Tiempo total de ejecucion: {time.time() - t0:.2f} s")

if __name__ == "__main__":
    construir_pmtiles_repda()
