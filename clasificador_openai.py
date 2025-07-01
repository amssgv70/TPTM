import streamlit as st
import pandas as pd
import time
from io import BytesIO
import os
import openai

# === CONFIGURACIÓN BÁSICA DE LA APP ===
st.set_page_config(page_title="Clasificador de Quejas", layout="centered")
st.title("🧾 Clasificador de Quejas de Pasajeros")

# === AUTENTICACIÓN ===
codigo_valido = os.getenv("CODIGO_ACCESO", "clasificar2024")

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    with st.form("form_codigo"):
        st.markdown("### 🔒 Acceso restringido")
        codigo = st.text_input("Ingresá el código de acceso:", type="password")
        submit = st.form_submit_button("Ingresar")

    if submit:
        if codigo == codigo_valido:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("❌ Código incorrecto.")
    st.stop()

# === CONFIGURACIÓN DE OPENAI ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("❌ API Key no configurada. Definila como variable de entorno OPENAI_API_KEY en Streamlit Cloud.")
    st.stop()

openai.api_key = OPENAI_API_KEY

# === FUNCIÓN DE CLASIFICACIÓN ===
def clasificar_queja_con_razon(texto, modelo="gpt-4o"):
    prompt_usuario = f"""Leé la siguiente queja de un pasajero y devolvé SOLO:

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
        response = openai.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": "Sos un asistente experto en analizar y categorizar quejas de pasajeros."},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=0.2,
            max_tokens=256
        )

        respuesta = response.choices[0].message.content.strip()
        categoria, razon = "", ""
        for linea in respuesta.splitlines():
            if linea.lower().startswith("categoría:") or linea.lower().startswith("categoria:"):
                categoria = linea.split(":", 1)[1].strip()
            elif linea.lower().startswith("razón:") or linea.lower().startswith("razon:"):
                razon = linea.split(":", 1)[1].strip()

        return categoria, razon

    except Exception as e:
        return "ERROR", str(e)

# === SELECCIÓN DE MODO ===
modo = st.radio("¿Qué querés hacer?", ["📝 Clasificar una queja manualmente", "📂 Clasificar archivo Excel/CSV"])
modelo = st.selectbox("🧠 Elegí el modelo de OpenAI a usar:", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"])

# === MODO 1: MANUAL ===
if modo == "📝 Clasificar una queja manualmente":
    texto = st.text_area("✏️ Ingresá una queja", height=200)

    if st.button("📊 Clasificar queja"):
        if not texto.strip():
            st.warning("Ingresá una queja antes de clasificar.")
        else:
            with st.spinner("Clasificando..."):
                categoria, razon = clasificar_queja_con_razon(texto, modelo)
            if categoria == "ERROR":
                st.error(f"❌ Error: {razon}")
            else:
                st.success("✅ Clasificación exitosa")
                st.write(f"**📌 Categoría:** {categoria}")
                st.write(f"**💬 Razón:** {razon}")

# === MODO 2: ARCHIVO ===
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

            errores_consecutivos = 0
            limite_errores = 20

            for i, texto in enumerate(df[columna].astype(str)):
                estado.text(f"Clasificando fila {i + 1} de {total}...")

                try:
                    categoria, razon = clasificar_queja_con_razon(texto, modelo)
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

            df["Clasificacion-OpenAI"] = categorias
            df["Razon-OpenAI"] = razones

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

# === CIERRE DE SESIÓN ===
if st.session_state.autenticado:
    if st.button("🔒 Cerrar sesión"):
        st.session_state.autenticado = False
        st.rerun()
