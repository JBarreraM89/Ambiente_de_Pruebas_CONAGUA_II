# convertidor_datos.py
import pandas as pd
import geopandas as gpd
import glob
import os

def consolidar_geojson_a_parquet():
    print("Iniciando consolidación de datos espaciales...")
    
    todos_los_geojson = glob.glob("*.geojson")
    archivos_vuln = [arch for arch in todos_los_geojson if "Linea_Costa" not in arch]
    
    print(f"🔍 Se encontraron {len(archivos_vuln)} archivos de vulnerabilidad para consolidar.")
    
    if len(archivos_vuln) == 0:
        print("❌ ERROR: No se encontraron archivos.")
        return

    lista_gdf = []
    archivos_procesados = 0
    
    for arch in archivos_vuln:
        try:
            gdf = gpd.read_file(arch)
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            elif gdf.crs.to_epsg() != 4326:
                gdf.to_crs(epsg=4326, inplace=True)
                
            lista_gdf.append(gdf)
            archivos_procesados += 1
            
            if archivos_procesados % 20 == 0:
                print(f"⏳ Procesados {archivos_procesados} de {len(archivos_vuln)} archivos...")
                
        except Exception as e:
            print(f"⚠️ Error leyendo el archivo {arch}: {e}")
            
    if lista_gdf:
        print("🧩 Uniendo todos los polígonos en un solo archivo...")
        gdf_nacional = pd.concat(lista_gdf, ignore_index=True)
        
        # =======================================================
        # 🧹 SOLUCIÓN AL ERROR DE PYARROW (Sanitización)
        # =======================================================
        print("🧹 Sanitizando tipos de datos para evitar errores de PyArrow...")
        
        # 1. Forzar VULNERABIL a número (si hay textos raros, los vuelve nulos)
        if 'VULNERABIL' in gdf_nacional.columns:
            gdf_nacional['VULNERABIL'] = pd.to_numeric(gdf_nacional['VULNERABIL'], errors='coerce')
            
        # 2. Forzar todas las demás columnas (excepto geometry) a Texto (String)
        for col in gdf_nacional.columns:
            if col not in ['geometry', 'VULNERABIL']:
                # Convertimos a string y quitamos los ".0" residuales en las claves
                gdf_nacional[col] = gdf_nacional[col].astype(str).str.replace('.0', '', regex=False)
        # =======================================================

        nombre_salida = "Vulnerabilidad_Nacional.parquet"
        gdf_nacional.to_parquet(nombre_salida)
        print(f"✅ ÉXITO: Archivo '{nombre_salida}' creado correctamente.")
        print(f"📊 Total de polígonos consolidados: {len(gdf_nacional)}")
    else:
        print("❌ No se pudo procesar ningún archivo válido.")

if __name__ == "__main__":
    consolidar_geojson_a_parquet()