import logging
import requests
import json
import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración - Obtiene las credenciales de las variables de entorno
TELEGRAM_BOT_TOKEN = "8348563279:AAFyUN1oydrnpPy1p3CIFTv8hxlOcyzsoLg"
GEMINI_API_KEY = "AIzaSyASDpF32SZhn2fS8PoCvlExIES4qfj2UfY"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

# Railway provee esto automáticamente cuando agregas PostgreSQL
DATABASE_URL = "postgresql://mario_c3hr_user:7da4l9yOsmbCcn2n0h2YkeHLTqrDEp5c@dpg-d3osu4h5pdvs73a5upn0-a.oregon-postgres.render.com/mario_c3hr?sslmode=require"


def get_db_connection():
    """Obtiene conexión a PostgreSQL"""
    return psycopg2.connect(DATABASE_URL, sslmode='require')


def inicializar_db():
    """Inicializa la base de datos PostgreSQL"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla de vendedores verificados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendedores (
            user_id BIGINT PRIMARY KEY,
            numero_vendedor INTEGER UNIQUE,
            username TEXT,
            nombre_completo TEXT,
            fecha_verificacion TIMESTAMP,
            verificado_por BIGINT
        )
    ''')
    
    # Tabla de advertencias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS advertencias (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            mensaje TEXT,
            contexto TEXT,
            fecha TIMESTAMP,
            warn_count INTEGER
        )
    ''')
    
    # Tabla de apelaciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apelaciones (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            warn_id INTEGER,
            apelacion_texto TEXT,
            decision TEXT,
            fecha TIMESTAMP,
            FOREIGN KEY (warn_id) REFERENCES advertencias (id) ON DELETE CASCADE
        )
    ''')
    
    # Tabla de configuración
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor INTEGER
        )
    ''')
    
    # Inicializar contador
    cursor.execute("SELECT valor FROM configuracion WHERE clave='contador_vendedores'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('contador_vendedores', 0)")
    
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("✅ Base de datos PostgreSQL inicializada correctamente")


def obtener_contador_vendedores():
    """Obtiene el contador actual de vendedores"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM configuracion WHERE clave='contador_vendedores'")
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado[0] if resultado else 0


def incrementar_contador_vendedores():
    """Incrementa y devuelve el nuevo contador de vendedores"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE configuracion SET valor = valor + 1 WHERE clave='contador_vendedores' RETURNING valor")
    nuevo_valor = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return nuevo_valor


def verificar_vendedor(user_id, username, nombre_completo, verificado_por):
    """Verifica un vendedor en la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT numero_vendedor FROM vendedores WHERE user_id=%s", (user_id,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return None
    
    numero = incrementar_contador_vendedores()
    
    cursor.execute('''
        INSERT INTO vendedores (user_id, numero_vendedor, username, nombre_completo, fecha_verificacion, verificado_por)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (user_id, numero, username, nombre_completo, datetime.now(), verificado_por))
    
    conn.commit()
    cursor.close()
    conn.close()
    return numero


def desverificar_vendedor(user_id):
    """Desverifica un vendedor de la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT numero_vendedor FROM vendedores WHERE user_id=%s", (user_id,))
    resultado = cursor.fetchone()
    
    if resultado:
        cursor.execute("DELETE FROM vendedores WHERE user_id=%s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return resultado[0]
    
    cursor.close()
    conn.close()
    return None


def es_vendedor_verificado(user_id):
    """Verifica si un usuario es vendedor verificado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT numero_vendedor FROM vendedores WHERE user_id=%s", (user_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado[0] if resultado else None


def obtener_lista_vendedores():
    """Obtiene la lista completa de vendedores verificados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT numero_vendedor, username, nombre_completo, fecha_verificacion 
        FROM vendedores 
        ORDER BY numero_vendedor
    ''')
    vendedores = cursor.fetchall()
    cursor.close()
    conn.close()
    return vendedores


