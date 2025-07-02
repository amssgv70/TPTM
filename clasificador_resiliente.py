import streamlit as st
import pandas as pd
import time
from io import BytesIO
import os
import google.generativeai as genai
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import google.api_core.exceptions as g_exceptions # Importar excepciones específicas de Google API

# === CONFIGURACIÓN BÁSICA DE LA APP ===
#st.set_page_config(page_title="Clasificador de Quejas", layout="centered")


# Obtener el código válido desde variable de entorno (o valor por defecto para pruebas)
codigo_valido = os.getenv("CODIGO_ACCESO", "clasificar2024")

# Inicializar estado de sesión
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# Si no está autenticado, mostrar formulario y detener app si no es válido
if not st.session_state.autenticado:
    with st.form("form_codigo"):
        st.markdown("### 🔒 Acceso restringido")
        codigo = st.text_input("Ingresá el código de acceso:", type="password")
        submit = st.form_submit_button("Ingresar")

    if submit:
        if codigo == codigo_valido:
            st.session_state.autenticado = True
            st.rerun()  # volver a cargar sin el formulario
        else:
            st.error("❌ Código incorrecto.")
    st.stop()  # Detener todo lo demás hasta que esté autenticado


# --- CONFIGURACIÓN DE GEMINI ---
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    st.error("❌ API Key no configurada. Definila como variable de entorno GEMINI_API_KEY en Streamlit Cloud.")
    st.stop()

genai.configure(api_key=API_KEY)

# Define las excepciones específicas de Gemini que quieres reintentar
RETRY_EXCEPTIONS = (
    g_exceptions.ResourceExhausted, # Cuota excedida
    g_exceptions.ServiceUnavailable, # Servicio no disponible
    g_exceptions.InternalServerError, # Errores internos del servidor de Gemini
    g_exceptions.TooManyRequests, # Demasiadas solicitudes
    #g_exceptions.ClientDisconnect, # Desconexión del cliente (red)
)

# === FUNCIÓN DE CLASIFICACIÓN CON RETRY ===
@retry(
    wait=wait_exponential(multiplier=1, min=4, max=60), # Espera exponencial: 4s, 8s, 16s... hasta 60s
    stop=stop_after_attempt(5), # Reintenta hasta 5 veces
    retry=retry_if_exception_type(RETRY_EXCEPTIONS),
    reraise=True # Re-lanza la excepción si todos los reintentos fallan
)
def _call_gemini_api(texto_queja): # Función interna para la llamada a la API con reintentos
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

Texto: {texto_queja}
"""
    model = genai.GenerativeModel("gemini-2.5-Flash")
    # Añade un timeout explícito para la llamada a la API
    response = model.generate_content(prompt, request_options={"timeout": 120}) # 120 segundos de timeout
    respuesta = response.text.strip()

    categoria, razon = "", ""
    for linea in respuesta.splitlines():
        if linea.lower().startswith("categoría:") or linea.lower().startswith("categoria:"):
            categoria = linea.split(":", 1)[1].strip()
        elif linea.lower().startswith("razón:") or linea.lower().startswith("razon:"):
            razon = linea.split(":", 1)[1].strip()
            
    if not categoria or not razon:
        raise ValueError(f"Formato de respuesta inesperado de Gemini: {respuesta}") # Levanta un error si el formato no es el esperado
        
    return categoria, razon

def clasificar_queja_con_razon(texto):
    try:
        categoria, razon = _call_gemini_api(texto)
        return categoria, razon
    except RETRY_EXCEPTIONS as e:
        # Esto se capturará si tenacity falla después de todos los reintentos
        return "ERROR_API", f"Fallo persistente de Gemini tras reintentos: {e}"
    except ValueError as e:
        # Esto se capturará si el formato de respuesta de Gemini es incorrecto
        return "ERROR_FORMATO", f"Error de formato de respuesta de Gemini: {e}"
    except Exception as e:
        # Cualquier otro error inesperado
        return "ERROR_GENERAL", f"Error inesperado durante la clasificación: {str(e)}"

# === INTERFAZ STREAMLIT ===
st.set_page_config(page_title="Clasificador de Quejas", layout="centered")
st.title("🧾 Clasificador de Quejas de Pasajeros")

modo = st.radio("¿Qué querés hacer?", ["📝 Clasificar una queja manualmente", "📂 Clasificar archivo Excel/CSV"])

# === MODO 1: CLASIFICACIÓN MANUAL (sin cambios significativos, solo usa la nueva función) ===
if modo == "📝 Clasificar una queja manualmente":
    texto = st.text_area("✏️ Ingresá una queja", height=200)

    if st.button("📊 Clasificar queja"):
        if not texto.strip():
            st.warning("Ingresá una queja antes de clasificar.")
        else:
            with st.spinner("Clasificando..."):
                categoria, razon = clasificar_queja_con_razon(texto)
            if categoria.startswith("ERROR"): # Ahora verificamos por cualquier tipo de error
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
        espera = st.slider("⏱ Espera entre clasificaciones (segundos)", 0, 10, 5)

        if st.button("🚀 Clasificar archivo"):
            categorias = []
            razones = []
            total = len(df)
            
            # Usar un placeholder para la barra de progreso y el estado para evitar re-renderizados
            progress_bar = st.progress(0, text="Iniciando clasificación...")
            status_text = st.empty()

            errores_consecutivos = 0
            limite_errores = 20

            for i, texto in enumerate(df[columna].astype(str)):
                status_text.text(f"Clasificando fila {i + 1} de {total}...")
                
                categoria, razon = clasificar_queja_con_razon(texto)
                
                if categoria.startswith("ERROR"):
                    errores_consecutivos += 1
                    status_text.warning(f"Error en fila {i+1}: {razon}. Errores consecutivos: {errores_consecutivos}. Reintentando...")
                    # No añadimos al progreso aquí para dar tiempo a Tenacity
                else:
                    errores_consecutivos = 0
                    
                categorias.append(categoria)
                razones.append(razon)
                
                # Actualiza la barra de progreso. La etiqueta de texto ya está en el progress_bar
                progress_bar.progress((i + 1) / total, text=f"Progreso: {((i + 1) / total)*100:.2f}% ({i+1}/{total} filas)")
                
                if errores_consecutivos >= limite_errores:
                    st.error(f"❌ Se detectaron {errores_consecutivos} errores consecutivos. Se detiene la clasificación.")
                    break
                
                time.sleep(espera)
            
            # --- Manejo del fin prematuro ---
            if len(categorias) < total:
                status_text.warning(f"La clasificación se detuvo prematuramente en la fila {len(categorias)}. Rellenando el resto del archivo.")
                while len(categorias) < total:
                    categorias.append("NO_CLASIFICADO")
                    razones.append("No procesado debido a errores consecutivos (posibles errores de API o límites)")
            else:
                status_text.success("✅ Clasificación de archivo completada.")


            df["Clasificacion-Gemini"] = categorias
            df["Razon-Gemini"] = razones

            # Descargar resultado
            salida = BytesIO()
            df.to_excel(salida, index=False)
            salida.seek(0)

            nombre_base = archivo.name.rsplit(".", 1)[0]
            nombre_resultado = f"{nombre_base}_clasificado.xlsx"

            st.success("✅ Proceso completado. Puedes descargar el archivo.")
            st.download_button(
                label="⬇️ Descargar archivo clasificado",
                data=salida,
                file_name=nombre_resultado,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if st.session_state.autenticado:
    if st.button("🔒 Cerrar sesión"):
        st.session_state.autenticado = False
        st.rerun()
