import streamlit as st
import pandas as pd

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero
from modules.portfolio_builder import construir_portafolio
from modules.simulator import simular_mis, simular_mss, construir_resumen_anual

st.set_page_config(
    page_title="Ilustrador Financiero V2",
    page_icon="🚀",
    layout="wide"
)


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================
def combinar_mss_con_extras_mis(df_mss: pd.DataFrame, df_mis_extras: pd.DataFrame) -> pd.DataFrame:
    """
    Combina una simulación MSS principal con una simulación MIS de aportes extra.
    Conserva la columna Etapa del MSS.
    """
    base = df_mss.copy()
    extra = df_mis_extras.copy()

    cols_sumar = ["Aporte_Acum", "Valor_Cuenta", "Valor_Rescate", "Retiro"]

    extra = extra[["Date"] + cols_sumar].copy()
    extra = extra.rename(columns={c: f"{c}_extra" for c in cols_sumar})

    df = base.merge(extra, on="Date", how="left")

    for c in cols_sumar:
        df[f"{c}_extra"] = df[f"{c}_extra"].fillna(0.0)
        df[c] = df[c].fillna(0.0) + df[f"{c}_extra"]

    cols_drop = [f"{c}_extra" for c in cols_sumar]
    df = df.drop(columns=cols_drop)

    return df


def color_valores(val):
    try:
        v = float(str(val).replace("USD", "").replace("%", "").replace(",", "").strip())
        if v < 0:
            return "color: red; font-weight: bold;"
        elif v > 0:
            return "color: green; font-weight: bold;"
        return ""
    except Exception:
        return ""


def formatear_resumen_anual(resumen_anual: pd.DataFrame):
    resumen_anual_fmt = resumen_anual.copy()

    for col in ["Aporte_Acum", "Retiro", "Valor_Cuenta", "Valor_Rescate"]:
        if col in resumen_anual_fmt.columns:
            resumen_anual_fmt[col] = resumen_anual_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Rendimiento", "Rendimiento_Acumulado"]:
        if col in resumen_anual_fmt.columns:
            resumen_anual_fmt[col] = resumen_anual_fmt[col].apply(lambda x: f"{x:.2f}%")

    styled = resumen_anual_fmt.style.applymap(
        color_valores,
        subset=[c for c in ["Rendimiento", "Rendimiento_Acumulado"] if c in resumen_anual_fmt.columns]
    )

    return styled


# =========================================================
# TÍTULO
# =========================================================
st.title("🚀 Ilustrador Financiero V2")
st.subheader("Paso 1 — Configuración inicial")

# =========================================================
# CARGA DE FONDOS
# =========================================================
try:
    fondos = cargar_todos_los_fondos("data")
except Exception as e:
    st.error(f"Error cargando fondos: {e}")
    st.stop()

if not fondos:
    st.warning("No se encontraron archivos .xlsx en la carpeta data.")
    st.stop()

# =========================================================
# CAMPOS DE CONFIGURACIÓN
# =========================================================
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
    anios_disponibles = list(range(2018, 2027))
    anio_inicio = st.selectbox("Año de inicio", anios_disponibles, index=0)

nombre_cliente = st.text_input("Nombre del cliente", value="Cliente Ejemplo")

# =========================================================
# FECHA DE REFERENCIA
# =========================================================
fecha_inicio_referencia = (
    pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)
    + pd.offsets.MonthEnd(0)
)

# =========================================================
# FILTRO DE FONDOS DISPONIBLES
# REGLA ESPECIAL PARA MANAGED FUND
# =========================================================
fecha_corte_managed = pd.Timestamp(year=2026, month=1, day=31)

fondos_disponibles = {}
fondos_no_disponibles = {}

dgt_managed = None
dcs_managed = None

for nombre, info in fondos.items():
    nombre_lower = nombre.lower()

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

managed_info = None

if fecha_inicio_referencia < fecha_corte_managed:
    if dgt_managed is not None:
        managed_info = dgt_managed
else:
    if dcs_managed is not None:
        managed_info = dcs_managed

if managed_info is not None:
    fondos_disponibles["Managed Fund"] = managed_info

# =========================================================
# RESUMEN DE CONFIGURACIÓN
# =========================================================
st.markdown("### Resumen de configuración")

resumen_config = {
    "Producto": producto,
    "Plazo": f"{plazo} años" if plazo else "No aplica",
    "Inicio": f"{mes_inicio_txt.capitalize()} {anio_inicio}",
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
        f"Para {mes_inicio_txt} {anio_inicio}, hay {len(fondos_disponibles)} fondos disponibles."
    )
else:
    st.error(f"No hay fondos disponibles para {mes_inicio_txt} {anio_inicio}.")