def agregar_advertencia(user_id, mensaje, contexto):
    """Agrega una advertencia a la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM advertencias WHERE user_id=%s", (user_id,))
    warn_count = cursor.fetchone()[0] + 1
    
    cursor.execute('''
        INSERT INTO advertencias (user_id, mensaje, contexto, fecha, warn_count)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    ''', (user_id, mensaje, contexto, datetime.now(), warn_count))
    
    warn_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return warn_id, warn_count


def obtener_advertencia(warn_id):
    """Obtiene información de una advertencia"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, mensaje, contexto, warn_count 
        FROM advertencias 
        WHERE id=%s
    ''', (warn_id,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado


def ya_apelo(user_id, warn_id):
    """Verifica si un usuario ya apeló una advertencia"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM apelaciones 
        WHERE user_id=%s AND warn_id=%s
    ''', (user_id, warn_id))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado is not None


def registrar_apelacion(user_id, warn_id, apelacion_texto, decision):
    """Registra una apelación en la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO apelaciones (user_id, warn_id, apelacion_texto, decision, fecha)
        VALUES (%s, %s, %s, %s, %s)
    ''', (user_id, warn_id, apelacion_texto, decision, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()


def quitar_advertencia(warn_id):
    """Elimina una advertencia de la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM advertencias WHERE id=%s", (warn_id,))
    conn.commit()
    cursor.close()
    conn.close()


