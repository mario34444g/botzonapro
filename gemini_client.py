# Cliente para la API de Gemini (google-genai SDK nuevo)
from google import genai
from google.genai import types
import time
import logging
import os


# Configuración — la API key viene de variable de entorno, NUNCA hardcodeada
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ Variable de entorno GEMINI_API_KEY no está definida.")

client = genai.Client(api_key=GEMINI_API_KEY)

logger = logging.getLogger(__name__)

# ============== REGLAS DE MODERACIÓN ==============
REGLAS_ORIGINALIDAD = """
✅ QUÉ SE CONSIDERA ORIGINAL:
- Producción propia: Videos diseñados, grabados y editados íntegramente por el creador.
- Aporte de valor único: Contenido que demuestre talento, experiencia o creatividad personal.
- Duración mínima: El video debe durar más de 1 minuto (60 segundos).
- Alta calidad técnica: Grabaciones con buena iluminación, audio claro y preferiblemente en resolución 1080p o superior.
- Uso creativo de material ajeno: Solo si hay edición significativa, comentarios originales o transformación sustancial.

❌ QUÉ NO SE CONSIDERA ORIGINAL (Causas de descalificación):
- Dúos (Duets) y Pegados (Stitches): No califican para monetización.
- Contenido resubido: Videos copiados de otros usuarios o plataformas sin cambios creativos.
- Ediciones mínimas: Cambiar solo velocidad, filtro sencillo, stickers o texto sobre video ajeno.
- Modo Foto y Carruseles: Videos que solo son imágenes estáticas o texto.
- Contenido repetitivo: Bucles de video (loops) o clips que se repiten.
- Marcas de agua externas: Videos con logotipos de otras redes o apps de edición.
- Música con copyright: Lip-syncs o videos donde música protegida suene más de un minuto.
- Contenido promocional: Anuncios, contenidos patrocinados o promociones pagadas.
"""

REGLAS_CALIDAD = """
⚠️ DEFICIENCIAS TÉCNICAS (Baja Calidad):
- Baja resolución: Videos borrosos, pixelados o con resolución inferior a 1080p.
- Audio deficiente: Sonido con ruido excesivo, distorsionado o incomprensible.
- Iluminación pobre: Videos demasiado oscuros o con luces que impiden ver claramente.

📉 FORMATOS "LOW-EFFORT" (Bajo Esfuerzo):
- Pantallas divididas: Dos clips juntos sin narrativa clara.
- Grabaciones de pantalla: Partidas de juegos sin comentario o navegación por apps.
- Pantallas en negro o estáticas: Imagen fija o fondo negro con audio.
- Reacciones irrelevantes: Creador solo asiente o reacciona mínimamente sin análisis.
- Modo Foto y diapositivas: Carruseles de imágenes estáticas, aunque tengan música.

🚫 COMPORTAMIENTO INADECUADO:
- Clickbait: Títulos o miniaturas engañosas sin contenido valioso.
- Contenido vulgar: Lenguaje ofensivo, gestos groseros o comportamiento sugerente.
- Spam y engaño: Videos que manipulan métricas o engañan usuarios.
"""

def subir_video_gemini(video_path):
    """Sube un video a Gemini y espera que esté listo"""
    try:
        logger.info(f"Subiendo archivo: {video_path}")
        video_file = client.files.upload(file=video_path)

        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            logger.error("Falló el procesamiento del video en Gemini.")
            return None

        logger.info(f"Video listo: {video_file.name}")
        return video_file

    except Exception as e:
        logger.error(f"Error subiendo video: {e}")
        return None

def subir_imagen_gemini(imagen_path):
    """Sube una imagen a Gemini y retorna el objeto de archivo"""
    try:
        logger.info(f"Subiendo imagen: {imagen_path}")
        imagen_file = client.files.upload(file=imagen_path)
        logger.info(f"Imagen lista: {imagen_file.name}")
        return imagen_file
    except Exception as e:
        logger.error(f"Error subiendo imagen: {e}")
        return None

