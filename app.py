import streamlit as st
import pandas as pd

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero

st.set_page_config(
    page_title="Ilustrador Financiero V2",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 Ilustrador Financiero V2")
st.subheader("Paso 1 — Configuración inicial")

# ---------------------------
# CARGA DE FONDOS
# ---------------------------
try:
    fondos = cargar_todos_los_fondos("data")
except Exception as e:
    st.error(f"Error cargando fondos: {e}")
    st.stop()

if not fondos:
    st.warning("No se encontraron archivos .xlsx en la carpeta data.")
    st.stop()

# ---------------------------
# CAMPOS DE CONFIGURACIÓN
# ---------------------------
col1, col2 = st.columns(2)

with col1:
    producto = st.selectbox("Producto", ["MIS", "MSS"])

with col2:
    if producto == "MSS":
        plazo = st.selectbox("Plazo", list(range(5, 21)))
    else:
        plazo = None
        st.selectbox("Plazo", ["No aplica"], disabled=True)

col3, col4 = st.columns(2)

with col3:
    mes_inicio_txt = st.selectbox("Mes de inicio", LISTA_MESES, index=0)
    mes_inicio = mes_numero(mes_inicio_txt)

with col4:
    años_disponibles = list(range(2018, 2027))
    año_inicio = st.selectbox("Año de inicio", años_disponibles, index=0)

nombre_cliente = st.text_input("Nombre del cliente", value="Cliente Ejemplo")

# ---------------------------
# FECHA DE REFERENCIA
# ---------------------------
fecha_inicio_referencia = (
    pd.Timestamp(year=año_inicio, month=mes_inicio, day=1)
    + pd.offsets.MonthEnd(0)
)

# ---------------------------
# FILTRO DE FONDOS DISPONIBLES
# REGLA ESPECIAL PARA MANAGED FUND
# - Antes de enero 2026: usar DGT Managed
# - Desde enero 2026: usar DCS Managed
# ---------------------------
fecha_corte_managed = pd.Timestamp(year=2026, month=1, day=31)

fondos_disponibles = {}
fondos_no_disponibles = {}

dgt_managed = None
dcs_managed = None

for nombre, info in fondos.items():
    nombre_lower = nombre.lower()

    # Detectar los dos fondos managed y separarlos
    if "managed" in nombre_lower:
        if "dgt" in nombre_lower:
            dgt_managed = info
        elif "dcs" in nombre_lower:
            dcs_managed = info
        continue

    fecha_fondo = pd.Timestamp(info["start_date"])
    fecha_fondo_mes = (
        pd.Timestamp(year=fecha_fondo.year, month=fecha_fondo.month, day=1)
        + pd.offsets.MonthEnd(0)
    )

    if fecha_fondo_mes <= fecha_inicio_referencia:
        fondos_disponibles[nombre] = info
    else:
        fondos_no_disponibles[nombre] = info

# Crear Managed Fund unificado
managed_info = None

if fecha_inicio_referencia < fecha_corte_managed:
    if dgt_managed is not None:
        managed_info = dgt_managed
else:
    if dcs_managed is not None:
        managed_info = dcs_managed

if managed_info is not None:
    fondos_disponibles["Managed Fund"] = managed_info

# ---------------------------
# RESUMEN DE CONFIGURACIÓN
# ---------------------------
st.markdown("### Resumen de configuración")

resumen_config = {
    "Producto": producto,
    "Plazo": f"{plazo} años" if plazo else "No aplica",
    "Inicio": f"{mes_inicio_txt.capitalize()} {año_inicio}",
    "Cliente": nombre_cliente if nombre_cliente else "-",
    "Fondos disponibles": len(fondos_disponibles),
    "Fondos no disponibles": len(fondos_no_disponibles),
}

st.dataframe(
    pd.DataFrame([resumen_config]),
    use_container_width=True,
    hide_index=True
)

st.caption(
    "Nota: El histórico del Managed Fund incorpora distintos vehículos utilizados en el tiempo para representar la misma estrategia."
)

if fondos_disponibles:
    st.success(
        f"Para {mes_inicio_txt} {año_inicio}, hay {len(fondos_disponibles)} fondos disponibles."
    )
else:
    st.error(f"No hay fondos disponibles para {mes_inicio_txt} {año_inicio}.")

# ---------------------------
# TABLA DE FONDOS DISPONIBLES
# ---------------------------
st.markdown("### Fondos disponibles para la fecha elegida")

if fondos_disponibles:
    tabla_disponibles = []

    for nombre, info in fondos_disponibles.items():
        tabla_disponibles.append({
            "Fondo": nombre,
            "Inicio": pd.Timestamp(info["start_date"]).strftime("%Y-%m-%d"),
            "Fin": pd.Timestamp(info["end_date"]).strftime("%Y-%m-%d"),
            "Meses disponibles": len(info["df_monthly"]),
        })

    df_disponibles = (
        pd.DataFrame(tabla_disponibles)
        .sort_values(["Inicio", "Fondo"])
        .reset_index(drop=True)
    )

    st.dataframe(df_disponibles, use_container_width=True, hide_index=True)

# ---------------------------
# TABLA DE FONDOS NO DISPONIBLES
# ---------------------------
with st.expander("Ver fondos que aún no estaban disponibles en esa fecha"):
    if fondos_no_disponibles:
        tabla_no_disponibles = []

        for nombre, info in fondos_no_disponibles.items():
            tabla_no_disponibles.append({
                "Fondo": nombre,
                "Disponible desde": pd.Timestamp(info["start_date"]).strftime("%Y-%m-%d"),
                "Fin": pd.Timestamp(info["end_date"]).strftime("%Y-%m-%d"),
                "Meses disponibles": len(info["df_monthly"]),
            })

        df_no_disponibles = (
            pd.DataFrame(tabla_no_disponibles)
            .sort_values(["Disponible desde", "Fondo"])
            .reset_index(drop=True)
        )

        st.dataframe(df_no_disponibles, use_container_width=True, hide_index=True)
    else:
        st.info("Todos los fondos estaban disponibles para esa fecha.")