def contar_advertencias(user_id):
    """Cuenta las advertencias activas de un usuario"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM advertencias WHERE user_id=%s", (user_id,))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count


def llamar_gemini(prompt: str) -> str:
    """Llama a la API de Gemini para análisis de texto"""
    import time
    max_reintentos = 3
    
    for intento in range(max_reintentos):
        try:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            
            response = requests.post(
                GEMINI_API_URL,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
            elif response.status_code == 503:
                if intento < max_reintentos - 1:
                    tiempo_espera = (intento + 1) * 2
                    logger.warning(f"Modelo sobrecargado, reintentando en {tiempo_espera}s...")
                    time.sleep(tiempo_espera)
                    continue
                else:
                    return "ERROR"
            else:
                logger.error(f"Error en Gemini API: {response.status_code}")
                return "ERROR"
        except Exception as e:
            logger.error(f"Excepción al llamar Gemini: {e}")
            if intento < max_reintentos - 1:
                time.sleep(2)
                continue
            return "ERROR"
    
    return "ERROR"


async def verificar_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /verificar - Verifica a un vendedor"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("⛔ Solo los administradores pueden usar este comando.")
            return
    except TelegramError:
        await update.message.reply_text("❌ Error al verificar permisos.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "ℹ️ Por favor, responde al mensaje de un usuario con /verificar para verificarlo como vendedor."
        )
        return
    
    usuario_verificar = update.message.reply_to_message.from_user
    usuario_id = usuario_verificar.id
    username = usuario_verificar.username or "Sin username"
    nombre_completo = usuario_verificar.full_name
    
    numero = verificar_vendedor(usuario_id, username, nombre_completo, user_id)
    
    if numero is None:
        numero_existente = es_vendedor_verificado(usuario_id)
        await update.message.reply_text(
            f"⚠️ El usuario ya está verificado como VENDEDOR {numero_existente}."
        )
        return
    
    try:
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=usuario_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_pin_messages=True,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False,
            can_manage_topics=False
        )
        
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=usuario_id,
            custom_title=f"VENDEDOR {numero}"
        )
        titulo_asignado = True
        error_tipo = None
    except TelegramError as e:
        logger.error(f"No se pudo promocionar o asignar título: {e}")
        titulo_asignado = False
        error_tipo = str(e)
    
    fecha_formato = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    mensaje_respuesta = (
        f"✅ Usuario verificado exitosamente como VENDEDOR {numero}\n\n"
        f"👤 {nombre_completo}"
    )
    
    if username != "Sin username":
        mensaje_respuesta += f" (@{username})"
    
    mensaje_respuesta += f"\n📅 Fecha: {fecha_formato}\n"
    
    if titulo_asignado:
        mensaje_respuesta += f"🏷️ Título 'VENDEDOR {numero}' asignado correctamente\n"
    else:
        if error_tipo and "User_not_mutual_contact" in error_tipo:
            bot_username = (await context.bot.get_me()).username
            mensaje_respuesta += (
                f"⚠️ No se pudo asignar el título automáticamente\n\n"
                f"📲 El usuario debe iniciar el bot primero:\n"
                f"1️⃣ @{usuario_verificar.username or nombre_completo} debe abrir chat con @{bot_username}\n"
                f"2️⃣ Enviar /start al bot\n"
                f"3️⃣ Luego un admin debe usar /verificar nuevamente\n"
            )
        else:
            mensaje_respuesta += "⚠️ No se pudo asignar el título (verifica que el bot sea administrador con permisos)\n"
    
    mensaje_respuesta += "\nAhora puede ofrecer productos y servicios en el grupo."
    
    await update.message.reply_text(mensaje_respuesta)


async def desverificar_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /desverificar - Remueve la verificación de un vendedor"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("⛔ Solo los administradores pueden usar este comando.")
            return
    except TelegramError:
        await update.message.reply_text("❌ Error al verificar permisos.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "ℹ️ Por favor, responde al mensaje de un usuario con /desverificar para remover su verificación."
        )
        return
    
    usuario_desverificar = update.message.reply_to_message.from_user
    usuario_id = usuario_desverificar.id
    
    numero = desverificar_vendedor(usuario_id)
    
    if numero is None:
        await update.message.reply_text(
            "⚠️ Este usuario no está verificado como vendedor."
        )
        return
    
    # Quitar permisos de admin
    try:
        chat_member = await context.bot.get_chat_member(chat_id, usuario_id)
        if chat_member.status in ['administrator']:
            await context.bot.promote_chat_member(
                chat_id=chat_id,
                user_id=usuario_id,
                can_manage_chat=False,
                can_delete_messages=False,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=False,
                can_post_messages=False,
                can_edit_messages=False,
                can_pin_messages=False,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
                can_manage_topics=False
            )
    except TelegramError as e:
        logger.error(f"No se pudo quitar admin: {e}")
    
    await update.message.reply_text(
        f"✅ Se ha removido la verificación del VENDEDOR {numero}\n\n"
        f"👤 {usuario_desverificar.full_name}\n"
        f"El usuario ya no puede ofrecer productos o servicios."
    )


async def listav_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /listav - Muestra la lista de vendedores verificados"""
    vendedores = obtener_lista_vendedores()
    
    if not vendedores:
        await update.message.reply_text(
            "📋 LISTA DE VENDEDORES VERIFICADOS\n\n"
            "No hay vendedores verificados actualmente."
        )
        return
    
    mensaje = "📋 VENDEDORES VERIFICADOS Y AUTORIZADOS PARA VENDER\n\n"
    
    for numero, username, nombre, fecha in vendedores:
        fecha_formato = fecha.strftime('%d/%m/%Y')
        
        mensaje += f"🔹 VENDEDOR {numero} ✅ AUTORIZADO\n"
        mensaje += f"   👤 {nombre}\n"
        
        if username != "Sin username":
            mensaje += f"   📱 @{username}\n"
        
        mensaje += f"   📅 Verificado: {fecha_formato}\n\n"
    
    mensaje += f"━━━━━━━━━━━━━━━━━\n"
    mensaje += f"Total: {len(vendedores)} vendedores autorizados"
    
    if len(mensaje) > 4000:
        mensajes_divididos = [mensaje[i:i+4000] for i in range(0, len(mensaje), 4000)]
        for msg in mensajes_divididos:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text(mensaje)


async def analizar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analiza mensajes en el grupo para detectar intentos de venta no autorizados"""
    if not update.message or not update.message.text:
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    mensaje = update.message.text
    
    if es_vendedor_verificado(user_id):
        return
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status in ['administrator', 'creator']:
            return
    except TelegramError:
        pass
    
    if mensaje.startswith('/'):
        return
    
    prompt = f"""Eres un moderador de un grupo de Telegram. Tu tarea es detectar si un mensaje intenta vender, ofrecer productos/servicios, o solicitar compras de manera directa o indirecta.