def decidir_apelacion_con_imagen(argumento_usuario, categoria, imagen_file):
    """
    Decide sobre una apelación analizando la IMAGEN y el ARGUMENTO.
    """
    nombres_categorias = {
        "no_original": "Contenido No Original / Reutilizado",
        "baja_calidad": "Contenido de Baja Calidad / Poco esfuerzo",
        "spam": "Spam o Contenido Irrelevante",
        "otro": "Otro motivo"
    }
    nombre_cat = nombres_categorias.get(categoria, "Sanción General")

    if categoria == "no_original":
        reglas = REGLAS_ORIGINALIDAD
    elif categoria == "baja_calidad":
        reglas = REGLAS_CALIDAD
    else:
        reglas = REGLAS_ORIGINALIDAD + "\n" + REGLAS_CALIDAD

    razones_aprobada = [
        "El contenido revisado cumple con los lineamientos de originalidad y calidad establecidos.",
        "Tras una revisión detallada, no se encontraron infracciones que justifiquen la sanción aplicada.",
        "El argumento presentado y el contenido analizado son compatibles con nuestras políticas de moderación."
    ]
    razones_rechazada = [
        "El contenido no cumple con los lineamientos mínimos de originalidad requeridos.",
        "Se detectaron elementos que infringen nuestras políticas de calidad de contenido.",
        "El material presentado no aporta valor original según nuestros estándares de moderación.",
        "El argumento proporcionado no es suficiente para revertir la decisión de moderación."
    ]

    prompt = f"""Eres el sistema de moderación de una plataforma de contenido digital. Tu tarea es analizar visualmente la imagen adjunta y emitir una decisión DEFINITIVA sobre si la apelación procede.

Categoría de sanción: "{nombre_cat}"
Argumento del usuario: "{argumento_usuario}"

Lineamientos oficiales de moderación:
{reglas}

PASO 1 — ANÁLISIS VISUAL OBLIGATORIO (responde cada punto):
- ¿Se observan marcas de agua, logos o indicadores de otras plataformas?
- ¿El contenido parece grabado originalmente o es una captura/resubida?
- ¿La calidad técnica (resolución, iluminación, audio visual) es adecuada?
- ¿Se detectan elementos de duplicación, collage o pantalla dividida?
- ¿El argumento del usuario es coherente con lo que se observa en la imagen?

PASO 2 — DECISIÓN:
Basándote ÚNICAMENTE en lo observado y los lineamientos, decide con total certeza.
Si existe alguna duda significativa que no puedas resolver mirando la imagen, decide RECHAZADA.

PASO 3 — FORMATO DE RESPUESTA:
Devuelve SOLO esto, sin ningún texto adicional:

DECISIÓN: [APROBADA o RECHAZADA]
MENSAJE: [Elige UNA razón de la lista correspondiente y cópiala exactamente]

Si APROBADA, elige de: {razones_aprobada}
Si RECHAZADA, elige de: {razones_rechazada}
"""

    modelos_a_probar = ['gemini-2.5-flash']

    for nombre_modelo in modelos_a_probar:
        try:
            logger.info(f"Intentando usar modelo: {nombre_modelo}")
            response = client.models.generate_content(
                model=nombre_modelo,
                contents=[imagen_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1024
                )
            )
            return response.text
        except Exception as e:
            logger.warning(f"Fallo modelo {nombre_modelo}: {e}")
            continue

    return "Error: No se pudo generar respuesta con ninguno de los modelos disponibles."

