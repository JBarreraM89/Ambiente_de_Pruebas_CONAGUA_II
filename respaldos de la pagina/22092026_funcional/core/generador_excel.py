# -*- coding: utf-8 -*-
"""
Generador de Excel para la Calculadora de Balance de Aguas Subterráneas.
Incluye creación de Tablero (Dashboard) oficial con Tablas Nativas y hojas de datos crudos.
"""

import pandas as pd
import io

def generar_excel_matriz(df_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, destino_salida=None, dnc_detalle=None, pme=5.0):
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
        
        # ==========================================
        # 1. FORMATOS PARA DASHBOARD OFICIAL
        # ==========================================
        # Colores de la cinta sincronizados con las tablas nativas
        f_ribbon_blue = workbook.add_format({'bg_color': '#9BC2E6', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 8})
        f_ribbon_ent  = workbook.add_format({'bg_color': '#9BBB59', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8}) # Verde Entradas
        f_ribbon_rep  = workbook.add_format({'bg_color': '#F79646', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 8}) # Naranja Bombeo
        f_ribbon_sal  = workbook.add_format({'bg_color': '#C0504D', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8}) # Rojo Salidas
        f_ribbon_alm  = workbook.add_format({'bg_color': '#4F81BD', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8}) # Azul Almacenamiento
        f_ribbon_dnc  = workbook.add_format({'bg_color': '#4BACC6', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 8}) # Aqua DNC        
        f_ribbon_val = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': '#,##0.0'})
        
        c_blue_tbl = '#C5D9F1'
        f_hdr_flujos = workbook.add_format({'bg_color': c_blue_tbl, 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 9})
        f_tot_flujos = workbook.add_format({'bg_color': c_blue_tbl, 'bold': True, 'font_color': '#002060', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_tot_flujos_num = workbook.add_format({'bg_color': c_blue_tbl, 'bold': True, 'font_color': '#002060', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9, 'num_format': '#,##0.0'})
        
        f_val_num1 = workbook.add_format({'num_format': '#,##0.0', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_val_num4 = workbook.add_format({'num_format': '#,##0.0000', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_val_txt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_val_pct = workbook.add_format({'num_format': '0.0', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        
        f_tbl_num1 = workbook.add_format({'num_format': '#,##0.0', 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_tbl_pct = workbook.add_format({'num_format': '0.0', 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        f_txt_bold = workbook.add_format({'bold': True, 'font_size': 10})

        # --- FORMATOS PARA CENTRAR ENCABEZADOS DE TABLAS NATIVAS ---
        # (Usando los colores exactos de la paleta Office 2007-2010 de tus capturas)
        f_hdr_nat_ent = workbook.add_format({'bg_color': '#9BBB59', 'font_color': 'white', 'bold': True, 'align': 'center', 'valign': 'vcenter'}) # Medio 11 (Verde)
        f_hdr_nat_sal = workbook.add_format({'bg_color': '#C0504D', 'font_color': 'white', 'bold': True, 'align': 'center', 'valign': 'vcenter'}) # Medio 10 (Rojo)
        f_hdr_nat_dnc = workbook.add_format({'bg_color': '#4BACC6', 'font_color': 'white', 'bold': True, 'align': 'center', 'valign': 'vcenter'}) # Medio 13 (Aqua)
        f_hdr_nat_alm = workbook.add_format({'bg_color': '#4F81BD', 'font_color': 'white', 'bold': True, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True}) # Medio 2 (Azul)
        f_hdr_nat_rep = workbook.add_format({'bg_color': '#F79646', 'font_color': 'white', 'bold': True, 'align': 'center', 'valign': 'vcenter'}) # Medio 14 (Naranja)

        ws = workbook.add_worksheet('Balance_Oficial')
        ws.set_zoom(75) 
        
        # Ajustar columnas
        ws.set_column('A:B', 15)
        ws.set_column('C:D', 12)
        ws.set_column('E:Z', 8)
        ws.set_column('AA:AC', 11)
        ws.set_column('B:I', 11) 
        ws.set_column('P:AA', 11) 
        
        # Extracción de valores
        valores = dict(zip(df_resumen['Concepto'], df_resumen['Volumen (hm³)'])) 
        def get_val(clave): return round(float(valores.get(clave, 0.0)), 1)
        
        v_rr, v_eh, v_rv = get_val("Recarga Vertical por Lluvia (Rr)"), get_val("Entradas Horizontales (Eh)"), get_val("Recarga Vertical Resultante (Rv)")
        v_ri, v_rtot = get_val("Recarga Incidental (Ri)"), get_val("RECARGA TOTAL (R)")
        v_b, v_etr, v_sh = get_val("Extracción / Bombeo (B)"), get_val("Evapotranspiración (ETR)"), get_val("Salidas Horizontales (Sh)")
        v_ssb, v_dfb, v_dm = get_val("Salidas Subterráneas (Ssb)"), get_val("Descarga Flujo Base (Dfb)"), get_val("Descarga Manantiales (Dm)")
        v_stot = get_val("DESCARGA TOTAL (S)")
        v_dnc = get_val("Descarga Natural Comprometida (DNC)")

        usos_dict = dict(zip(df_usos['Tipo de Uso'].str.upper(), df_usos['Volumen [hm³/año]']))
        def get_uso(nombre): return float(usos_dict.get(nombre, 0.0))

        # ==========================================
        # CINTA SUPERIOR (Filas 0 y 1)
        # ==========================================
        ws.set_row(0, 30)
        
        # Funciones matemáticas seguras para calcular los porcentajes sin error #¡DIV/0!
        def calc_pct(dnc_val, total_val):
            return round((dnc_val / total_val) * 100, 1) if total_val > 0 else 0.0
            
        # Extraemos valores de detalle de DNC de forma segura
        d_etr, d_sh, d_ssb, d_dfb, d_dm = 0, 0, 0, 0, 0
        if dnc_detalle and len(dnc_detalle) == 5:
            d_etr, d_sh, d_ssb, d_dfb, d_dm = dnc_detalle
            
        con_sumatoria = d_etr + d_sh + d_ssb + d_dfb + d_dm

        cinta = [
            ("ÁREA DEL ACUÍFERO (km²)", f_ribbon_blue, ""), 
            ("ÁREA DE BALANCE (km²)", f_ribbon_blue, ""),
            ("PRECIPITACIÓN MEDIA ANUAL (m)", f_ribbon_blue, ""), 
            ("TEMPERATURA MEDIA ANUAL (°C)", f_ribbon_blue, ""),
            ("Rr", f_ribbon_ent, v_rr), 
            ("Ri", f_ribbon_ent, v_ri), 
            ("Eh", f_ribbon_ent, v_eh), 
            ("Ehs", f_ribbon_ent, get_val("Entradas de Agua Salobre (Eas)")),
            ("Rv", f_ribbon_ent, v_rv), 
            ("R", f_ribbon_ent, v_rtot),
            ("USO PÚBLICO URBANO", f_ribbon_rep, get_uso("PÚBLICO URBANO")), 
            ("USO AGRÍCOLA", f_ribbon_rep, get_uso("AGRÍCOLA")),
            ("USO SERVICIOS", f_ribbon_rep, get_uso("SERVICIOS")), 
            ("USO DOMÉSTICO", f_ribbon_rep, get_uso("DOMÉSTICO")),
            ("USO INDUSTRIAL", f_ribbon_rep, get_uso("INDUSTRIAL")), 
            ("USO MÚLTIPLE", f_ribbon_rep, get_uso("DIFERENTES USOS") + get_uso("OTROS")),
            ("B", f_ribbon_sal, v_b), 
            ("ETR", f_ribbon_sal, v_etr), 
            ("Sh", f_ribbon_sal, v_sh), 
            ("Ssb", f_ribbon_sal, v_ssb), 
            ("fb", f_ribbon_sal, v_dfb), 
            ("Dm", f_ribbon_sal, v_dm),
            ("ΔV(S)", f_ribbon_alm, dvs_anualizado),
            ("DNC ETR", f_ribbon_dnc, d_etr), 
            ("%", f_ribbon_dnc, calc_pct(d_etr, v_etr)),
            ("DNC Sh", f_ribbon_dnc, d_sh), 
            ("%", f_ribbon_dnc, calc_pct(d_sh, v_sh)),
            ("DNC Ssb", f_ribbon_dnc, d_ssb), 
            ("%", f_ribbon_dnc, calc_pct(d_ssb, v_ssb)),
            ("DNC fb", f_ribbon_dnc, d_dfb), 
            ("%", f_ribbon_dnc, calc_pct(d_dfb, v_dfb)),
            ("DNC Dm", f_ribbon_dnc, d_dm), 
            ("%", f_ribbon_dnc, calc_pct(d_dm, v_dm)),
            ("CON SUMATORIA", f_ribbon_dnc, con_sumatoria),
            ("DNC TOTAL", f_ribbon_dnc, v_dnc)
        ]
        
        ws.set_column('AD:AK', 8)
        
        for col, (titulo, formato, valor) in enumerate(cinta):
            ws.write(0, col, titulo, formato)
            ws.write(1, col, valor, f_ribbon_val)

        # ==========================================
        # BLOQUE IZQUIERDO (Filas 3 a 10)
        # ==========================================
        ws.write('A4', 'Area del Acuífero (km²)', f_txt_bold)
        ws.write('A5', 'Area de balance (km²)', f_txt_bold)
        ws.write('A6', 'Precipitación media anual (m)', f_txt_bold)
        ws.write('A7', 'Temperatura media anual (°C)', f_txt_bold)
        ws.write('A8', 'L =', f_txt_bold)
        ws.write('A9', 'ETR (mm)=', f_txt_bold)
        ws.write('A10', 'P2 =', f_txt_bold)
        ws.write('A11', 'L2 =', f_txt_bold)

        # ==========================================
        # TABLA 1: EVAPOTRANSPIRACIÓN (Inicia Fila 13)
        # ==========================================
        r_etr = 13  
        ws.merge_range(r_etr, 1, r_etr, 7, 'EVAPOTRANSPIRACIÓN', f_hdr_flujos)
        hdr_etr = ['RANGOS DE\nPROFUNDIDAD (m)', 'PROFUNDIDAD\nMEDIA (m)', 'ÁREA\n(km²)', 'LÁMINA\nETR (m)', 'PROFUNDIDAD\nMÁXIMA DE\nEXTINCIÓN', '% ETR', 'VOLUMEN\nETR\n(hm³/año)']
        for col, txt in enumerate(hdr_etr): ws.write(r_etr+1, col+1, txt, f_hdr_flujos)
            
        r = r_etr + 2
        for _, row in df_etr.iterrows():
            
            # --- LÓGICA INTELIGENTE DE RANGOS DE PROFUNDIDAD ---
            lim_sup = row.get('Límite Sup [m]')
            lim_inf = row.get('Límite Inf [m]')
            
            if pd.notna(lim_sup) and pd.notna(lim_inf) and str(lim_inf).strip() != "":
                v_max = max(float(lim_sup), float(lim_inf))
                v_min = min(float(lim_sup), float(lim_inf))
                def fmt_num(v): return int(v) if v.is_integer() else v
                rango_txt = f"{fmt_num(v_max)} A {fmt_num(v_min)}"
            else:
                rango_txt = str(row.get('Polígono / Zona', ''))
            # -----------------------------------------------------

            ws.write(r, 1, rango_txt, f_val_txt)
            ws.write(r, 2, float(row.get('Prof. Media (PM) [m]', 0)) if not pd.isna(row.get('Prof. Media (PM) [m]')) else '', f_val_num1)
            ws.write(r, 3, float(row.get('Área [km²]', 0)) if not pd.isna(row.get('Área [km²]')) else '', f_val_num1)
            ws.write(r, 4, float(row.get('Lámina ETR [m]', 0)) if not pd.isna(row.get('Lámina ETR [m]')) else '', f_val_num4)
            
            # --- AQUÍ INYECTAMOS LA VARIABLE PME ---
            ws.write(r, 5, pme, f_val_num1) 
            
            ws.write(r, 6, float(row.get('% ETR', 0)) if not pd.isna(row.get('% ETR')) else '', f_val_pct)
            ws.write(r, 7, float(row.get('Volumen [hm³/año]', 0)) if not pd.isna(row.get('Volumen [hm³/año]')) else '', f_val_num1)
            r += 1
            
        ws.merge_range(r, 1, r, 6, 'Total', f_tot_flujos)
        ws.write(r, 7, v_etr, f_tot_flujos_num)

        # ==========================================
        # TABLA 2: ALMACENAMIENTO DVS (Inicia Fila 13)
        # ==========================================
        r_dvs = 13
        ws.merge_range(r_dvs, 10, r_dvs, 14, f'Cálculo del cambio de almacenamiento {a_base}-{a_tope}', f_hdr_flujos)
        hdr_dvs = ['Evolución\n(m)', 'Evolución\nmedia (m)', 'Área\n(km²)', 'Sy', 'DV(S)\n(hm³/año)']
        for col, txt in enumerate(hdr_dvs): ws.write(r_dvs+1, col+10, txt, f_hdr_flujos)
            
        r_d = r_dvs + 2
        for _, row in df_dvs.iterrows():
            
            # --- LÓGICA INTELIGENTE DE RANGOS DE EVOLUCIÓN (DVS) ---
            lim1 = row.get('Límite 1 [m]')
            lim2 = row.get('Límite 2 [m]')
            
            def fmt_num(v): 
                try:
                    val = float(v)
                    return int(val) if val.is_integer() else val
                except:
                    return v

            if pd.notna(lim1) and str(lim1).strip() != "":
                if pd.notna(lim2) and str(lim2).strip() != "":
                    # Si hay dos límites, los concatena con "a"
                    rango_dvs = f"{fmt_num(lim1)} a {fmt_num(lim2)}"
                else:
                    # Si solo hay un límite, pone el número directo
                    rango_dvs = str(fmt_num(lim1))
            else:
                # Si todo está vacío, usa el nombre del Rango
                rango_dvs = str(row.get('Polígono / Rango', ''))
            # -----------------------------------------------------

            ws.write(r_d, 10, rango_dvs, f_val_txt)
            ws.write(r_d, 11, float(row.get('Evolución Media [m]', 0)) if not pd.isna(row.get('Evolución Media [m]')) else '', f_val_num1)
            ws.write(r_d, 12, float(row.get('Área [km²]', 0)) if not pd.isna(row.get('Área [km²]')) else '', f_val_num1)
            ws.write(r_d, 13, float(row.get('Sy', 0)) if not pd.isna(row.get('Sy')) else '', f_val_num4)
            ws.write(r_d, 14, float(row.get('Volumen Parcial [hm³]', 0)) if not pd.isna(row.get('Volumen Parcial [hm³]')) else '', f_val_num1)
            r_d += 1
            
        ws.merge_range(r_d, 10, r_d, 13, 'TOTAL', f_tot_flujos)
        ws.write(r_d, 14, df_dvs['Volumen Parcial [hm³]'].sum() if not df_dvs.empty else 0, f_tot_flujos_num)
        ws.merge_range(r_d+1, 10, r_d+1, 13, 'Promedio anual', f_tot_flujos)
        ws.write(r_d+1, 14, dvs_anualizado, f_tot_flujos_num)

        # ==========================================
        # TABLAS DE RESUMEN NATIVAS (Inician Fila 13)
        # ==========================================
        r_res = 13
        
        ws.write(r_res-2, 16, 'Rv = B + Sh + ETR ± ΔV(S) - Eh - Ri', workbook.add_format({'bold': True, 'font_color': '#2F5597', 'font_size': 11}))
        
        # 1. ENTRADAS (Medio 11)
        data_entradas = [["Rv", v_rv], ["Rr", v_rr], ["Ri", v_ri], ["Eh", v_eh]]
        ws.add_table(r_res, 16, r_res + len(data_entradas) + 1, 17, {
            'data': data_entradas,
            'columns': [
                {'header': 'ENTRADAS', 'total_string': 'TOTAL', 'header_format': f_hdr_nat_ent}, 
                {'header': 'hm³', 'total_function': 'sum', 'format': f_tbl_num1, 'header_format': f_hdr_nat_ent}
            ],
            'style': 'Table Style Medium 11',
            'total_row': True
        })

        # 2. SALIDAS (Medio 10)
        data_salidas = [["B", v_b], ["ETR", v_etr], ["Sh", v_sh], ["Ssb", v_ssb], ["Dfb", v_dfb], ["Dm", v_dm]]
        ws.add_table(r_res, 19, r_res + len(data_salidas) + 1, 20, {
            'data': data_salidas,
            'columns': [
                {'header': 'SALIDAS', 'total_string': 'TOTAL', 'header_format': f_hdr_nat_sal}, 
                {'header': 'hm³', 'total_function': 'sum', 'format': f_tbl_num1, 'header_format': f_hdr_nat_sal}
            ],
            'style': 'Table Style Medium 10',
            'total_row': True
        })

        # ==========================================
        # 3. DNC hm3 (Estilo Medio 13) - VERSIÓN DEFINITIVA
        # ==========================================
        # 1. Escribimos los números DIRECTO en las celdas ANTES de crear la tabla
        if dnc_detalle and len(dnc_detalle) == 5:
            ws.write_blank(r_res + 1, 21, None, f_tbl_num1)     # Celda matemática vacía segura
            ws.write(r_res + 2, 21, dnc_detalle[0], f_tbl_num1) # Fila ETR
            ws.write(r_res + 3, 21, dnc_detalle[1], f_tbl_num1) # Fila Sh
            ws.write(r_res + 4, 21, dnc_detalle[2], f_tbl_num1) # Fila Ssb
            ws.write(r_res + 5, 21, dnc_detalle[3], f_tbl_num1) # Fila Dfb
            ws.write(r_res + 6, 21, dnc_detalle[4], f_tbl_num1) # Fila Dm

        # 2. Ahora envolvemos las celdas con el diseño de Tabla 
        ws.add_table(r_res, 21, r_res + len(data_salidas) + 1, 21, {
            'columns': [{'header': 'DNC hm³', 'total_function': 'sum', 'format': f_tbl_num1, 'header_format': f_hdr_nat_dnc}],
            'style': 'Table Style Medium 13',
            'total_row': True
        })

        # 4. CAMBIO DE ALMACENAMIENTO (Medio 2)
        data_alm = [["ΔV(S)", dvs_anualizado]]
        ws.add_table(r_res, 23, r_res + len(data_alm), 24, {
            'data': data_alm,
            'columns': [
                {'header': 'CAMBIO DE\nALMACENAMIENTO', 'header_format': f_hdr_nat_alm}, 
                {'header': 'hm³', 'format': f_tbl_num1, 'header_format': f_hdr_nat_alm}
            ],
            'style': 'Table Style Medium 2',
            'total_row': False
        })

        # ==========================================
        # TABLA 3: ENTRADAS HORIZONTALES
        # ==========================================
        r_eh = max(r, r_d) + 3
        ws.merge_range(r_eh, 1, r_eh, 8, f'ENTRADAS POR FLUJO SUBTERRÁNEO HORIZONTAL {anio_b}', f_hdr_flujos)
        hdr_flu = ['CELDA', 'LONGITUD B\n(m)', 'ANCHO a\n(m)', 'h2-h1\n(m)', 'Gradiente i', 'T\n(m²/s)', 'Q\n(m³/s)', 'VOLUMEN\n(hm³/año)']
        for col, txt in enumerate(hdr_flu): ws.write(r_eh+1, col+1, txt, f_hdr_flujos)
            
        r_e = r_eh + 2
        for _, row in df_eh.iterrows():
            t = float(row.get('Transmisividad T [m²/s]', 0))
            grad = float(row.get('Gradiente i', 0))
            long_b = float(row.get('Longitud B [m]', 0))
            q_val = (t * grad * long_b) if not (pd.isna(t) or pd.isna(grad) or pd.isna(long_b)) else 0

            ws.write(r_e, 1, str(row.get('Celda', '')), f_val_txt)
            ws.write(r_e, 2, long_b if not pd.isna(long_b) else '', f_val_num1)
            ws.write(r_e, 3, float(row.get('Ancho a [m]', 0)) if not pd.isna(row.get('Ancho a [m]')) else '', f_val_num1)
            ws.write(r_e, 4, float(row.get('h2-h1 [m]', 0)) if not pd.isna(row.get('h2-h1 [m]')) else '', f_val_num1)
            ws.write(r_e, 5, grad if not pd.isna(grad) else '', f_val_num4)
            ws.write(r_e, 6, t if not pd.isna(t) else '', f_val_num4)
            ws.write(r_e, 7, q_val, f_val_num4)
            ws.write(r_e, 8, float(row.get('Volumen [hm³/año]', 0)) if not pd.isna(row.get('Volumen [hm³/año]')) else '', f_val_num1)
            r_e += 1
        ws.merge_range(r_e, 1, r_e, 7, 'TOTAL', f_tot_flujos)
        ws.write(r_e, 8, v_eh, f_tot_flujos_num)

        # ==========================================
        # TABLA 4: SALIDAS HORIZONTALES 
        # ==========================================
        r_sh = r_e + 3
        ws.merge_range(r_sh, 1, r_sh, 8, f'SALIDAS POR FLUJO SUBTERRÁNEO HORIZONTAL {anio_b}', f_hdr_flujos)
        for col, txt in enumerate(hdr_flu): ws.write(r_sh+1, col+1, txt, f_hdr_flujos)
            
        r_s = r_sh + 2
        for _, row in df_sh.iterrows():
            t = float(row.get('Transmisividad T [m²/s]', 0))
            grad = float(row.get('Gradiente i', 0))
            long_b = float(row.get('Longitud B [m]', 0))
            q_val = (t * grad * long_b) if not (pd.isna(t) or pd.isna(grad) or pd.isna(long_b)) else 0

            ws.write(r_s, 1, str(row.get('Celda', '')), f_val_txt)
            ws.write(r_s, 2, long_b if not pd.isna(long_b) else '', f_val_num1)
            ws.write(r_s, 3, float(row.get('Ancho a [m]', 0)) if not pd.isna(row.get('Ancho a [m]')) else '', f_val_num1)
            ws.write(r_s, 4, float(row.get('h2-h1 [m]', 0)) if not pd.isna(row.get('h2-h1 [m]')) else '', f_val_num1)
            ws.write(r_s, 5, grad if not pd.isna(grad) else '', f_val_num4)
            ws.write(r_s, 6, t if not pd.isna(t) else '', f_val_num4)
            ws.write(r_s, 7, q_val, f_val_num4)
            ws.write(r_s, 8, float(row.get('Volumen [hm³/año]', 0)) if not pd.isna(row.get('Volumen [hm³/año]')) else '', f_val_num1)
            r_s += 1
        ws.merge_range(r_s, 1, r_s, 7, 'TOTAL', f_tot_flujos)
        ws.write(r_s, 8, v_sh, f_tot_flujos_num)

        # ==========================================
        # TABLA BOMBEO REPDA (Medio 14) 
        # ==========================================
        r_b = max(r_res + len(data_salidas) + 2, r_eh) + 1
        ws.write(r_b, 19, f'BOMBEO REPDA {anio_b}', f_txt_bold)
        
        data_bombeo = []
        df_usos['Volumen [hm³/año]'] = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0)
        for _, row in df_usos.iterrows():
            uso_val = float(row.get('Volumen [hm³/año]', 0))
            if uso_val > 0:
                pct = (uso_val / v_b * 100) if v_b > 0 else 0
                data_bombeo.append([str(row.get('Tipo de Uso', '')), uso_val, pct])
                
        if not data_bombeo: data_bombeo = [["Sin Usos", 0.0, 0.0]]
            
        ws.add_table(r_b+1, 19, r_b+1 + len(data_bombeo) + 1, 21, {
            'data': data_bombeo,
            'columns': [
                {'header': 'USO', 'total_string': 'VOL TOTAL hm³', 'header_format': f_hdr_nat_rep},
                {'header': 'hm³', 'total_function': 'sum', 'format': f_tbl_num1, 'header_format': f_hdr_nat_rep},
                {'header': '%', 'total_function': 'sum', 'format': f_tbl_pct, 'header_format': f_hdr_nat_rep}
            ],
            'style': 'Table Style Medium 14',
            'total_row': True
        })

        # ==========================================
        # FORMATOS PARA HOJAS DE DATOS CRUDOS
        # ==========================================
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
        for row_idx in range(1, len(df_resumen) + 1):
            for c in range(len(df_resumen.columns)): ws_res.write(row_idx, c, df_resumen.iloc[row_idx - 1, c], f_bor)

        def formatear_hoja(df, sheet_name, is_dvs=False, is_usos=False):
            if df.empty: return
            df = df.replace([float('inf'), float('-inf')], "").fillna("")
            inicio_fila_tabla = 2 if (is_dvs or is_usos) else 0
            
            if is_usos:
                df['Volumen [hm³/año]'] = pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
                suma_volumen = df['Volumen [hm³/año]'].sum()
                df['Porcentaje (%)'] = (df['Volumen [hm³/año]'] / suma_volumen) if suma_volumen > 0 else 0.0
                
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=inicio_fila_tabla)
            ws_hoja = writer.sheets[sheet_name]
            num_cols, num_rows = len(df.columns), len(df)
            
            if is_usos:
                ws_hoja.set_column(0, 0, 35, f_base); ws_hoja.set_column(1, 1, 25, f_base); ws_hoja.set_column(2, 2, 20, f_base) 
                ws_hoja.write(0, 0, f"Origen de datos: {fuente_b}", f_met); ws_hoja.write(0, 1, f"Año de info: {anio_b}", f_met)
            elif is_dvs:
                ws_hoja.set_column(0, num_cols - 1, 22, f_base)
                ws_hoja.write(0, 0, f"Año Base: {a_base}", f_met); ws_hoja.write(0, 1, f"Año Tope: {a_tope}", f_met); ws_hoja.write(0, 2, f"RDA: {rda} años", f_met)
            else: ws_hoja.set_column(0, num_cols - 1, 22, f_base)
            
            for col_num, value in enumerate(df.columns.values): ws_hoja.write(inicio_fila_tabla, col_num, value, f_cab)
            for row in range(1, num_rows + 1):
                fila_excel = inicio_fila_tabla + row
                for col in range(num_cols):
                    valor = df.iloc[row - 1, col]
                    if pd.isna(valor): valor = ""
                    if is_usos and col == (num_cols - 1): ws_hoja.write(fila_excel, col, valor, f_pct)
                    else: ws_hoja.write(fila_excel, col, valor, f_bor)
                
            fila_total = inicio_fila_tabla + num_rows + 1 
            if is_usos:
                ws_hoja.write(fila_total, 0, "Total", f_tot_tex)
                ws_hoja.write(fila_total, 1, pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').sum(), f_tot_num)
                ws_hoja.write(fila_total, 2, 1.0, f_tot_pct) 
            elif not is_dvs:
                ws_hoja.merge_range(fila_total, 0, fila_total, num_cols - 2, "Total", f_tot_tex)
                ws_hoja.write(fila_total, num_cols - 1, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
            else:
                if 'Límite 2 [m]' in df.columns:
                    idx_l2, idx_area = df.columns.get_loc('Límite 2 [m]'), df.columns.get_loc('Área [km²]')
                    idx_evm, idx_vol = df.columns.get_loc('Evolución Media [m]'), df.columns.get_loc('Volumen Parcial [hm³]')
                    ws_hoja.merge_range(fila_total, 0, fila_total, idx_l2, "Total", f_tot_tex)
                    ws_hoja.write(fila_total, idx_area, pd.to_numeric(df['Área [km²]'], errors='coerce').sum(), f_tot_num)
                    ws_hoja.merge_range(fila_total, idx_area + 1, fila_total, idx_evm, "Total", f_tot_tex)
                    ws_hoja.write(fila_total, idx_vol, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
                    fila_prom = fila_total + 1
                    ws_hoja.merge_range(fila_prom, 0, fila_prom, idx_vol - 1, "Promedio anual", f_tot_tex)
                    ws_hoja.write(fila_prom, idx_vol, dvs_anualizado, f_tot_num)

        formatear_hoja(df_eh, 'Entradas_Eh')
        formatear_hoja(df_eas, 'Entradas_Salobres_Eas')
        formatear_hoja(df_usos, 'Extraccion_Bombeo', is_usos=True)
        formatear_hoja(df_sh, 'Salidas_Sh')
        formatear_hoja(df_etr, 'Evapo_ETR')
        formatear_hoja(df_dvs, 'Almacenamiento_DVS', is_dvs=True)

    if retornar_bytes:
        return destino_salida.getvalue()