Mensaje a analizar: "{mensaje}"

Reglas:
- Detecta ventas directas ("vendo", "compra aquí", "tengo para vender")
- Detecta insinuaciones de venta ("me dedico a...", "si necesitas X contáctame", "tengo disponible", "WhatsApp en bio")
- Detecta solicitudes de compra ("alguien vende...", "busco quien venda...")
- NO detectes conversaciones normales, preguntas generales o charla casual
- NO detectes cuando alguien menciona productos sin intención comercial

Responde SOLO con:
"VENTA" si detectas intención de vender/ofrecer/solicitar compra
"NORMAL" si es conversación normal sin intención comercial

Respuesta:"""

    resultado = llamar_gemini(prompt)
    
    if resultado == "ERROR":
        logger.error("Error al analizar mensaje con Gemini")
        return
    
    if "VENTA" in resultado.upper():
        contexto = update.message.reply_to_message.text if update.message.reply_to_message else None
        warn_id, warns_actuales = agregar_advertencia(user_id, mensaje, contexto)
        
        if warns_actuales == 1:
            bot_username = (await context.bot.get_me()).username
            url_apelacion = f"https://t.me/{bot_username}?start=apelar_{warn_id}_{chat_id}"
            keyboard = [[InlineKeyboardButton("⚖️ Apelar Decisión", url=url_apelacion)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"⚠️ ADVERTENCIA 1/2\n\n"
                f"🚫 USTED NO ESTÁ AUTORIZADO PARA VENDER\n\n"
                f"Se ha detectado un intento de venta sin autorización. Solo los vendedores verificados pueden ofrecer productos o servicios.\n\n"
                f"📋 Para convertirse en vendedor verificado, contacte a un administrador.\n\n"
                f"⚠️ Una segunda infracción resultará en silenciamiento preventivo y se recomendará su baneo.\n\n"
                f"Si considera que esto es un error, puede apelar esta decisión haciendo clic en el botón.",
                reply_markup=reply_markup
            )
        
        elif warns_actuales >= 2:
            bot_username = (await context.bot.get_me()).username
            url_apelacion = f"https://t.me/{bot_username}?start=apelar_{warn_id}_{chat_id}"
            keyboard = [[InlineKeyboardButton("⚖️ Apelar Decisión", url=url_apelacion)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                # Silenciar al usuario en lugar de banear
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions={
                        'can_send_messages': False,
                        'can_send_media_messages': False,
                        'can_send_polls': False,
                        'can_send_other_messages': False,
                        'can_add_web_page_previews': False,
                        'can_change_info': False,
                        'can_invite_users': False,
                        'can_pin_messages': False
                    }
                )
                
                await update.message.reply_text(
                    f"⚠️ SEGUNDA INFRACCIÓN DETECTADA\n\n"
                    f"🚫 USTED NO ESTÁ AUTORIZADO PARA VENDER\n\n"
                    f"El usuario ha sido silenciado preventivamente por violar las normas de venta en dos ocasiones.\n\n"
                    f"@admin Se recomienda banear a este usuario.\n\n"
                    f"Las reglas deben respetarse para mantener un ambiente profesional.\n\n"
                    f"Si considera que esto es un error, puede apelar esta decisión haciendo clic en el botón.",
                    reply_markup=reply_markup
                )
            except TelegramError as e:
                logger.error(f"Error al silenciar usuario: {e}")
                await update.message.reply_text(
                    "❌ No se pudo silenciar al usuario. Verifique que el bot tenga permisos de administrador."
                )


async def start_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    if context.args and len(context.args) > 0:
        parametro = context.args[0]
        
        if parametro.startswith("apelar_"):
            partes = parametro.replace("apelar_", "").split("_")
            warn_id = int(partes[0])
            grupo_chat_id = int(partes[1]) if len(partes) > 1 else None
            
            user_id = update.effective_user.id
            
            advertencia = obtener_advertencia(warn_id)
            if not advertencia:
                await update.message.reply_text("❌ Esta advertencia ya no está disponible.")
                return
            
            warn_user_id, mensaje, contexto, warn_count = advertencia
            
            if warn_user_id != user_id:
                await update.message.reply_text("⛔ Solo el usuario advertido puede apelar esta decisión.")
                return
            
            if ya_apelo(user_id, warn_id):
                await update.message.reply_text("⚠️ Ya has apelado esta advertencia anteriormente.")
                return
            
            context.user_data['apelacion_warn_id'] = warn_id
            context.user_data['apelacion_activa'] = True
            context.user_data['grupo_chat_id'] = grupo_chat_id
            
            mensaje_escapado = mensaje.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            
            await update.message.reply_text(
                f"📝 PROCESO DE APELACIÓN INICIADO\n\n"
                f"Has decidido apelar la advertencia recibida.\n\n"
                f"Mensaje original que fue detectado:\n"
                f'"{mensaje_escapado}"\n\n'
                f"Por favor, explica por qué consideras que tu mensaje NO violaba las normas de venta.\n\n"
                f"Sé claro y específico en tu explicación. Tu caso será revisado de manera imparcial."
            )
            return
    
    await update.message.reply_text(
        "🤖 Bot de Verificación de Vendedores\n\n"
        "✅ Base de datos PostgreSQL persistente\n"
        "📊 Tus datos están seguros\n\n"
        "Comandos disponibles:\n"
        "• /verificar - (Admins) Verificar vendedor\n"
        "• /desverificar - (Admins) Remover verificación\n"
        "• /listav - Ver vendedores verificados\n"
        "• /ayuda - Ayuda completa\n\n"
        "¡Respeta las normas!"
    )


async def ayuda_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda"""
    await update.message.reply_text(
        "ℹ️ AYUDA - Sistema de Vendedores\n\n"
        "Para Administradores:\n"
        "• /verificar - Responde a un mensaje para verificar vendedor\n"
        "• /desverificar - Responde a un mensaje para remover verificación\n"
        "• /listav - Ver todos los vendedores verificados\n\n"
        "Para Usuarios:\n"
        "• Solo vendedores verificados pueden ofrecer productos/servicios\n"
        "• Los administradores están exentos de advertencias\n"
        "• Si recibes una advertencia injusta, puedes apelar\n"
        "• 2 advertencias = silenciamiento preventivo\n\n"
        "Sistema de Apelaciones:\n"
        "• Haz clic en 'Apelar Decisión' si consideras la advertencia injusta\n"
        "• Explica tu caso en privado al bot\n"
        "• Tu mensaje será revisado objetivamente\n"
        "• Solo puedes apelar una vez por advertencia\n\n"
        "Normas:\n"
        "• No vendas sin estar verificado\n"
        "• No insinúes ventas indirectamente\n"
        "• No solicites compras si no eres vendedor\n\n"
        "Base de Datos:\n"
        "• PostgreSQL persistente en Railway\n"
        "• Historial de advertencias y apelaciones\n"
        "• Registro completo de vendedores\n\n"
        "Mantengamos ZONA PRO profesional y ordenada. 🎯"
    )


