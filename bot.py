# Bot de Apelaciones - Moderación (CON VIDEO ANALISIS)
import logging
import asyncio
import os
import re
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters, 
    ContextTypes
)
from gemini_client import (
    decidir_apelacion_con_video,
    decidir_apelacion_con_imagen,
    decidir_apelacion_texto,
    subir_video_gemini,
    subir_imagen_gemini,
    explicar_motivo_agente
)
from casos import iniciar_apelacion, obtener_estado_usuario, finalizar_apelacion, obtener_datos_usuario, actualizar_caso

# Token
TELEGRAM_TOKEN = "8791531690:AAE_LHSB3vF-2R37KBAu7LJ9Pa65QYMDfhg"

# Carpeta temporal
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CATEGORIAS = {
    "no_original": "©️ Contenido No Original",
    "baja_calidad": "📉 Baja Calidad",
    "spam": "🚫 Spam / Irrelevante",
    "otro": "⚙️ Otro Motivo"
}

# Regex para detectar URLs de TikTok / VM / YouTube
URL_REGEX = re.compile(
    r'https?://(?:www\.)?(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com|youtu\.be|youtube\.com)\S+',
    re.IGNORECASE
)

def descargar_video_url(url: str, output_path: str) -> bool:
    """Descarga un video desde una URL usando yt-dlp. Retorna True si tuvo éxito."""
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Error descargando video con yt-dlp: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = """👋 *Centro de Apelaciones y Soporte*
━━━━━━━━━━━━━━━━━━━━━━━
Hola. Bienvenido al sistema de gestión de apelaciones.
Seleccione el motivo de la sanción:"""
    keyboard = [[InlineKeyboardButton(text, callback_data=f"cat_{key}")] for key, text in CATEGORIAS.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(mensaje, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(mensaje, parse_mode='Markdown', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Selección de categoría
    if data.startswith("cat_"):
        categoria_key = data.replace("cat_", "")
        nombre_categoria = CATEGORIAS.get(categoria_key, "Otro")
        
        iniciar_apelacion(query.message.chat_id, query.from_user.username, categoria_key)
        
        mensaje = f"""📝 *Apelación: {nombre_categoria}*

Para que nuestro equipo pueda verificar su contenido, por favor **ENVÍE EL LINK DEL VIDEO, O EL VIDEO O IMAGEN** del contenido sancionado.

_Sube el video como archivo/video de Telegram, o la imagen directamente._"""
        
        await query.edit_message_text(mensaje, parse_mode='Markdown')

    # Respuesta "Sí, entendí el motivo"
    elif data == "entendio_si":
        await query.edit_message_text(
            "✅ Gracias por confirmarlo. Si necesitas iniciar una nueva apelación, usa /start.",
            parse_mode='Markdown'
        )
        finalizar_apelacion(query.message.chat_id)

    # Respuesta "No, no entendí el motivo"
    elif data == "entendio_no":
        chat_id = query.message.chat_id
        datos = obtener_datos_usuario(chat_id)

        await query.edit_message_text(
            "🔄 *Conectando con un agente...*\n\nUn miembro de nuestro equipo te explicará el motivo en un momento.",
            parse_mode='Markdown'
        )

        if not datos:
            await context.bot.send_message(
                chat_id,
                "⚠️ No pudimos recuperar los datos de tu caso. Por favor usa /start para iniciar una nueva apelación."
            )
            return

        decision  = datos.get("decision_final", "RECHAZADA")
        motivo    = datos.get("motivo_decision", "No se pudo recuperar el motivo.")
        categoria = datos.get("categoria", "otro")
        argumento = datos.get("argumento", "")

        loop = asyncio.get_running_loop()
        explicacion = await loop.run_in_executor(
            None, explicar_motivo_agente, decision, motivo, categoria, argumento
        )

        mensaje_agente = f"""💬 *Agente: Carlos — Equipo de Soporte*
━━━━━━━━━━━━━━━━━━━━━━━

{explicacion}

━━━━━━━━━━━━━━━━━━━━━━━
_Si necesitas iniciar una nueva apelación, usa /start._"""

        try:
            await context.bot.send_message(chat_id, mensaje_agente, parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id, mensaje_agente)

        finalizar_apelacion(chat_id)

async def recibir_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga el video enviado por el usuario"""
    chat_id = update.effective_chat.id
    datos = obtener_datos_usuario(chat_id)
    
    if not datos or datos.get("estado") != "esperando_video":
        await update.message.reply_text("⚠️ No estamos esperando un video en este momento. Use /start.")
        return

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("⚠️ Por favor envíe un archivo de video válido.")
        return

    msg = await update.message.reply_text("📥 *Descargando video para análisis...*", parse_mode='Markdown')
    
    file = await context.bot.get_file(video.file_id)
    file_path = os.path.join(TEMP_DIR, f"{chat_id}_{video.file_id}.mp4")
    await file.download_to_drive(file_path)
    
    actualizar_caso(chat_id, video_path=file_path, estado="esperando_argumento")
    
    await msg.edit_text("✅ *Video recibido.*\n\nAhora escriba su **ARGUMENTO** detallado explicando por qué es un error.", parse_mode='Markdown')

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga la imagen enviada por el usuario"""
    chat_id = update.effective_chat.id
    datos = obtener_datos_usuario(chat_id)

    if not datos or datos.get("estado") != "esperando_video":
        await update.message.reply_text("⚠️ No estamos esperando un archivo en este momento. Use /start.")
        return

    photo = update.message.photo[-1]
    msg = await update.message.reply_text("📥 *Descargando imagen para análisis...*", parse_mode='Markdown')

    file = await context.bot.get_file(photo.file_id)
    file_path = os.path.join(TEMP_DIR, f"{chat_id}_{photo.file_id}.jpg")
    await file.download_to_drive(file_path)

    actualizar_caso(chat_id, imagen_path=file_path, estado="esperando_argumento")

    await msg.edit_text("✅ *Imagen recibida.*\n\nAhora escriba su **ARGUMENTO** detallado explicando por qué es un error.", parse_mode='Markdown')

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = update.message.text
    datos = obtener_datos_usuario(chat_id)

    if not datos:
        return

    estado = datos.get("estado")

    if estado == "esperando_argumento":
        await procesar_apelacion(update, context, datos, texto)

    elif estado == "esperando_video":
        # Detectar si el usuario envió una URL de TikTok/YouTube
        match = URL_REGEX.search(texto)
        if match:
            url = match.group(0)
            msg = await update.message.reply_text(
                f"🔗 *Enlace detectado. Descargando video...*\n\n`{url}`\n\n_Esto puede tomar unos segundos._",
                parse_mode='Markdown'
            )
            file_path = os.path.join(TEMP_DIR, f"{chat_id}_url_video.mp4")

            loop = asyncio.get_running_loop()
            exito = await loop.run_in_executor(None, descargar_video_url, url, file_path)

            if exito:
                actualizar_caso(chat_id, video_path=file_path, estado="esperando_argumento")
                await msg.edit_text(
                    "✅ *Video descargado correctamente.*\n\nAhora escriba su **ARGUMENTO** detallado explicando por qué cree que la sanción es un error.",
                    parse_mode='Markdown'
                )
            else:
                await msg.edit_text(
                    "⚠️ No pudimos descargar el video desde ese enlace. Puede que sea privado o no compatible.\n\n"
                    "Por favor envíe el video directamente como archivo adjunto en Telegram."
                )
        else:
            await update.message.reply_text(
                "⚠️ Estamos esperando que envíe el video, una imagen, o un enlace de TikTok/YouTube."
            )

async def procesar_apelacion(update: Update, context: ContextTypes.DEFAULT_TYPE, datos, argumento):
    chat_id = update.effective_chat.id
    categoria = datos.get("categoria", "otro")
    video_path = datos.get("video_path")
    imagen_path = datos.get("imagen_path")

    msg_procesando = await update.message.reply_text(
        "⏳ *Analizando contenido...*\n\nNuestro equipo está visualizando el contenido y revisando su caso. Esto puede tomar tiempo, recibirás una notificación.",
        parse_mode='Markdown'
    )

    loop = asyncio.get_running_loop()

    if video_path and os.path.exists(video_path):
        video_file = await loop.run_in_executor(None, subir_video_gemini, video_path)
        if video_file:
            respuesta_raw = await loop.run_in_executor(None, decidir_apelacion_con_video, argumento, categoria, video_file)
        else:
            respuesta_raw = "Error técnico procesando el video."
    elif imagen_path and os.path.exists(imagen_path):
        imagen_file = await loop.run_in_executor(None, subir_imagen_gemini, imagen_path)
        if imagen_file:
            respuesta_raw = await loop.run_in_executor(None, decidir_apelacion_con_imagen, argumento, categoria, imagen_file)
        else:
            respuesta_raw = "Error técnico procesando la imagen."
    else:
        respuesta_raw = await loop.run_in_executor(None, decidir_apelacion_texto, argumento, categoria)

    # Parsear respuesta
    decision_final = "RECHAZADA"
    mensaje_usuario = str(respuesta_raw)
    
    try:
        if "DECISIÓN:" in respuesta_raw and "MENSAJE:" in respuesta_raw:
            partes = respuesta_raw.split("MENSAJE:")
            decision_final = partes[0].split("DECISIÓN:")[1].strip()
            mensaje_usuario = partes[1].strip().replace("---", "").strip()
    except:
        pass

    actualizar_caso(
        chat_id,
        estado="esperando_confirmacion",
        decision_final=decision_final,
        motivo_decision=mensaje_usuario,
        argumento=argumento
    )

    aprobada = "APROBADA" in decision_final.upper()
    icono = "✅" if aprobada else "❌"
    encabezado = "Hemos aprobado tu apelación." if aprobada else "No hemos podido aprobar tu apelación."
    
    await msg_procesando.delete()
    
    mensaje_final = f"""{icono} *RESOLUCIÓN DE APELACIÓN*
━━━━━━━━━━━━━━━━━━━━━━━

{encabezado}

*Motivo:* {mensaje_usuario}

_Atte. Equipo de Moderación_"""

    keyboard = [
        [
            InlineKeyboardButton("✅ Sí, entendí", callback_data="entendio_si"),
            InlineKeyboardButton("❌ No entendí", callback_data="entendio_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.message.reply_text(
            mensaje_final + "\n\n❓ *¿Entendió el motivo de esta resolución?*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except:
        await update.message.reply_text(
            mensaje_final + "\n\n¿Entendió el motivo de esta resolución?",
            reply_markup=reply_markup
        )
    
    # Limpiar archivos temporales
    for path in [video_path, imagen_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

def main():
    print("⚖️ Iniciando Moderación con VIDEO (v3.2)...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^entendio_"))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, recibir_video))
    application.add_handler(MessageHandler(filters.PHOTO, recibir_imagen))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    
    print("✅ Sistema en línea.")
    application.run_polling()

if __name__ == "__main__":
    main()
