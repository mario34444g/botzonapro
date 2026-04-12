# Sistema de Gestión de Casos Simplificado (Solo Apelaciones)
import json
import os
from datetime import datetime

ARCHIVO_CASOS = os.path.join(os.path.dirname(__file__), "data", "apelaciones.json")

def _asegurar_directorio():
    directorio = os.path.dirname(ARCHIVO_CASOS)
    if not os.path.exists(directorio):
        os.makedirs(directorio)

def _cargar_datos():
    _asegurar_directorio()
    if os.path.exists(ARCHIVO_CASOS):
        try:
            with open(ARCHIVO_CASOS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def _guardar_datos(datos):
    _asegurar_directorio()
    with open(ARCHIVO_CASOS, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def iniciar_apelacion(chat_id, username, categoria):
    """Inicia un proceso de apelación para el usuario"""
    datos = _cargar_datos()
    
    # Estado: 'esperando_video' (Nuevo paso 1)
    datos[str(chat_id)] = {
        "username": username,
        "estado": "esperando_video",
        "categoria": categoria,
        "video_path": None,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    _guardar_datos(datos)
    return True

def actualizar_caso(chat_id, **kwargs):
    """Actualiza datos de un caso activo"""
    datos = _cargar_datos()
    chat_id_str = str(chat_id)
    
    if chat_id_str in datos:
        for key, value in kwargs.items():
            datos[chat_id_str][key] = value
        _guardar_datos(datos)
        return True
    return False

def obtener_datos_usuario(chat_id):
    """Obtiene los datos completos del usuario"""
    datos = _cargar_datos()
    return datos.get(str(chat_id))

def obtener_estado_usuario(chat_id):
    """Obtiene el estado actual del usuario"""
    datos = _cargar_datos()
    usuario = datos.get(str(chat_id))
    if usuario:
        return usuario.get("estado")
    return None

def finalizar_apelacion(chat_id):
    """Borra el estado del usuario (apelación terminada)"""
    datos = _cargar_datos()
    if str(chat_id) in datos:
        del datos[str(chat_id)]
        _guardar_datos(datos)