async def procesar_apelacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el mensaje de apelación del usuario"""
    user_id = update.effective_user.id
    apelacion_texto = update.message.text
    
    if 'apelacion_warn_id' not in context.user_data or not context.user_data.get('apelacion_activa'):
        return
    
    warn_id = context.user_data['apelacion_warn_id']
    
    advertencia = obtener_advertencia(warn_id)
    if not advertencia:
        await update.message.reply_text("❌ Esta advertencia ya no está disponible.")
        context.user_data.clear()
        return
    
    warn_user_id, mensaje_original, contexto, warn_count = advertencia
    grupo_chat_id = context.user_data.get('grupo_chat_id')
    
   
    
    await update.message.reply_text("⏳ Analizando tu apelación...")
    
    prompt = f"""Eres un juez imparcial revisando una apelación sobre una advertencia por intento de venta no autorizado en un grupo de Telegram.

MENSAJE ORIGINAL: "{mensaje_original}"
CONTEXTO PREVIO: "{contexto if contexto else 'Sin contexto'}"
APELACIÓN DEL USUARIO: "{apelacion_texto}"

REGLAS DEL GRUPO:
- Solo vendedores verificados pueden ofrecer productos/servicios
- Se prohíben ventas directas, insinuaciones de venta.
- Si es el usuario estaba preguntando por compra o quien vendía, es inocente. esta permitido.