def decidir_apelacion_con_video(argumento_usuario, categoria, video_file):
    """
    Decide sobre una apelación analizando el VIDEO y el ARGUMENTO.
    """
    nombres_categorias = {
        "no_original": "Contenido No Original / Reutilizado",
        "baja_calidad": "Contenido de Baja Calidad / Poco esfuerzo",
        "spam": "Spam o Contenido Irrelevante",
        "otro": "Otro motivo"
    }

    nombre_cat = nombres_categorias.get(categoria, "Sanción General")

    if categoria == "no_original":
        reglas = REGLAS_ORIGINALIDAD
    elif categoria == "baja_calidad":
        reglas = REGLAS_CALIDAD
    else:
        reglas = REGLAS_ORIGINALIDAD + "\n" + REGLAS_CALIDAD

    razones_aprobada = [
        "El contenido revisado cumple con los lineamientos de originalidad y calidad establecidos.",
        "Tras una revisión detallada, no se encontraron infracciones que justifiquen la sanción aplicada.",
        "El argumento presentado y el contenido analizado son compatibles con nuestras políticas de moderación."
    ]
    razones_rechazada = [
        "El contenido no cumple con los lineamientos mínimos de originalidad requeridos.",
        "Se detectaron elementos que infringen nuestras políticas de calidad de contenido.",
        "El material presentado no aporta valor original según nuestros estándares de moderación.",
        "El argumento proporcionado no es suficiente para revertir la decisión de moderación."
    ]

    prompt = f"""Eres el sistema de moderación de una plataforma de videos de formato corto. Tu tarea es analizar visualmente el video adjunto fotograma a fotograma y emitir una decisión DEFINITIVA y CONSISTENTE.

Categoría de sanción: "{nombre_cat}"
Argumento del usuario: "{argumento_usuario}"

Lineamientos oficiales de moderación:
{reglas}

PASO 1 — ANÁLISIS VISUAL DEL VIDEO (responde cada punto antes de decidir):
- Duración aproximada del video: ¿más o menos de 60 segundos?
- ¿Se observan marcas de agua, logos de TikTok, Instagram, YouTube u otras plataformas?
- ¿El video fue grabado originalmente o es una captura de pantalla de otro dispositivo/app?
- ¿Se detecta pantalla dividida (duet/stitch), collage, o video dentro de video?
- ¿La iluminación y la resolución son adecuadas (no borroso, no oscuro)?
- ¿El audio es claro y original, o es música de fondo dominante con lip-sync?
- ¿Hay evidencia de que el creador aparece, habla o crea activamente el contenido?
- ¿El argumento del usuario es coherente con lo que se observa en el video?

PASO 2 — DECISIÓN DETERMINISTA:
Basándote ÚNICAMENTE en la evidencia visual observada y los lineamientos:
- Si el video cumple la mayoría de los criterios positivos: APROBADA.
- Si el video incumple incluso UN criterio crítico (marcas de agua externas, screen recording, menos de 60s sin contenido original): RECHAZADA.
- En caso de duda, decide RECHAZADA.
Se CONSISTENTE: el mismo video siempre debe recibir la misma decisión.

PASO 3 — FORMATO DE RESPUESTA:
Devuelve SOLO esto, sin texto adicional:

DECISIÓN: [APROBADA o RECHAZADA]
MENSAJE: [Elige UNA razón de la lista y cópiala exactamente]

Si APROBADA, elige de: {razones_aprobada}
Si RECHAZADA, elige de: {razones_rechazada}
"""

    modelos_a_probar = ['gemini-2.5-flash']

    for nombre_modelo in modelos_a_probar:
        try:
            logger.info(f"Intentando usar modelo: {nombre_modelo}")
            response = client.models.generate_content(
                model=nombre_modelo,
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1024
                )
            )
            return response.text
        except Exception as e:
            logger.warning(f"Fallo modelo {nombre_modelo}: {e}")
            continue

    return "Error: No se pudo generar respuesta con ninguno de los modelos disponibles."

