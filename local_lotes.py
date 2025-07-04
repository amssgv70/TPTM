import streamlit as st
import pandas as pd
import time
from io import BytesIO
import os
import google.generativeai as genai
import json # Necesario para parsear la respuesta JSON de Gemini

# === CONFIGURACIÓN BÁSICA DE LA APP ===
st.set_page_config(page_title="Clasificador de Quejas", layout="centered")

# === CONFIGURACIÓN DE GEMINI ===
# ADVERTENCIA: No es recomendable almacenar la API Key directamente en el código fuente
# para aplicaciones en producción. Para uso local, puedes definirla aquí.
# Reemplaza "TU_API_KEY_DE_GEMINI_AQUI" con tu clave real.
API_KEY = "TU_API_KEY_DE_GEMINI_AQUI"

if not API_KEY or API_KEY == "TU_API_KEY_DE_GEMINI_AQUI":
    st.error("❌ La API Key de Gemini no está configurada. Por favor, reemplaza 'TU_API_KEY_DE_GEMINI_AQUI' en el código con tu clave real.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- Define el modelo de Gemini a usar ---
# Puedes ajustar esto según tus necesidades. gemini-1.5-flash es más rápido y económico
# que gemini-1.5-pro, y es ideal para tareas de clasificación masiva.
GEMINI_MODEL = "gemini-1.5-flash-latest"

# === FUNCIÓN DE CLASIFICACIÓN INDIVIDUAL (PARA MODO MANUAL) ===
# Se mantiene la función original, ya que el modo manual clasifica una por una.
def clasificar_queja_con_razon(texto):
    prompt = f"""Leé la siguiente queja de un pasajero y devolvé SOLO:

1. La categoría más adecuada según esta lista centrándote en la causa raíz:
- Servicio Operativo y Frecuencia
- Infraestructura y Mantenimiento
- Seguridad y Control
- Atención al Usuario
- Otros
- Conducta de Terceros
- Incidentes y Emergencias
- Accesibilidad y Público Vulnerable
- Personal y Desempeño Laboral
- Ambiente y Confort
- Tarifas y Boletos

2. Una breve razón de por qué fue clasificada así.

Formato de salida:
Categoría: <nombre de categoría>
Razón: <explicación>

Texto: {texto}
"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        respuesta = response.text.strip()

        categoria, razon = "", ""
        for linea in respuesta.splitlines():
            if linea.lower().startswith("categoría:") or linea.lower().startswith("categoria:"):
                categoria = linea.split(":", 1)[1].strip()
            elif linea.lower().startswith("razón:") or linea.lower().startswith("razon:"):
                razon = linea.split(":", 1)[1].strip()
        return categoria, razon

    except Exception as e:
        print(f"DEBUG: Error en clasificar_queja_con_razon para texto '{texto[:50]}...': {e}") # Debugging
        return "ERROR", str(e)

# --- NUEVA FUNCIÓN DE CLASIFICACIÓN POR LOTES ---
def clasificar_lote_con_gemini(textos_lote, model_name=GEMINI_MODEL):
    """
    Clasifica un lote de textos usando la API de Gemini, solicitando una respuesta JSON.

    Args:
        textos_lote (list): Una lista de cadenas de texto a clasificar.
        model_name (str): Nombre del modelo de Gemini a usar.

    Returns:
        list: Una lista de diccionarios, donde cada diccionario contiene
              'id', 'categoria' y 'razon' para cada texto clasificado.
              Devuelve una lista vacía si hay un error.
    """
    # El prompt ahora pide una respuesta JSON con un ID para cada queja.
    # Es crucial que Gemini entienda que debe clasificar CADA elemento de la lista.
    prompt_base = f"""Clasifica los siguientes comentarios de pasajeros.
    Para cada comentario, devuelve la categoría más adecuada según la causa raíz y una breve razón.

    Categorías permitidas:
    - Servicio Operativo y Frecuencia
    - Infraestructura y Mantenimiento
    - Seguridad y Control
    - Atención al Usuario
    - Otros
    - Conducta de Terceros
    - Incidentes y Emergencias
    - Accesibilidad y Público Vulnerable
    - Personal y Desempeño Laboral
    - Ambiente y Confort
    - Tarifas y Boletos

    Tu respuesta debe ser una lista de objetos JSON. Cada objeto debe tener:
    - "id": Un número entero que corresponde al índice del comentario en la lista original (empezando por 0).
    - "categoria": La categoría asignada.
    - "razon": Una breve explicación de la clasificación.

    Comentarios a clasificar:
    """

    # Construye la parte de los comentarios del prompt
    comentarios_en_prompt = ""
    for idx, texto in enumerate(textos_lote):
        comentarios_en_prompt += f"{idx}: \"{texto}\"\n"

    prompt_final = prompt_base + comentarios_en_prompt

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt_final)
        respuesta_json_str = response.text.strip()

        # Asegúrate de que la respuesta es un JSON válido.
        # A veces Gemini puede añadir texto antes o después del JSON.
        # Buscamos el primer '[' y el último ']' para extraer el JSON puro.
        start_idx = respuesta_json_str.find('[')
        end_idx = respuesta_json_str.rfind(']')
        if start_idx == -1 or end_idx == -1:
            raise ValueError("La respuesta de Gemini no contiene un JSON válido.")

        json_puro = respuesta_json_str[start_idx : end_idx + 1]

        # st.write(f"DEBUG: Respuesta JSON de Gemini (parte inicial):\n{json_puro[:500]}") # Debugging
        clasificaciones = json.loads(json_puro)

        # Validar que cada clasificación tenga los campos esperados
        for item in clasificaciones:
            if not all(k in item for k in ['id', 'categoria', 'razon']):
                raise ValueError(f"Objeto JSON incompleto: {item}")
        
        return clasificaciones

    except json.JSONDecodeError as e:
        print(f"DEBUG: Error al decodificar JSON de Gemini: {e}")
        print(f"DEBUG: Respuesta cruda: {respuesta_json_str}")
        return [{"id": i, "categoria": "ERROR_JSON", "razon": str(e)} for i in range(len(textos_lote))]
    except ValueError as e:
        print(f"DEBUG: Error de validación o formato en la respuesta de Gemini: {e}")
        print(f"DEBUG: Respuesta cruda: {respuesta_json_str}")
        return [{"id": i, "categoria": "ERROR_FORMATO", "razon": str(e)} for i in range(len(textos_lote))]
    except Exception as e:
        print(f"DEBUG: Error inesperado en clasificar_lote_con_gemini: {e}")
        return [{"id": i, "categoria": "ERROR_API", "razon": str(e)} for i in range(len(textos_lote))]

# --- Calcula el tamaño del prompt para estimar tokens ---
def estimar_tokens_prompt(prompt_base_template, ejemplo_texto, num_ejemplos):
    """
    Estima el número de tokens que ocuparía un prompt con un número dado de ejemplos.
    Esta es una estimación simple, no un cálculo exacto de tokens de la API.
    """
    # Construir un prompt de ejemplo para estimar su longitud
    ejemplo_lote = [ejemplo_texto] * num_ejemplos
    comentarios_en_prompt = ""
    for idx, texto in enumerate(ejemplo_lote):
        comentarios_en_prompt += f"{idx}: \"{texto}\"\n"
    
    prompt_ejemplo = prompt_base_template + comentarios_en_prompt
    return len(prompt_ejemplo.split()) # Contar palabras como una proxy de tokens

# === INTERFAZ STREAMLIT ===
st.title("🧾 Clasificador de Quejas de Pasajeros")

modo = st.radio("¿Qué querés hacer?", ["📝 Clasificar una queja manualmente", "📂 Clasificar archivo Excel/CSV"])

# === MODO 1: CLASIFICACIÓN MANUAL ===
if modo == "📝 Clasificar una queja manualmente":
    texto = st.text_area("✏️ Ingresá una queja", height=200)

    if st.button("📊 Clasificar queja"):
        if not texto.strip():
            st.warning("Ingresá una queja antes de clasificar.")
        else:
            with st.spinner("Clasificando..."):
                categoria, razon = clasificar_queja_con_razon(texto)
            if categoria == "ERROR":
                st.error(f"❌ Error: {razon}")
            else:
                st.success("✅ Clasificación exitosa")
                st.write(f"**📌 Categoría:** {categoria}")
                st.write(f"**💬 Razón:** {razon}")

# === MODO 2: CLASIFICACIÓN POR ARCHIVO ===
else:
    archivo = st.file_uploader("📁 Subí un archivo Excel (.xlsx) o CSV (.csv)", type=["xlsx", "csv"])

    if archivo:
        if archivo.name.endswith(".csv"):
            df = pd.read_csv(archivo)
        else:
            df = pd.read_excel(archivo)

        st.write("✅ Archivo cargado. Columnas:")
        st.write(df.columns.tolist())

        columna = st.selectbox("Seleccioná la columna con las quejas:", df.columns)
        
        # --- Nuevo control para tokens_por_request ---
        st.info("Configurá el número máximo de tokens por solicitud a Gemini. Más tokens pueden procesar más quejas a la vez, pero tienen un costo y un límite del modelo.")
        tokens_por_request = st.slider(
            "Tokens máximos por solicitud a Gemini (incluye prompt y respuesta):",
            min_value=1000, max_value=32000, value=8000, step=500
        )
        
        # Se elimina el slider de espera y se fija el valor a 0.0 para no añadir retrasos artificiales
        espera = 0.0

        if st.button("🚀 Clasificar archivo"):
            # Lógica para determinar el tamaño del lote dinámicamente
            # Necesitamos estimar cuántas quejas caben en 'tokens_por_request'
            # Esta es una heurística; la implementación real de tokens puede variar.
            # Asumimos una queja promedio de 20 palabras/tokens, y que la respuesta agrega 10 tokens por queja.
            # Y que el prompt base ocupa unos 200 tokens (estimación).
            
            # Estimación del prompt base (sin los comentarios variables)
            prompt_base_estimacion = f"""Clasifica los siguientes comentarios de pasajeros.
            Para cada comentario, devuelve la categoría más adecuada según la causa raíz y una breve razón.

            Categorías permitidas:
            - Servicio Operativo y Frecuencia
            - Infraestructura y Mantenimiento
            - Seguridad y Control
            - Atención al Usuario
            - Otros
            - Conducta de Terceros
            - Incidentes y Emergencias
            - Accesibilidad y Público Vulnerable
            - Personal y Desempeño Laboral
            - Ambiente y Confort
            - Tarifas y Boletos

            Tu respuesta debe ser una lista de objetos JSON. Cada objeto debe tener:
            - "id": Un número entero que corresponde al índice del comentario en la lista original (empezando por 0).
            - "categoria": La categoría asignada.
            - "razon": Una breve explicación de la clasificación.

            Comentarios a clasificar:
            """
            
            # Usaremos el `count_tokens` del SDK de Gemini para una estimación más precisa si el modelo lo soporta,
            # o una heurística basada en la longitud del texto.
            try:
                model_token_counter = genai.GenerativeModel(GEMINI_MODEL)
                prompt_base_tokens_obj = model_token_counter.count_tokens(prompt_base_estimacion)
                prompt_base_tokens = prompt_base_tokens_obj.total_tokens
                # st.write(f"DEBUG: Tokens del prompt base estimado: {prompt_base_tokens}")
            except Exception as e:
                # Fallback a estimación heurística si count_tokens falla o no está disponible para el modelo
                print(f"DEBUG: No se pudo usar count_tokens para el modelo {GEMINI_MODEL}: {e}. Usando heurística.")
                prompt_base_tokens = len(prompt_base_estimacion.split()) * 1.5 # Factor de ajuste

            # Estimación de tokens por cada comentario y su respuesta esperada
            # 1.5 es un factor común para pasar de palabras a tokens en español.
            # Se asume que una queja promedio tendrá ~30 palabras y su respuesta ~15 palabras.
            # Total de tokens por queja + respuesta esperada
            tokens_por_queja_y_respuesta = (30 * 1.5) + (15 * 1.5) + len("{\"id\": 0, \"categoria\": \"\", \"razon\": \"\"},".split()) 
            
            # Calcular cuántos tokens quedan para las quejas y sus respuestas
            tokens_disponibles_para_contenido = tokens_por_request - prompt_base_tokens
            
            # Calcular el tamaño del lote (número de quejas por solicitud)
            if tokens_disponibles_para_contenido <= 0 or tokens_por_queja_y_respuesta <= 0:
                st.error("Error al calcular el tamaño del lote. Ajusta los tokens máximos por solicitud o revisa el prompt.")
                st.stop()

            # Asegurarse de que no sea cero para evitar división por cero
            num_quejas_por_lote = max(1, int(tokens_disponibles_para_contenido / tokens_por_queja_y_respuesta))
            
            # Un límite máximo para el lote para evitar problemas de memoria o respuestas gigantes
            num_quejas_por_lote = min(num_quejas_por_lote, 100) # Límite práctico, ajustar si es necesario

            st.info(f"Se procesarán aproximadamente **{num_quejas_por_lote} quejas por cada solicitud** a Gemini, basándose en los {tokens_por_request} tokens configurados.")

            # --- Preparación para la clasificación por lotes ---
            total = len(df)
            todas_las_categorias = [""] * total # Inicializa con el tamaño total
            todas_las_razones = [""] * total   # Inicializa con el tamaño total
            
            # Convertir la columna de quejas a tipo string para evitar errores con tipos mixtos
            quejas_a_procesar = df[columna].astype(str).tolist()

            progreso = st.progress(0)
            estado = st.empty()
            proceso_completado_exitosamente = False

            errores_consecutivos = 0
            limite_errores = 5 # Reducido para ser más sensible a problemas de API

            try:
                # Iterar sobre los lotes
                for i_lote_inicio in range(0, total, num_quejas_por_lote):
                    i_lote_fin = min(i_lote_inicio + num_quejas_por_lote, total)
                    lote_actual_textos = quejas_a_procesar[i_lote_inicio:i_lote_fin]
                    
                    estado.text(f"Clasificando lote de quejas: {i_lote_inicio + 1} a {i_lote_fin} de {total}...")
                    
                    try:
                        # Llamada a la nueva función de clasificación por lotes
                        resultados_lote = clasificar_lote_con_gemini(lote_actual_textos, GEMINI_MODEL)
                        errores_lote_actual = 0

                        # Procesar los resultados del lote
                        for resultado in resultados_lote:
                            idx_relativo = resultado.get('id')
                            categoria = resultado.get('categoria', "NO_CLASIFICADO")
                            razon = resultado.get('razon', "No se pudo extraer la razón")

                            # Calcular el índice absoluto en el DataFrame original
                            idx_absoluto = i_lote_inicio + idx_relativo
                            
                            # Asignar los resultados a las listas globales
                            if 0 <= idx_absoluto < total:
                                todas_las_categorias[idx_absoluto] = categoria
                                todas_las_razones[idx_absoluto] = razon
                                if categoria.startswith("ERROR"):
                                    errores_lote_actual += 1
                                    print(f"DEBUG: Error en resultado de lote (índice absoluto {idx_absoluto}): Categoría={categoria}, Razón={razon}")
                            else:
                                print(f"DEBUG: Índice absoluto fuera de rango: {idx_absoluto}")
                                errores_lote_actual += 1 # Considerar como error si el ID es inválido

                        if errores_lote_actual > 0:
                            errores_consecutivos += 1
                        else:
                            errores_consecutivos = 0 # Reiniciar contador de errores consecutivos

                    except Exception as e:
                        # Captura errores en la llamada al lote, por ejemplo, problemas de conexión o API.
                        print(f"DEBUG: Excepción en el procesamiento del lote {i_lote_inicio}-{i_lote_fin}: {e}")
                        errores_consecutivos += 1
                        # Rellenar las entradas de este lote con un estado de error
                        for j in range(i_lote_inicio, i_lote_fin):
                            if j < total: # Asegurarse de no exceder los límites
                                todas_las_categorias[j] = "ERROR_LOTE"
                                todas_las_razones[j] = f"Error en lote: {str(e)}"
                    
                    progreso.progress(min(1.0, (i_lote_fin) / total)) # Asegurar que no exceda 1.0
                    
                    if errores_consecutivos >= limite_errores:
                        st.error(f"❌ Se detectaron {errores_consecutivos} errores consecutivos. Se detiene la clasificación.")
                        print(f"DEBUG: Límite de errores consecutivos alcanzado en el lote {i_lote_inicio}.")
                        # Marcar las filas restantes como no procesadas
                        for j_restante in range(i_lote_fin, total):
                            todas_las_categorias[j_restante] = "NO_CLASIFICADO"
                            todas_las_razones[j_restante] = "Proceso detenido por errores consecutivos"
                        break # Sale del bucle de lotes
                    
                    time.sleep(espera) # Retraso si `espera` es > 0

                # Asegura que la barra de progreso llegue al 100% al finalizar o detenerse
                progreso.progress(1.0)
                estado.text("Clasificación finalizada.")
                print("DEBUG: Proceso de clasificación completado (o detenido por errores).")
                proceso_completado_exitosamente = True

            except Exception as e: # Captura cualquier error que ocurra durante el bucle principal de lotes
                st.error(f"❌ ¡Ocurrió un error inesperado durante el procesamiento del archivo! Por favor, revisa la consola de tu terminal. Error: {e}")
                print(f"DEBUG: Excepción crítica en el bucle principal de lotes: {e}")
                progreso.progress(1.0)
                estado.text("Clasificación detenida por error crítico.")

            df["Clasificacion-Gemini"] = todas_las_categorias
            df["Razon-Gemini"] = todas_las_razones

            # Descargar resultado
            salida = BytesIO()
            df.to_excel(salida, index=False)
            salida.seek(0)

            nombre_base = archivo.name.rsplit(".", 1)[0]
            nombre_resultado = f"{nombre_base}_clasificado.xlsx"

            st.success("✅ Clasificación completada")
            st.download_button(
                label="⬇️ Descargar archivo clasificado",
                data=salida,
                file_name=nombre_resultado,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            if proceso_completado_exitosamente:
                st.info("El proceso de clasificación ha finalizado y el archivo está listo para descargar. Si hubo errores, se registraron en el archivo.")
            else:
                st.error("El proceso de clasificación fue interrumpido por un error crítico. Por favor, revisa la consola de tu terminal.")
