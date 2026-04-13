import streamlit as st
import pandas as pd

from modules.fund_loader import cargar_todos_los_fondos

st.set_page_config(
    page_title="Ilustrador Financiero V2",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 Ilustrador Financiero V2")
st.subheader("Paso 2 — Lectura de fondos DCS")

try:
    fondos = cargar_todos_los_fondos("data")
except Exception as e:
    st.error(f"Error cargando fondos: {e}")
    st.stop()

if not fondos:
    st.warning("No se encontraron archivos .xlsx en la carpeta data.")
    st.stop()

st.success(f"Se cargaron {len(fondos)} fondos.")

resumen = []
for nombre, info in fondos.items():
    resumen.append({
        "Fondo": nombre,
        "Archivo": info["file_name"],
        "Inicio": info["start_date"].strftime("%Y-%m-%d"),
        "Fin": info["end_date"].strftime("%Y-%m-%d"),
        "Meses disponibles": len(info["df_monthly"]),
    })

df_resumen = pd.DataFrame(resumen).sort_values(["Inicio", "Fondo"]).reset_index(drop=True)

st.dataframe(df_resumen, use_container_width=True, hide_index=True)

fondo_elegido = st.selectbox("Ver detalle de un fondo", list(fondos.keys()))

info = fondos[fondo_elegido]

st.markdown(f"### {fondo_elegido}")
st.write(f"**Archivo:** {info['file_name']}")
st.write(f"**Inicio:** {info['start_date'].strftime('%Y-%m-%d')}")
st.write(f"**Fin:** {info['end_date'].strftime('%Y-%m-%d')}")

st.markdown("#### Serie mensual")
st.dataframe(info["df_monthly"].head(12), use_container_width=True, hide_index=True)

st.markdown("#### Evolución del NAV mensual")
chart_df = info["df_monthly"].set_index("Date")[["Price"]]
st.line_chart(chart_df)