def decidir_apelacion_texto(argumento_usuario, categoria):
    """Fallback por si no hay video (solo texto)"""
    nombres_categorias = {
        "no_original": "Contenido No Original / Reutilizado",
        "baja_calidad": "Contenido de Baja Calidad / Poco esfuerzo",
        "spam": "Spam o Contenido Irrelevante",
        "otro": "Otro motivo"
    }
    nombre_cat = nombres_categorias.get(categoria, "Sanción General")

    if categoria == "no_original":
        reglas = REGLAS_ORIGINALIDAD
    elif categoria == "baja_calidad":
        reglas = REGLAS_CALIDAD
    else:
        reglas = REGLAS_ORIGINALIDAD + "\n" + REGLAS_CALIDAD

    razones_aprobada = [
        "El contenido revisado cumple con los lineamientos de originalidad y calidad establecidos.",
        "Tras una revisión detallada, no se encontraron infracciones que justifiquen la sanción aplicada.",
        "El argumento presentado es compatible con nuestras políticas de moderación."
    ]
    razones_rechazada = [
        "El contenido no cumple con los lineamientos mínimos de originalidad requeridos.",
        "Se detectaron elementos que infringen nuestras políticas de calidad de contenido.",
        "El material presentado no aporta valor original según nuestros estándares de moderación.",
        "El argumento proporcionado no es suficiente para revertir la decisión de moderación."
    ]

    prompt = f"""Eres el sistema de moderación de una plataforma de videos. El usuario no adjuntó video, solo un argumento de texto.

Categoría de sanción: "{nombre_cat}"
Argumento del usuario: "{argumento_usuario}"

Lineamientos:
{reglas}

INSTRUCCIONES:
- Sin video adjunto, la carga de la prueba recae en el argumento del usuario.
- Solo decide APROBADA si el argumento describe evidencia concreta, específica e irrefutable de que no hay infracción.
- En cualquier otro caso, decide RECHAZADA.
- Sé consistente: el mismo argumento siempre debe producir la misma decisión.

Devuelve SOLO esto:

DECISIÓN: [APROBADA o RECHAZADA]
MENSAJE: [Elige UNA razón de la lista y cópiala exactamente]

Si APROBADA, elige de: {razones_aprobada}
Si RECHAZADA, elige de: {razones_rechazada}
"""

    modelos_a_probar = ['gemini-2.5-flash']

    for nombre_modelo in modelos_a_probar:
        try:
            response = client.models.generate_content(
                model=nombre_modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1024
                )
            )
            return response.text
        except Exception as e:
            continue

    return "Error: No se pudo conectar con el sistema."


def explicar_motivo_agente(decision, motivo, categoria, argumento_usuario):
    """
    La IA actúa como agente humano de soporte y explica el motivo
    de la decisión en un solo párrafo claro y específico.
    """
    nombres_categorias = {
        "no_original": "Contenido No Original / Reutilizado",
        "baja_calidad": "Contenido de Baja Calidad / Poco esfuerzo",
        "spam": "Spam o Contenido Irrelevante",
        "otro": "Otro motivo"
    }
    nombre_cat = nombres_categorias.get(categoria, "Sanción General")

    if categoria == "no_original":
        reglas = REGLAS_ORIGINALIDAD
    elif categoria == "baja_calidad":
        reglas = REGLAS_CALIDAD
    else:
        reglas = REGLAS_ORIGINALIDAD + "\n" + REGLAS_CALIDAD

    estado_decision = "APROBADA" if "APROBADA" in decision.upper() else "RECHAZADA"

    prompt = f"""Eres Carlos, un agente del equipo de moderación. Un usuario no entendió por qué su apelación fue {estado_decision}.

Datos del caso:
- Categoría de sanción: {nombre_cat}
- Argumento del usuario: "{argumento_usuario}"
- Motivo oficial de la decisión: "{motivo}"

Lineamientos internos que aplicaron:
{reglas}

Escribe UN ÚNICO PÁRRAFO de máximo 4 oraciones que:
1. Indique claramente si la decisión fue APROBADA o RECHAZADA.
2. Mencione 1 o 2 elementos concretos y específicos que se observaron en el contenido (no inventes datos, base te en el motivo y la categoría).
3. Relacione esos elementos con el lineamiento específico que se infringe o cumple.
4. Use un tono directo y profesional, sin rodeos, sin listas, sin encabezados.

REGLAS ABSOLUTAS:
- NUNCA uses asteriscos, guiones, emojis ni formato markdown.
- NUNCA menciones que eres IA, bot o sistema automático. Eres Carlos.
- Escribe en segunda persona ("tu contenido", "tu video").
- El resultado debe ser UN solo bloque de texto corrido, sin saltos de línea.
"""

    modelos_a_probar = ['gemini-2.5-flash']

    for nombre_modelo in modelos_a_probar:
        try:
            response = client.models.generate_content(
                model=nombre_modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1024
                )
            )
            return response.text
        except Exception as e:
            continue

    return "Hola, soy Carlos del equipo de soporte. En este momento tenemos dificultades técnicas para brindarte más detalles. Por favor intenta nuevamente más tarde."
