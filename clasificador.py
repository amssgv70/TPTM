import streamlit as st
import pandas as pd
import time
from io import BytesIO
import os
import google.generativeai as genai

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






# === CONFIGURACIÓN DE GEMINI ===
API_KEY = os.getenv("GEMINI_API_KEY_2")
if not API_KEY:
    st.error("❌ API Key no configurada. Definila como variable de entorno GEMINI_API_KEY en Streamlit Cloud.")
    st.stop()

genai.configure(api_key=API_KEY)

# === FUNCIÓN DE CLASIFICACIÓN ===
def clasificar_queja_con_razon(texto):
    prompt = f"""Leé la siguiente queja de un pasajero y devolvé SOLO:

1. La categoría más adecuada según esta lista:
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
        model = genai.GenerativeModel("gemini-2.5-flash")
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
        return "ERROR", str(e)

# === INTERFAZ STREAMLIT ===
st.set_page_config(page_title="Clasificador de Quejas", layout="centered")
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
        espera = st.slider("⏱ Espera entre clasificaciones (segundos)", 0, 10, 5)

        if st.button("🚀 Clasificar archivo"):
            categorias = []
            razones = []
            total = len(df)
            progreso = st.progress(0)
            estado = st.empty()

     #       for i, texto in enumerate(df[columna].astype(str)):
     #           estado.text(f"Clasificando fila {i + 1} de {total}...")
     #           categoria, razon = clasificar_queja_con_razon(texto)
     #           categorias.append(categoria)
     #           razones.append(razon)
     #           progreso.progress((i + 1) / total)
     #           time.sleep(espera)

            errores_consecutivos = 0
            limite_errores = 20

            for i, texto in enumerate(df[columna].astype(str)):
                estado.text(f"Clasificando fila {i + 1} de {total}...")
            
                try:
                    categoria, razon = clasificar_queja_con_razon(texto)
                    if categoria == "ERROR":
                        errores_consecutivos += 1
                        razon = razon or "Error sin mensaje"
                    else:
                        errores_consecutivos = 0
                except Exception as e:
                    categoria = "ERROR"
                    razon = str(e)
                    errores_consecutivos += 1
            
                categorias.append(categoria)
                razones.append(razon)
                progreso.progress((i + 1) / total)
            
                if errores_consecutivos >= limite_errores:
                    st.error(f"❌ Se detectaron {errores_consecutivos} errores consecutivos. Se detiene la clasificación.")
                    break
            
                time.sleep(espera)
 
            
            df["Clasificacion-Gemini"] = categorias
            df["Razon-Gemini"] = razones

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

if st.session_state.autenticado:
    if st.button("🔒 Cerrar sesión"):
        st.session_state.autenticado = False
        st.rerun()
