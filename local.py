import streamlit as st
import pandas as pd
import time
from io import BytesIO
import os
import google.generativeai as genai

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

# === FUNCIÓN DE CLASIFICACIÓN ===
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
        print(f"DEBUG: Error en clasificar_queja_con_razon para texto '{texto[:50]}...': {e}") # Debugging
        return "ERROR", str(e)

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
        # Se elimina el slider de espera y se fija el valor a 0.0 para no añadir retrasos artificiales
        espera = 0.0 

        if st.button("🚀 Clasificar archivo"):
            categorias = []
            razones = []
            total = len(df)
            progreso = st.progress(0)
            estado = st.empty()
            proceso_completado_exitosamente = False # Bandera para saber si el script terminó su ejecución

            errores_consecutivos = 0
            limite_errores = 20
            
            try:
                for i, texto in enumerate(df[columna].astype(str)):
                    estado.text(f"Clasificando fila {i + 1} de {total}...")
                    
                    try:
                        categoria, razon = clasificar_queja_con_razon(texto)
                        if categoria == "ERROR":
                            errores_consecutivos += 1
                            razon = razon or "Error sin mensaje" # Asegura que haya un mensaje de error
                            print(f"DEBUG: Error clasif. en fila {i+1}: {razon}") # Debugging
                        else:
                            errores_consecutivos = 0 # Reinicia el contador si la clasificación es exitosa
                    except Exception as e: # Captura errores inesperados dentro de clasificar_queja_con_razon si no fueron devueltos como "ERROR"
                        categoria = "ERROR_INESPERADO"
                        razon = str(e)
                        errores_consecutivos += 1
                        print(f"DEBUG: Excepción inesperada en fila {i+1}: {razon}") # Debugging
                    
                    categorias.append(categoria)
                    razones.append(razon)
                    progreso.progress((i + 1) / total)
                    
                    if errores_consecutivos >= limite_errores:
                        st.error(f"❌ Se detectaron {errores_consecutivos} errores consecutivos. Se detiene la clasificación.")
                        print(f"DEBUG: Límite de errores consecutivos alcanzado en fila {i+1}.") # Debugging
                        break # Sale del bucle for
                    
                    time.sleep(espera) # Se mantiene para permitir un respiro si es necesario, pero ahora el default es 0.0
                
                # Lógica de relleno si el bucle se detuvo prematuramente
                if len(categorias) < total:
                    st.warning(f"La clasificación se detuvo prematuramente en la fila {len(categorias)}. Rellenando el resto con 'NO_CLASIFICADO' y 'No procesado debido a errores consecutivos'.")
                    print(f"DEBUG: Rellenando filas restantes. Procesadas: {len(categorias)}, Total: {total}") # Debugging
                    # Rellenar con los valores predeterminados hasta el final del DataFrame
                    while len(categorias) < total:
                        categorias.append("NO_CLASIFICADO")
                        razones.append("No procesado debido a errores consecutivos")
                
                # Asegura que la barra de progreso llegue al 100% al finalizar o detenerse
                progreso.progress(1.0)
                estado.text("Clasificación finalizada.")
                print("DEBUG: Proceso de clasificación completado (o detenido por errores).") # Debugging
                proceso_completado_exitosamente = True # El script llegó a su fin

            except Exception as e: # Captura cualquier error que ocurra durante el bucle principal
                st.error(f"❌ ¡Ocurrió un error inesperado durante el procesamiento del archivo! Por favor, revisa la consola de tu terminal. Error: {e}")
                print(f"DEBUG: Excepción crítica en el bucle principal: {e}") # Debugging
                # Asegura que la barra de progreso se detenga y muestre el estado final
                progreso.progress(1.0)
                estado.text("Clasificación detenida por error crítico.")

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
            # Mensaje final para confirmar que el script llegó hasta aquí
            if proceso_completado_exitosamente:
                st.info("El proceso de clasificación ha finalizado y el archivo está listo para descargar. Si hubo errores, se registraron en el archivo.")
            else:
                st.error("El proceso de clasificación fue interrumpido por un error crítico. Por favor, revisa la consola de tu terminal.")

