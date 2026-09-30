# -*- coding: utf-8 -*-
"""
Created on Wed Aug 12 12:45:51 2026

@author: dchable
"""

import pandas as pd
import io

def generar_excel_matriz(df_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, destino_salida=None):
    """
    Genera el archivo Excel de la matriz de cálculo.
    Si destino_salida es None, devuelve los bytes (en RAM). 
    Si se le pasa un string de ruta, lo guarda en el disco duro.
    """
    retornar_bytes = False
    if destino_salida is None:
        destino_salida = io.BytesIO()
        retornar_bytes = True

    try:
        writer = pd.ExcelWriter(destino_salida, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}})
    except TypeError:
        writer = pd.ExcelWriter(destino_salida, engine='xlsxwriter', options={'nan_inf_to_errors': True})
        
    with writer:
        workbook = writer.book
        f_cab = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        f_base = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'align': 'center'})
        f_bor = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'border': 1, 'align': 'center'})
        f_tot_tex = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right', 'valign': 'vcenter'})
        f_tot_num = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        f_pct = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'border': 1, 'align': 'center', 'num_format': '0.00%'})
        f_tot_pct = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'num_format': '0.00%'})
        f_met = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'font_color': '#1f497d', 'align': 'left'})

        df_resumen.to_excel(writer, sheet_name='Resumen_Balance', index=False)
        ws_res = writer.sheets['Resumen_Balance']
        ws_res.set_column('A:A', 40, f_base); ws_res.set_column('B:B', 20, f_base)
        for c, v in enumerate(df_resumen.columns.values): ws_res.write(0, c, v, f_cab)
        for r in range(1, len(df_resumen) + 1):
            for c in range(len(df_resumen.columns)): ws_res.write(r, c, df_resumen.iloc[r - 1, c], f_bor)

        def formatear_hoja(df, sheet_name, is_dvs=False, is_usos=False):
            if df.empty: return
            df = df.replace([float('inf'), float('-inf')], "").fillna("")
            inicio_fila_tabla = 2 if (is_dvs or is_usos) else 0
            
            if is_usos:
                df['Volumen [hm³/año]'] = pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
                suma_volumen = df['Volumen [hm³/año]'].sum()
                df['Porcentaje (%)'] = (df['Volumen [hm³/año]'] / suma_volumen) if suma_volumen > 0 else 0.0
                
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=inicio_fila_tabla)
            ws = writer.sheets[sheet_name]
            num_cols, num_rows = len(df.columns), len(df)
            
            if is_usos:
                ws.set_column(0, 0, 35, f_base); ws.set_column(1, 1, 25, f_base); ws.set_column(2, 2, 20, f_base) 
                ws.write(0, 0, f"Origen de datos: {fuente_b}", f_met); ws.write(0, 1, f"Año de info: {anio_b}", f_met)
            elif is_dvs:
                ws.set_column(0, num_cols - 1, 22, f_base)
                ws.write(0, 0, f"Año Base: {a_base}", f_met); ws.write(0, 1, f"Año Tope: {a_tope}", f_met); ws.write(0, 2, f"RDA: {rda} años", f_met)
            else: ws.set_column(0, num_cols - 1, 22, f_base)
            
            for col_num, value in enumerate(df.columns.values): ws.write(inicio_fila_tabla, col_num, value, f_cab)
            for row in range(1, num_rows + 1):
                fila_excel = inicio_fila_tabla + row
                for col in range(num_cols):
                    valor = df.iloc[row - 1, col]
                    if pd.isna(valor): valor = ""
                    if is_usos and col == (num_cols - 1): ws.write(fila_excel, col, valor, f_pct)
                    else: ws.write(fila_excel, col, valor, f_bor)
                
            fila_total = inicio_fila_tabla + num_rows + 1 
            if is_usos:
                ws.write(fila_total, 0, "Total", f_tot_tex)
                ws.write(fila_total, 1, pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').sum(), f_tot_num)
                ws.write(fila_total, 2, 1.0, f_tot_pct) 
            elif not is_dvs:
                ws.merge_range(fila_total, 0, fila_total, num_cols - 2, "Total", f_tot_tex)
                ws.write(fila_total, num_cols - 1, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
            else:
                if 'Límite 2 [m]' in df.columns:
                    idx_l2, idx_area = df.columns.get_loc('Límite 2 [m]'), df.columns.get_loc('Área [km²]')
                    idx_evm, idx_vol = df.columns.get_loc('Evolución Media [m]'), df.columns.get_loc('Volumen Parcial [hm³]')
                    ws.merge_range(fila_total, 0, fila_total, idx_l2, "Total", f_tot_tex)
                    ws.write(fila_total, idx_area, pd.to_numeric(df['Área [km²]'], errors='coerce').sum(), f_tot_num)
                    ws.merge_range(fila_total, idx_area + 1, fila_total, idx_evm, "Total", f_tot_tex)
                    ws.write(fila_total, idx_vol, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
                    fila_prom = fila_total + 1
                    ws.merge_range(fila_prom, 0, fila_prom, idx_vol - 1, "Promedio anual", f_tot_tex)
                    ws.write(fila_prom, idx_vol, dvs_anualizado, f_tot_num)

        formatear_hoja(df_eh, 'Entradas_Eh')
        formatear_hoja(df_eas, 'Entradas_Salobres_Eas')
        formatear_hoja(df_usos, 'Extraccion_Bombeo', is_usos=True)
        formatear_hoja(df_sh, 'Salidas_Sh')
        formatear_hoja(df_etr, 'Evapo_ETR')
        formatear_hoja(df_dvs, 'Almacenamiento_DVS', is_dvs=True)

    if retornar_bytes:
        return destino_salida.getvalue()