# =========================================================
# TABLA DE FONDOS DISPONIBLES
# =========================================================
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

# =========================================================
# PASO 2 — SELECCIÓN DE FONDOS
# =========================================================
st.markdown("## Paso 2 — Selección de fondos")

nombres_fondos = list(fondos_disponibles.keys())

fondos_seleccionados = st.multiselect(
    "Selecciona hasta 8 fondos",
    options=nombres_fondos,
    default=[],
    max_selections=8
)

st.write(f"Fondos seleccionados: {len(fondos_seleccionados)} de 8")

# =========================================================
# PASO 3 — ASIGNACIÓN DE PORCENTAJES
# =========================================================
if fondos_seleccionados:
    st.markdown("## Paso 3 — Asignación inicial")

    opciones_porcentaje = list(range(0, 101, 10))
    asignaciones = {}
    total_asignado = 0

    for fondo in fondos_seleccionados:
        info_fondo = fondos_disponibles[fondo]

        st.markdown(f"### {fondo}")
        st.caption(
            f"Inicio: {pd.Timestamp(info_fondo['start_date']).strftime('%Y-%m-%d')} | "
            f"Fin: {pd.Timestamp(info_fondo['end_date']).strftime('%Y-%m-%d')}"
        )

        porcentaje = st.selectbox(
            f"Asignación para {fondo}",
            options=opciones_porcentaje,
            index=0,
            key=f"peso_{fondo}"
        )

        asignaciones[fondo] = porcentaje
        total_asignado += porcentaje

    st.markdown("### Resumen de asignación")

    col_a, col_b = st.columns(2)

    with col_a:
        st.metric("Total asignado", f"{total_asignado}%")

    with col_b:
        diferencia = 100 - total_asignado
        if diferencia > 0:
            st.warning(f"Falta asignar {diferencia}%")
        elif diferencia < 0:
            st.error(f"Excede en {abs(diferencia)}%")
        else:
            st.success("Asignación completa: 100%")

    tabla_asignacion = pd.DataFrame([
        {"Fondo": fondo, "Asignación inicial": f"{porcentaje}%"}
        for fondo, porcentaje in asignaciones.items()
    ])

    st.dataframe(tabla_asignacion, use_container_width=True, hide_index=True)

    if total_asignado == 100:
        st.success("Ya puedes pasar al cálculo de la ilustración.")
    else:
        st.info("La asignación debe sumar exactamente 100% para continuar.")

    # =====================================================
    # PASO 4 — CONFIGURACIÓN FINANCIERA
    # =====================================================
    if total_asignado == 100:
        st.markdown("## Paso 4 — Configuración financiera")

        if producto == "MIS":
            monto_inicial = st.number_input(
                "Inversión inicial (USD)",
                min_value=10000,
                value=10000,
                step=1000
            )

            frecuencia_pago = None
            aporte_periodico = None

            st.caption("Mínimo inicial para MIS: USD 10,000")

        else:
            frecuencia_pago = st.selectbox(
                "Frecuencia de aportes",
                ["Mensual", "Trimestral", "Semestral", "Anual"]
            )

            minimos_mss = {
                "Mensual": 150,
                "Trimestral": 450,
                "Semestral": 900,
                "Anual": 1800
            }

            minimo_aporte = minimos_mss[frecuencia_pago]

            aporte_periodico = st.number_input(
                f"Aporte por periodo (USD) — mínimo {minimo_aporte}",
                min_value=minimo_aporte,
                value=minimo_aporte,
                step=minimo_aporte
            )

            monto_inicial = 0

            st.caption(
                "Mínimo MSS: USD 150 mensuales o sus equivalentes: "
                "USD 450 trimestral, USD 900 semestral, USD 1,800 anual."
            )

        st.markdown("### Aportes adicionales")
        st.caption("Los aportes adicionales tienen un mínimo de USD 1,500.")

        aportes_extra = []

        if st.checkbox("Agregar aportes adicionales"):
            for i in range(3):
                st.markdown(f"**Aporte adicional {i+1}**")

                col_x, col_y, col_z = st.columns(3)

                with col_x:
                    monto_extra = st.number_input(
                        f"Monto {i+1}",
                        min_value=0,
                        value=0,
                        step=500,
                        key=f"extra_monto_{i}"
                    )

                with col_y:
                    anio_extra = st.number_input(
                        f"Año {i+1}",
                        min_value=2018,
                        max_value=2035,
                        value=anio_inicio,
                        key=f"extra_anio_{i}"
                    )

                with col_z:
                    mes_extra_txt = st.selectbox(
                        f"Mes {i+1}",
                        LISTA_MESES,
                        key=f"extra_mes_{i}"
                    )
                    mes_extra = mes_numero(mes_extra_txt)

                if monto_extra > 0:
                    if monto_extra < 1500:
                        st.warning(
                            f"El aporte adicional {i+1} es menor al mínimo de USD 1,500 y no será considerado."
                        )
                    else:
                        aportes_extra.append({
                            "monto": float(monto_extra),
                            "anio": int(anio_extra),
                            "mes": int(mes_extra)
                        })

        if producto == "MSS" and aportes_extra:
            st.info(
                "En MSS, los aportes adicionales se simularán con estructura de costos tipo MIS."
            )

        # =====================================================
        # PASO 5 — PORTAFOLIO COMBINADO
        # =====================================================
        st.markdown("## Paso 5 — Portafolio combinado")

        try:
            df_portafolio = construir_portafolio(fondos_disponibles, asignaciones)

            st.success("Portafolio combinado construido correctamente.")

            st.markdown("### Serie mensual del portafolio")
            st.dataframe(df_portafolio.head(24), use_container_width=True, hide_index=True)

            st.markdown("### Evolución del portafolio combinado")
            st.line_chart(df_portafolio.set_index("Date")[["Price"]])

            fecha_inicio_port = df_portafolio["Date"].min().strftime("%Y-%m-%d")
            fecha_fin_port = df_portafolio["Date"].max().strftime("%Y-%m-%d")
            nav_inicial = df_portafolio["Price"].iloc[0]
            nav_final = df_portafolio["Price"].iloc[-1]
            rendimiento_total = ((nav_final / nav_inicial) - 1) * 100 if nav_inicial != 0 else 0

            resumen_port = pd.DataFrame([{
                "Inicio": fecha_inicio_port,
                "Fin": fecha_fin_port,
                "Meses": len(df_portafolio),
                "NAV inicial": f"{nav_inicial:,.4f}",
                "NAV final": f"{nav_final:,.4f}",
                "Rendimiento acumulado": f"{rendimiento_total:.2f}%"
            }])

            st.markdown("### Resumen del portafolio")
            st.dataframe(resumen_port, use_container_width=True, hide_index=True)

            # =================================================
            # PASO 6 — SIMULACIÓN DEL PRODUCTO
            # =================================================
            st.markdown("## Paso 6 — Simulación del producto")

            retiros_programados = []

            if producto == "MIS":
                df_resultado = simular_mis(
                    df_base=df_portafolio,
                    monto_inicial=float(monto_inicial),
                    anio_inicio=int(anio_inicio),
                    mes_inicio=int(mes_inicio),
                    aportes_extra=aportes_extra,
                    retiros_programados=retiros_programados
                )

            else:
                # MSS principal
                df_mss_principal = simular_mss(
                    df_base=df_portafolio,
                    plazo_anios=int(plazo),
                    monto_aporte=float(aporte_periodico),
                    frecuencia_pago=frecuencia_pago,
                    anio_inicio=int(anio_inicio),
                    mes_inicio=int(mes_inicio),
                    retiros_programados=retiros_programados
                )

                # Si hay aportes extra, se simulan como MIS y se suman
                if aportes_extra:
                    df_mis_extras = simular_mis(
                        df_base=df_portafolio,
                        monto_inicial=0.0,
                        anio_inicio=int(anio_inicio),
                        mes_inicio=int(mes_inicio),
                        aportes_extra=aportes_extra,
                        retiros_programados=[]
                    )

                    df_resultado = combinar_mss_con_extras_mis(df_mss_principal, df_mis_extras)
                else:
                    df_resultado = df_mss_principal

            st.success("Simulación completada correctamente.")

            valor_final = df_resultado["Valor_Cuenta"].iloc[-1]
            valor_rescate = df_resultado["Valor_Rescate"].iloc[-1]
            aporte_total = df_resultado["Aporte_Acum"].iloc[-1]

            c1, c2, c3 = st.columns(3)
            c1.metric("Aporte total", f"USD {aporte_total:,.2f}")
            c2.metric("Valor en cuenta", f"USD {valor_final:,.2f}")
            c3.metric("Valor de rescate", f"USD {valor_rescate:,.2f}")

            st.markdown("### Evolución de la inversión")
            graf_df = df_resultado.set_index("Date")[[
                "Aporte_Acum",
                "Valor_Cuenta",
                "Valor_Rescate"
            ]]
            st.line_chart(graf_df)

            st.markdown("### Resumen anual")
            resumen_anual = construir_resumen_anual(
                df_resultado,
                anio_inicio=int(anio_inicio),
                mes_inicio=int(mes_inicio)
            )

            styled_resumen = formatear_resumen_anual(resumen_anual)
            st.dataframe(styled_resumen, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Error en el cálculo: {e}")

# =========================================================
# TABLA DE FONDOS NO DISPONIBLES
# =========================================================
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