TAREA:
Analiza objetivamente si el mensaje original REALMENTE violaba las normas o si fue una conversación normal sin intención comercial.

Responde SOLO con:
"ACEPTAR" si la apelación es válida y el mensaje NO violaba las normas
"RECHAZAR" si el mensaje SÍ violaba las normas y la advertencia fue justa

Respuesta:"""

    decision = llamar_gemini(prompt)
    
    if decision == "ERROR":
        await update.message.reply_text(
            "❌ Error al procesar la apelación. Intenta más tarde o contacta a un administrador."
        )
        return
    
    registrar_apelacion(user_id, warn_id, apelacion_texto, decision)
    usuario_nombre = update.effective_user.first_name
    
    if "ACEPTAR" in decision.upper():
        quitar_advertencia(warn_id)
        
        await update.message.reply_text(
            "✅ APELACIÓN ACEPTADA\n\n"
            "Tras revisar tu caso, se ha determinado que tu mensaje no violaba las normas del grupo.\n\n"
            "La advertencia ha sido retirada. Disculpa las molestias."
        )
        
        if grupo_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=grupo_chat_id,
                    text=f"✅ La apelación del usuario {usuario_nombre} ha sido ACEPTADA.\n\nLa advertencia ha sido retirada."
                )
            except TelegramError as e:
                logger.error(f"No se pudo notificar al grupo: {e}")
    else:
        await update.message.reply_text(
            "⚖️ APELACIÓN RECHAZADA\n\n"
            "Tras revisar tu caso, se ha confirmado que tu mensaje violaba las normas del grupo.\n\n"
            "En ZONA PRO mantenemos estándares y reglas que deben cumplirse para garantizar un ambiente profesional y ordenado.\n\n"
            "Te invitamos a leer las normas y respetarlas. Solo los vendedores verificados pueden ofrecer productos o servicios.\n\n"
            "La advertencia permanece activa."
        )
        
        if grupo_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=grupo_chat_id,
                    text=f"⚠️ La apelación del usuario {usuario_nombre} ha sido RECHAZADA.\n\n🚫 Este usuario NO está autorizado para vender."
                )
            except TelegramError as e:
                logger.error(f"No se pudo notificar al grupo: {e}")
    
    context.user_data.clear()


def main():
    """Función principal"""
    # Verificar variable de entorno
    if not DATABASE_URL:
        logger.error("❌ ERROR: Falta la variable DATABASE_URL")
        logger.error("Railway/Render la proveen automáticamente cuando agregas PostgreSQL")
        return
    
    # Inicializar base de datos
    try:
        inicializar_db()
    except Exception as e:
        logger.error(f"❌ Error al conectar con PostgreSQL: {e}")
        logger.error("Verifica que hayas agregado PostgreSQL en Railway/Render")
        return
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", start_comando))
    application.add_handler(CommandHandler("ayuda", ayuda_comando))
    application.add_handler(CommandHandler("verificar", verificar_comando))
    application.add_handler(CommandHandler("desverificar", desverificar_comando))
    application.add_handler(CommandHandler("listav", listav_comando))
    
    # Mensajes en grupos (análisis)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
        analizar_mensaje
    ))
    
    # Mensajes privados (apelaciones)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        procesar_apelacion
    ))
    
    # Iniciar bot
    logger.info("🚀 Bot iniciado correctamente con PostgreSQL")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()