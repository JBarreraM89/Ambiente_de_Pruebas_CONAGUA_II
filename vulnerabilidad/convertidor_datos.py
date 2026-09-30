# convertidor_datos.py
import pandas as pd
import geopandas as gpd
import glob
import os

def consolidar_geojson_a_parquet():
    print("Iniciando consolidación de datos espaciales...")
    
    # 1. Buscar TODOS los archivos .geojson en la carpeta actual
    todos_los_geojson = glob.glob("*.geojson")
    
    # 2. Filtrar: Excluir las líneas de costa para quedarnos solo con los acuíferos (los que tienen números)
    archivos_vuln = [arch for arch in todos_los_geojson if "Linea_Costa" not in arch]
    
    print(f"🔍 Se encontraron {len(archivos_vuln)} archivos de vulnerabilidad para consolidar.")
    
    if len(archivos_vuln) == 0:
        print("❌ ERROR: No se encontraron archivos.")
        return

    lista_gdf = []
    archivos_procesados = 0
    
    for arch in archivos_vuln:
        try:
            # Leer el GeoJSON
            gdf = gpd.read_file(arch)
            
            # Estandarizar el sistema de coordenadas (WGS84 - Lat/Lon)
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            elif gdf.crs.to_epsg() != 4326:
                gdf.to_crs(epsg=4326, inplace=True)
                
            lista_gdf.append(gdf)
            archivos_procesados += 1
            
            # Mostrar progreso cada 20 archivos para no saturar la consola
            if archivos_procesados % 20 == 0:
                print(f"⏳ Procesados {archivos_procesados} de {len(archivos_vuln)} archivos...")
                
        except Exception as e:
            print(f"⚠️ Error leyendo el archivo {arch}: {e}")
            
    # 3. Unir y guardar
    if lista_gdf:
        print("🧩 Uniendo todos los polígonos en un solo archivo...")
        gdf_nacional = pd.concat(lista_gdf, ignore_index=True)
        
        # Guardar como Parquet
        nombre_salida = "Vulnerabilidad_Nacional.parquet"
        gdf_nacional.to_parquet(nombre_salida)
        print(f"✅ ÉXITO: Archivo '{nombre_salida}' creado correctamente.")
        print(f"📊 Total de polígonos consolidados: {len(gdf_nacional)}")
    else:
        print("❌ No se pudo procesar ningún archivo válido.")

if __name__ == "__main__":
    consolidar_geojson_a_parquet()