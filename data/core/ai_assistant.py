# -*- coding: utf-8 -*-
"""
Created on Mon Aug  3 11:56:55 2026

@author: dchable
"""

# core/ai_assistant.py
import google.generativeai as genai
import streamlit as st
import os

def inicializar_ia():
    """Conecta con Google Gemini de manera segura y retorna el modelo disponible."""
    api_key = None
    if hasattr(st, "secrets"):
        api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
        
    if not api_key:
        return None, False

    try:
        genai.configure(api_key=api_key)
        # Buscar modelo Flash (más rápido) o cualquier otro generativo
        modelo_elegido = None
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    modelo_elegido = m.name
                    break
        if not modelo_elegido:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    modelo_elegido = m.name
                    break
                    
        if modelo_elegido:
            model = genai.GenerativeModel(modelo_elegido)
            return model, True
    except Exception as e:
        st.error(f"⚠️ Error de conexión con IA: {e}")
        return None, False
        
    return None, False

def generar_respuesta_stream(model, contexto, prompt):
    """Genera una respuesta en paquetes (chunks) para efecto máquina de escribir."""
    full_prompt = f"{contexto}\n\nPREGUNTA DEL USUARIO:\n{prompt}"
    response = model.generate_content(full_prompt, stream=True)
    for chunk in response:
        yield chunk.text