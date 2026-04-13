import streamlit as st
import pandas as pd

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero
from modules.portfolio_builder import construir_portafolio
from modules.simulator import simular_mis, simular_mss, construir_resumen_anual
from modules.reporting import construir_estado_cuenta_final


# ============================
# CONFIG
# ============================
st.set_page_config(
    page_title="Ilustrador Financiero V2",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 Ilustrador Financiero V2")

# ============================
# FORMATO Y COLORES
# ============================
def color_valores(val):
    try:
        v = float(str(val).replace("USD", "").replace("%", "").replace(",", "").strip())
        if v < 0:
            return "color: red; font-weight: bold;"
        elif v > 0:
            return "color: green; font-weight: bold;"
        return ""
    except:
        return ""

def formatear_resumen(df):
    df_fmt = df.copy()

    for col in ["Aporte_Acum", "Retiro", "Valor_Cuenta", "Valor_Rescate"]:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Rendimiento", "Rendimiento_Acumulado"]:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")

    styled = df_fmt.style.map(
        color_valores,
        subset=["Rendimiento", "Rendimiento_Acumulado"]
    )

    return styled


# ============================
# CARGA DE FONDOS
# ============================
fondos = cargar_todos_los_fondos("data")

# ============================
# CONFIGURACIÓN
# ============================
st.subheader("Paso 1 — Configuración inicial")

col1, col2 = st.columns(2)

with col1:
    producto = st.selectbox("Producto", ["MIS", "MSS"])

with col2:
    plazo = st.selectbox("Plazo", list(range(5, 21))) if producto == "MSS" else None

col3, col4 = st.columns(2)

with col3:
    mes_txt = st.selectbox("Mes", LISTA_MESES)
    mes_inicio = mes_numero(mes_txt)

with col4:
    anio_inicio = st.selectbox("Año", list(range(2018, 2027)))

fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1) + pd.offsets.MonthEnd(0)

# ============================
# FILTRO FONDOS
# ============================
fondos_disponibles = {}

for nombre, info in fondos.items():
    fecha_fondo = pd.Timestamp(info["start_date"])
    fecha_fondo_mes = pd.Timestamp(year=fecha_fondo.year, month=fecha_fondo.month, day=1) + pd.offsets.MonthEnd(0)

    if fecha_fondo_mes <= fecha_inicio:
        fondos_disponibles[nombre] = info

# ============================
# SELECCIÓN FONDOS
# ============================
st.subheader("Paso 2 — Selección de fondos")

fondos_seleccionados = st.multiselect(
    "Selecciona hasta 8 fondos",
    list(fondos_disponibles.keys()),
    max_selections=8
)

# ============================
# ASIGNACIÓN
# ============================
if fondos_seleccionados:
    st.subheader("Paso 3 — Asignación")

    asignaciones = {}
    total = 0

    for f in fondos_seleccionados:
        p = st.selectbox(f, list(range(0, 101, 10)), key=f)
        asignaciones[f] = p
        total += p

    st.write(f"Total: {total}%")

    if total != 100:
        st.warning("Debe sumar 100%")

    # ============================
    # CONFIG FINANCIERA
    # ============================
    if total == 100:

        st.subheader("Paso 4 — Configuración financiera")

        if producto == "MIS":
            monto_inicial = st.number_input("Monto inicial", min_value=10000, value=10000)
            aporte_periodico = 0
            frecuencia_pago = None
        else:
            frecuencia_pago = st.selectbox("Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"])
            aporte_periodico = st.number_input("Aporte", min_value=150, value=150)
            monto_inicial = 0

        # ============================
        # APORTES EXTRA
        # ============================
        aportes_extra = []

        if st.checkbox("Aportes extra"):
            for i in range(2):
                monto = st.number_input(f"Monto extra {i}", min_value=0)
                if monto >= 1500:
                    aportes_extra.append({
                        "monto": monto,
                        "anio": anio_inicio,
                        "mes": mes_inicio
                    })

        # ============================
        # PORTAFOLIO
        # ============================
        df_port = construir_portafolio(fondos_disponibles, asignaciones)

        st.line_chart(df_port.set_index("Date")["Price"])

        # ============================
        # SIMULACIÓN
        # ============================
        if producto == "MIS":
            df_res = simular_mis(df_port, monto_inicial, anio_inicio, mes_inicio, aportes_extra, [])
        else:
            df_mss = simular_mss(df_port, plazo, aporte_periodico, frecuencia_pago, anio_inicio, mes_inicio, [])

            if aportes_extra:
                df_extra = simular_mis(df_port, 0, anio_inicio, mes_inicio, aportes_extra, [])
                df_res = df_mss.copy()
                df_res["Valor_Cuenta"] += df_extra["Valor_Cuenta"]
                df_res["Valor_Rescate"] += df_extra["Valor_Rescate"]
                df_res["Aporte_Acum"] += df_extra["Aporte_Acum"]
            else:
                df_res = df_mss

        st.success("Simulación lista")

        # ============================
        # RESULTADOS
        # ============================
        st.metric("Valor final", f"USD {df_res['Valor_Cuenta'].iloc[-1]:,.2f}")

        st.line_chart(df_res.set_index("Date")[["Valor_Cuenta", "Valor_Rescate"]])

        # ============================
        # RESUMEN ANUAL
        # ============================
        resumen = construir_resumen_anual(df_res, anio_inicio, mes_inicio)
        st.subheader("Resumen anual")
        st.dataframe(formatear_resumen(resumen))

        # ============================
        # ESTADO FINAL POR FONDO
        # ============================
        estado = construir_estado_cuenta_final(
            fondos_disponibles,
            asignaciones,
            anio_inicio,
            mes_inicio,
            df_res["Aporte_Acum"].iloc[-1]
        )

        st.subheader("Estado final por fondo")
        st.dataframe(estado)

        # ============================
        # SNAPSHOT SIMPLE
        # ============================
        st.subheader("Estado en fecha específica")

        mes_obj = mes_numero(st.selectbox("Mes snapshot", LISTA_MESES))
        anio_obj = st.selectbox("Año snapshot", sorted(df_res["Date"].dt.year.unique()))

        fecha_obj = pd.Timestamp(year=anio_obj, month=mes_obj, day=1) + pd.offsets.MonthEnd(0)

        df_snap = df_res[df_res["Date"] <= fecha_obj]

        if not df_snap.empty:
            fila = df_snap.iloc[-1]
            st.write("Valor en cuenta:", f"USD {fila['Valor_Cuenta']:,.2f}")
            st.write("Aporte:", f"USD {fila['Aporte_Acum']:,.2f}")