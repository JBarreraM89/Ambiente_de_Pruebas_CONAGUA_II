import os
import requests
from bs4 import BeautifulSoup

# URL de la página de ordenamientos de CONAGUA
url_pagina = (
    "https://sigagis.conagua.gob.mx/Gas1/sections/ordenamientos_subsuelo.html"
)

# Carpeta de salida para los PDFs originales
output_dir = "ordenamientos_pdf_directos"
os.makedirs(output_dir, exist_ok=True)

print(f"Obteniendo contenido de: {url_pagina}")
response = requests.get(url_pagina)
response.encoding = "utf-8"
soup = BeautifulSoup(response.text, "html.parser")

tablas = soup.find_all("table")
contador = 0

for tabla in tablas:
  filas = tabla.find_all("tr")[1:]
  for fila in filas:
    columnas = fila.find_all("td")
    if len(columnas) >= 4:
      nombre_corto = columnas[0].get_text(strip=True)
      enlace_pdf = columnas[3].find("a")

      if enlace_pdf and enlace_pdf.get("href"):
        href = enlace_pdf["href"]
        pdf_url = (
            href
            if href.startswith("http")
            else f"https://sigagis.conagua.gob.mx/Gas1/sections/{href}"
        )

        # Limpiar nombre para el archivo de forma segura
        nombre_archivo = "".join(
            c for c in nombre_corto if c.isalnum() or c in (" ", "_", "-")
        ).strip()
        nombre_archivo = nombre_archivo.replace(" ", "_")[:50]
        if not nombre_archivo:
          nombre_archivo = f"documento_{contador}"

        print(f"Descargando: {nombre_corto}...")

        try:
          pdf_res = requests.get(pdf_url)
          if pdf_res.status_code == 200:
            pdf_filename = os.path.join(
                output_dir, f"{nombre_archivo}.pdf"
            )
            with open(pdf_filename, "wb") as f:
              f.write(pdf_res.content)
            contador += 1
          else:
            print(
                f"  -> No se pudo descargar (Código HTTP {pdf_res.status_code})"
            )

        except Exception as e:
          print(f"  -> Error en la descarga: {e}")

print(
    f"\n¡Proceso finalizado! Se descargaron {contador} archivos PDF"
    f" directamente en la carpeta '{output_dir}'."
)