import io

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from modules.fund_loader import cargar_todos_los_fondos
from modules.portfolio_builder import construir_portafolio
from modules.simulator import construir_resumen_anual, simular_mis, simular_mss
from modules.utils import LISTA_MESES, mes_numero

st.set_page_config(page_title="Ilustrador Financiero", page_icon="💼", layout="wide")

# =========================================================
# LOGIN
# =========================================================
APP_PASSWORD = "test"


def check_password() -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔒 Acceso")
    st.write("Introduce la contraseña para continuar.")

    password = st.text_input("Contraseña", type="password")

    if st.button("Entrar", use_container_width=True):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False


if not check_password():
    st.stop()

# =========================================================
# UTILIDADES
# =========================================================
def month_end(year: int, month: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def fmt_usd(x: float) -> str:
    return f"USD {x:,.2f}"


def fmt_pct(x: float) -> str:
    return f"{x:.2f}%"


def color_valores(val):
    try:
        v = float(str(val).replace("USD", "").replace("%", "").replace(",", "").strip())
        if v < 0:
            return "color:red;font-weight:bold"
        if v > 0:
            return "color:green;font-weight:bold"
        return ""
    except Exception:
        return ""


def style_table(df: pd.DataFrame, money_cols=None, pct_cols=None):
    money_cols = money_cols or []
    pct_cols = pct_cols or []

    out = df.copy()

    for c in money_cols:
        if c in out.columns:
            out[c] = out[c].apply(fmt_usd)

    for c in pct_cols:
        if c in out.columns:
            out[c] = out[c].apply(fmt_pct)

    subset = [c for c in out.columns if c in set(money_cols + pct_cols)]
    return out.style.map(color_valores, subset=subset)


# =========================================================
# FONDOS DISPONIBLES
# =========================================================
def fondos_disponibles_en_fecha(fondos: dict, fecha: pd.Timestamp) -> dict:
    return {
        k: v
        for k, v in fondos.items()
        if pd.Timestamp(v["start_date"]) <= fecha
    }


# =========================================================
# CAMBIOS
# =========================================================
def limpiar_cambios(raw_cambios: list, fecha_inicio: pd.Timestamp) -> list:
    validos = []

    for c in raw_cambios:
        fecha = month_end(c["anio"], c["mes"])
        asig = {k: v for k, v in c["asig"].items() if v > 0}
        total = sum(asig.values())

        if fecha <= fecha_inicio:
            continue
        if total != 100:
            continue
        if not asig:
            continue

        validos.append({
            "fecha": fecha,
            "anio": c["anio"],
            "mes": c["mes"],
            "asig": asig,
        })

    validos = sorted(validos, key=lambda x: x["fecha"])

    dedup = {}
    for c in validos:
        dedup[c["fecha"]] = c

    return [dedup[k] for k in sorted(dedup.keys())]


def construir_segmentos(asignacion_inicial: dict, cambios_validos: list, fecha_inicio: pd.Timestamp):
    segmentos = []

    asign_actual = {k: v for k, v in asignacion_inicial.items() if v > 0}
    fecha_actual = fecha_inicio

    for c in cambios_validos:
        segmentos.append({
            "inicio": fecha_actual,
            "fin": c["fecha"] - pd.offsets.MonthEnd(1),
            "asig": asign_actual.copy(),
        })
        asign_actual = c["asig"].copy()
        fecha_actual = c["fecha"]

    segmentos.append({
        "inicio": fecha_actual,
        "fin": None,
        "asig": asign_actual.copy(),
    })

    return segmentos


# =========================================================
# PORTAFOLIO CON CAMBIOS Y CONTINUIDAD
# =========================================================
def portafolio_con_cambios(
    fondos_all: dict,
    asignacion_inicial: dict,
    cambios_validos: list,
    fecha_inicio: pd.Timestamp,
):
    segmentos = construir_segmentos(asignacion_inicial, cambios_validos, fecha_inicio)

    frames = []
    ultimo_precio = None

    for seg in segmentos:
        fondos_seg = fondos_disponibles_en_fecha(fondos_all, seg["inicio"])
        asig_seg = {k: v for k, v in seg["asig"].items() if v > 0 and k in fondos_seg}

        if not asig_seg or sum(asig_seg.values()) != 100:
            continue

        df_seg = construir_portafolio(fondos_seg, asig_seg)
        df_seg = df_seg[df_seg["Date"] >= seg["inicio"]].copy()

        if seg["fin"] is not None:
            df_seg = df_seg[df_seg["Date"] <= seg["fin"]].copy()

        if df_seg.empty:
            continue

        if ultimo_precio is not None:
            factor = ultimo_precio / float(df_seg["Price"].iloc[0])
            df_seg["Price"] = df_seg["Price"] * factor

        df_seg["Segmento"] = seg["inicio"].strftime("%Y-%m")
        frames.append(df_seg)
        ultimo_precio = float(df_seg["Price"].iloc[-1])

    if not frames:
        raise ValueError("No fue posible construir el portafolio con los tramos definidos.")

    df_total = pd.concat(frames, ignore_index=True)
    df_total = df_total.drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    df_total["Return"] = df_total["Price"].pct_change().fillna(0.0)

    return df_total, segmentos


# =========================================================
# EVOLUCIÓN POR FONDO, TRAMO A TRAMO
# =========================================================
def construir_evolucion_por_fondo(
    fondos_all: dict,
    segmentos: list,
    capital_inicial_base: float,
) -> pd.DataFrame:
    frames = []
    capital_tramo = capital_inicial_base

    for idx, seg in enumerate(segmentos, start=1):
        fondos_seg = fondos_disponibles_en_fecha(fondos_all, seg["inicio"])
        asig_seg = {k: v for k, v in seg["asig"].items() if v > 0 and k in fondos_seg}

        if not asig_seg:
            continue

        finales = []

        for fondo, pct in asig_seg.items():
            df = fondos_seg[fondo]["df_monthly"].copy()
            df = df[df["Date"] >= seg["inicio"]].copy()

            if seg["fin"] is not None:
                df = df[df["Date"] <= seg["fin"]].copy()

            if df.empty:
                continue

            base = capital_tramo * (pct / 100.0)
            precio0 = float(df["Price"].iloc[0])

            df_out = df[["Date", "Price"]].copy()
            df_out["Fondo"] = fondo
            df_out["Segmento_N"] = idx
            df_out["Segmento_Inicio"] = seg["inicio"]
            df_out["Valor"] = base * (df_out["Price"] / precio0)
            df_out["Asignacion_Tramo"] = pct
            df_out["Capital_Tramo"] = base

            finales.append(float(df_out["Valor"].iloc[-1]))
            frames.append(
                df_out[[
                    "Date", "Fondo", "Segmento_N", "Segmento_Inicio",
                    "Valor", "Asignacion_Tramo", "Capital_Tramo"
                ]]
            )

        if finales:
            capital_tramo = sum(finales)

    if not frames:
        return pd.DataFrame(
            columns=[
                "Date", "Fondo", "Segmento_N", "Segmento_Inicio",
                "Valor", "Asignacion_Tramo", "Capital_Tramo"
            ]
        )

    df_long = pd.concat(frames, ignore_index=True)
    df_long = df_long.sort_values(["Date", "Fondo"]).reset_index(drop=True)
    return df_long


# =========================================================
# TABLAS DE ESTADO
# =========================================================
def construir_estado_final_sin_cambios(
    df_evol_fondos: pd.DataFrame,
    asignacion_inicial: dict,
    capital_inicial_base: float,
) -> pd.DataFrame:
    if df_evol_fondos.empty:
        return pd.DataFrame()

    ult = (
        df_evol_fondos.sort_values("Date")
        .groupby("Fondo", as_index=False)
        .last()
    )

    ult["Asignación inicial"] = ult["Fondo"].map(lambda f: asignacion_inicial.get(f, 0))
    ult["Capital inicial asignado"] = ult["Fondo"].map(
        lambda f: capital_inicial_base * (asignacion_inicial.get(f, 0) / 100.0)
    )
    ult["Valor actual"] = ult["Valor"]
    ult["Ganancia / pérdida no realizada"] = ult["Valor actual"] - ult["Capital inicial asignado"]
    ult["Rentabilidad acumulada"] = ult.apply(
        lambda r: ((r["Valor actual"] / r["Capital inicial asignado"]) - 1) * 100
        if r["Capital inicial asignado"] > 0 else 0.0,
        axis=1
    )

    total = ult["Valor actual"].sum()
    ult["Participación actual"] = (ult["Valor actual"] / total) * 100 if total > 0 else 0.0

    out = ult[[
        "Fondo",
        "Asignación inicial",
        "Capital inicial asignado",
        "Valor actual",
        "Ganancia / pérdida no realizada",
        "Rentabilidad acumulada",
        "Participación actual",
    ]].copy()

    out = out.sort_values("Valor actual", ascending=False).reset_index(drop=True)

    total_row = pd.DataFrame([{
        "Fondo": "Total",
        "Asignación inicial": out["Asignación inicial"].sum(),
        "Capital inicial asignado": out["Capital inicial asignado"].sum(),
        "Valor actual": out["Valor actual"].sum(),
        "Ganancia / pérdida no realizada": out["Ganancia / pérdida no realizada"].sum(),
        "Rentabilidad acumulada": (
            ((out["Valor actual"].sum() / out["Capital inicial asignado"].sum()) - 1) * 100
            if out["Capital inicial asignado"].sum() > 0 else 0.0
        ),
        "Participación actual": 100.0 if out["Valor actual"].sum() > 0 else 0.0,
    }])

    return pd.concat([out, total_row], ignore_index=True)


def construir_composicion_con_cambios(
    df_evol_fondos: pd.DataFrame,
    total_valor_real: float,
    fecha_objetivo: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if df_evol_fondos.empty:
        return pd.DataFrame()

    df = df_evol_fondos.copy()
    if fecha_objetivo is not None:
        df = df[df["Date"] <= fecha_objetivo].copy()

    if df.empty:
        return pd.DataFrame()

    ult = (
        df.sort_values("Date")
        .groupby("Fondo", as_index=False)
        .last()
    )

    total_raw = ult["Valor"].sum()
    if total_raw <= 0:
        return pd.DataFrame()

    ult["Participación actual"] = (ult["Valor"] / total_raw) * 100
    ult["Valor actual"] = (ult["Participación actual"] / 100.0) * total_valor_real

    primero = (
        df.groupby("Fondo", as_index=False)["Segmento_Inicio"]
        .min()
        .rename(columns={"Segmento_Inicio": "Primer ingreso"})
    )
    ultimo = (
        df.groupby("Fondo", as_index=False)["Segmento_N"]
        .max()
        .rename(columns={"Segmento_N": "Último tramo"})
    )

    out = ult[["Fondo", "Valor actual", "Participación actual"]].merge(primero, on="Fondo").merge(ultimo, on="Fondo")
    out["Primer ingreso"] = pd.to_datetime(out["Primer ingreso"]).dt.strftime("%Y-%m")

    out = out.sort_values("Valor actual", ascending=False).reset_index(drop=True)

    total_row = pd.DataFrame([{
        "Fondo": "Total",
        "Valor actual": out["Valor actual"].sum(),
        "Participación actual": 100.0 if out["Valor actual"].sum() > 0 else 0.0,
        "Primer ingreso": "",
        "Último tramo": "",
    }])

    return pd.concat([out, total_row], ignore_index=True)


def construir_estado_en_fecha_sin_cambios(
    df_evol_fondos: pd.DataFrame,
    asignacion_inicial: dict,
    capital_inicial_base: float,
    fecha_objetivo: pd.Timestamp,
) -> pd.DataFrame:
    df = df_evol_fondos[df_evol_fondos["Date"] <= fecha_objetivo].copy()
    if df.empty:
        return pd.DataFrame()

    ult = df.sort_values("Date").groupby("Fondo", as_index=False).last()

    ult["Asignación inicial"] = ult["Fondo"].map(lambda f: asignacion_inicial.get(f, 0))
    ult["Capital inicial asignado"] = ult["Fondo"].map(
        lambda f: capital_inicial_base * (asignacion_inicial.get(f, 0) / 100.0)
    )
    ult["Valor actual"] = ult["Valor"]
    ult["Ganancia / pérdida no realizada"] = ult["Valor actual"] - ult["Capital inicial asignado"]
    ult["Rentabilidad acumulada"] = ult.apply(
        lambda r: ((r["Valor actual"] / r["Capital inicial asignado"]) - 1) * 100
        if r["Capital inicial asignado"] > 0 else 0.0,
        axis=1
    )

    total = ult["Valor actual"].sum()
    ult["Participación actual"] = (ult["Valor actual"] / total) * 100 if total > 0 else 0.0

    out = ult[[
        "Fondo",
        "Asignación inicial",
        "Capital inicial asignado",
        "Valor actual",
        "Ganancia / pérdida no realizada",
        "Rentabilidad acumulada",
        "Participación actual",
    ]].copy()

    out = out.sort_values("Valor actual", ascending=False).reset_index(drop=True)

    total_row = pd.DataFrame([{
        "Fondo": "Total",
        "Asignación inicial": out["Asignación inicial"].sum(),
        "Capital inicial asignado": out["Capital inicial asignado"].sum(),
        "Valor actual": out["Valor actual"].sum(),
        "Ganancia / pérdida no realizada": out["Ganancia / pérdida no realizada"].sum(),
        "Rentabilidad acumulada": (
            ((out["Valor actual"].sum() / out["Capital inicial asignado"].sum()) - 1) * 100
            if out["Capital inicial asignado"].sum() > 0 else 0.0
        ),
        "Participación actual": 100.0 if out["Valor actual"].sum() > 0 else 0.0,
    }])

    return pd.concat([out, total_row], ignore_index=True)


# =========================================================
# PDF
# =========================================================
def generar_pdf_premium(
    cliente: str,
    producto: str,
    fecha_inicio: pd.Timestamp,
    fecha_reporte: pd.Timestamp,
    df_resultado: pd.DataFrame,
    resumen_anual: pd.DataFrame,
    tabla_portafolio: pd.DataFrame,
    tabla_tipo: str,
    df_evol_fondos: pd.DataFrame,
    segmentos: list,
):
    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:
        # Página 1
        fig = plt.figure(figsize=(11, 8))
        plt.figtext(0.08, 0.93, "Ilustración Financiera", fontsize=20, weight="bold")
        plt.figtext(0.08, 0.89, f"Cliente: {cliente}", fontsize=11)
        plt.figtext(0.08, 0.86, f"Producto: {producto}", fontsize=11)
        plt.figtext(0.08, 0.83, f"Inicio: {fecha_inicio.strftime('%Y-%m')}", fontsize=11)
        plt.figtext(0.08, 0.80, f"Reporte a: {fecha_reporte.strftime('%Y-%m')}", fontsize=11)

        valor_final = float(df_resultado["Valor_Cuenta"].iloc[-1])
        rescate_final = float(df_resultado["Valor_Rescate"].iloc[-1])
        aporte_final = float(df_resultado["Aporte_Acum"].iloc[-1])

        plt.figtext(0.08, 0.73, f"Aporte acumulado: {fmt_usd(aporte_final)}", fontsize=11)
        plt.figtext(0.08, 0.70, f"Valor en cuenta: {fmt_usd(valor_final)}", fontsize=11)
        plt.figtext(0.08, 0.67, f"Valor de rescate: {fmt_usd(rescate_final)}", fontsize=11)

        ax = fig.add_axes([0.08, 0.10, 0.84, 0.50])
        plot_df = df_resultado.set_index("Date")[["Aporte_Acum", "Valor_Cuenta", "Valor_Rescate"]].rename(
            columns={
                "Aporte_Acum": "Aporte acumulado",
                "Valor_Cuenta": "Valor en cuenta",
                "Valor_Rescate": "Valor de rescate",
            }
        )
        plot_df.plot(ax=ax, linewidth=2)
        ax.set_title("Evolución de la ilustración")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left")

        for seg in segmentos[1:]:
            if seg["inicio"] <= fecha_reporte:
                ax.axvline(seg["inicio"], linestyle="--", alpha=0.45)

        pdf.savefig(fig, bbox_inches="tight")
        plt.close()

        # Página 2
        fig2 = plt.figure(figsize=(11, 8))
        ax2 = fig2.add_axes([0, 0, 1, 1])
        ax2.axis("off")
        plt.figtext(0.08, 0.93, "Evolución anual", fontsize=18, weight="bold")

        resumen_pdf = resumen_anual.copy()
        for col in ["Aporte_Acum", "Retiro", "Valor_Cuenta", "Valor_Rescate"]:
            if col in resumen_pdf.columns:
                resumen_pdf[col] = resumen_pdf[col].apply(fmt_usd)
        for col in ["Rendimiento", "Rendimiento_Acumulado"]:
            if col in resumen_pdf.columns:
                resumen_pdf[col] = resumen_pdf[col].apply(fmt_pct)

        tabla2 = ax2.table(
            cellText=resumen_pdf.values,
            colLabels=resumen_pdf.columns,
            cellLoc="center",
            loc="center",
            bbox=[0.04, 0.10, 0.92, 0.75],
        )
        tabla2.auto_set_font_size(False)
        tabla2.set_fontsize(9)
        pdf.savefig(fig2, bbox_inches="tight")
        plt.close()

        # Página 3
        fig3 = plt.figure(figsize=(11, 8))
        titulo = "Estado final por fondo" if tabla_tipo == "clasico" else "Composición actual del portafolio"
        plt.figtext(0.08, 0.93, titulo, fontsize=18, weight="bold")

        ax3 = fig3.add_axes([0.04, 0.45, 0.92, 0.35])
        ax3.axis("off")

        tabla_pdf = tabla_portafolio.copy()
        for col in ["Capital inicial asignado", "Valor actual", "Ganancia / pérdida no realizada"]:
            if col in tabla_pdf.columns:
                tabla_pdf[col] = tabla_pdf[col].apply(fmt_usd)
        for col in ["Asignación inicial", "Rentabilidad acumulada", "Participación actual"]:
            if col in tabla_pdf.columns:
                tabla_pdf[col] = tabla_pdf[col].apply(fmt_pct)

        tabla3 = ax3.table(
            cellText=tabla_pdf.values,
            colLabels=tabla_pdf.columns,
            cellLoc="center",
            loc="center",
            bbox=[0.00, 0.00, 1.00, 1.00],
        )
        tabla3.auto_set_font_size(False)
        tabla3.set_fontsize(8)

        tabla_sin_total = tabla_portafolio[tabla_portafolio["Fondo"] != "Total"].copy()
        if "Asignación inicial" in tabla_sin_total.columns:
            inicial = tabla_sin_total["Asignación inicial"]
        else:
            inicial = None

        actual = tabla_sin_total["Participación actual"] if "Participación actual" in tabla_sin_total.columns else None

        ax31 = fig3.add_axes([0.08, 0.08, 0.30, 0.25])
        ax32 = fig3.add_axes([0.52, 0.08, 0.30, 0.25])
        ax33 = fig3.add_axes([0.84, 0.08, 0.14, 0.25])
        ax33.axis("off")

        if inicial is not None:
            wedges1, _, _ = ax31.pie(
                inicial,
                labels=None,
                autopct="%1.1f%%",
                wedgeprops={"width": 0.4},
                startangle=90,
            )
            ax31.set_title("Composición inicial")
        else:
            ax31.axis("off")

        if actual is not None:
            wedges2, _, _ = ax32.pie(
                actual,
                labels=None,
                autopct="%1.1f%%",
                wedgeprops={"width": 0.4},
                startangle=90,
            )
            ax32.set_title("Composición actual")
            ax33.legend(wedges2, tabla_sin_total["Fondo"], loc="center left", frameon=False)
        else:
            ax32.axis("off")

        pdf.savefig(fig3, bbox_inches="tight")
        plt.close()

        # Página 4
        fig4 = plt.figure(figsize=(11, 8))
        plt.figtext(0.08, 0.93, "Timeline de estrategia y evolución por fondo", fontsize=18, weight="bold")

        ax4_text = fig4.add_axes([0.08, 0.66, 0.84, 0.20])
        ax4_text.axis("off")

        y = 0.95
        for i, seg in enumerate(segmentos, start=1):
            if seg["inicio"] > fecha_reporte:
                continue
            fin_real = seg["fin"]
            if fin_real is None or fin_real > fecha_reporte:
                fin_txt = "en adelante" if fecha_reporte == df_resultado["Date"].max() else fecha_reporte.strftime("%Y-%m")
            else:
                fin_txt = fin_real.strftime("%Y-%m")

            asign_txt = ", ".join([f"{k}: {v}%" for k, v in seg["asig"].items() if v > 0])
            ax4_text.text(0.0, y, f"Tramo {i}: {seg['inicio'].strftime('%Y-%m')} → {fin_txt}", fontsize=10)
            ax4_text.text(0.03, y - 0.10, asign_txt[:170], fontsize=9)
            y -= 0.24

        ax4 = fig4.add_axes([0.08, 0.10, 0.84, 0.45])
        if not df_evol_fondos.empty:
            df_plot = (
                df_evol_fondos[df_evol_fondos["Date"] <= fecha_reporte]
                .pivot_table(index="Date", columns="Fondo", values="Valor", aggfunc="last")
            )
            if not df_plot.empty:
                df_plot.plot(ax=ax4, linewidth=2)
                ax4.set_title("Evolución por fondo")
                ax4.grid(True, alpha=0.25)
                ax4.legend(loc="upper left")

        pdf.savefig(fig4, bbox_inches="tight")
        plt.close()

    buffer.seek(0)
    return buffer


# =========================================================
# APP
# =========================================================
st.markdown("# 💼 Ilustrador Financiero")
st.divider()

fondos = cargar_todos_los_fondos("data")

c1, c2 = st.columns(2)
with c1:
    producto = st.selectbox("Producto", ["MIS", "MSS"])
with c2:
    plazo = st.selectbox("Plazo", list(range(5, 21))) if producto == "MSS" else None

c3, c4 = st.columns(2)
with c3:
    mes_txt = st.selectbox("Mes de inicio", LISTA_MESES)
    mes_inicio = mes_numero(mes_txt)
with c4:
    anio_inicio = st.selectbox("Año de inicio", list(range(2018, 2027)))

cliente = st.text_input("Cliente", value="Cliente")
fecha_inicio = month_end(anio_inicio, mes_inicio)

st.divider()

fondos_disp_inicio = fondos_disponibles_en_fecha(fondos, fecha_inicio)

fondos_sel = st.multiselect(
    "Fondos de la estrategia inicial",
    list(fondos_disp_inicio.keys()),
    max_selections=8,
)

asignaciones = {}
total_inicial = 0

if fondos_sel:
    st.subheader("Asignación inicial")
    for f in fondos_sel:
        p = st.number_input(f, min_value=0, max_value=100, step=10, key=f"init_{f}")
        asignaciones[f] = p
        total_inicial += p

    st.write(f"Total asignado: {total_inicial}%")

raw_cambios = []

if fondos_sel and st.checkbox("Modificar composición del portafolio en fechas específicas"):
    num_cambios = st.number_input("Número de cambios", min_value=1, max_value=5, value=1)

    for i in range(int(num_cambios)):
        st.markdown(f"### Cambio {i+1}")

        d1, d2 = st.columns(2)
        with d1:
            mes_c_txt = st.selectbox("Mes", LISTA_MESES, key=f"mes_{i}")
            mes_c = mes_numero(mes_c_txt)
        with d2:
            anio_c = st.selectbox("Año", list(range(anio_inicio, 2027)), key=f"anio_{i}")

        fecha_cambio = month_end(anio_c, mes_c)
        fondos_disp_fecha = fondos_disponibles_en_fecha(fondos, fecha_cambio)

        fondos_cambio = st.multiselect(
            "Fondos para este cambio",
            list(fondos_disp_fecha.keys()),
            key=f"fondos_cambio_{i}",
        )

        nueva = {}
        total_cambio = 0

        for f in fondos_cambio:
            p = st.number_input(
                f"{f}",
                min_value=0,
                max_value=100,
                step=10,
                key=f"{f}_{i}",
            )
            nueva[f] = p
            total_cambio += p

        st.write(f"Total del cambio: {total_cambio}%")
        if total_cambio != 100:
            st.error("La composición del cambio debe sumar 100%.")

        raw_cambios.append({
            "anio": anio_c,
            "mes": mes_c,
            "asig": nueva,
        })

st.divider()

if fondos_sel and total_inicial == 100:
    st.subheader("Configuración financiera")

    aportes_extra = []

    if producto == "MIS":
        monto_inicial = st.number_input("Monto inicial", min_value=10000, value=10000, step=1000)
    else:
        freq = st.selectbox("Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"])
        minimos = {"Mensual": 150, "Trimestral": 450, "Semestral": 900, "Anual": 1800}
        aporte = st.number_input("Aporte por período", min_value=minimos[freq], value=minimos[freq], step=minimos[freq])

        if st.checkbox("Agregar aportes extra"):
            num_extra = st.number_input("Número de aportes extra", min_value=1, max_value=5, value=1, key="num_extra")
            for j in range(int(num_extra)):
                e1, e2, e3 = st.columns(3)
                with e1:
                    monto_extra = st.number_input(f"Monto extra {j+1}", min_value=1500, value=1500, step=500, key=f"monto_extra_{j}")
                with e2:
                    mes_extra_txt = st.selectbox(f"Mes extra {j+1}", LISTA_MESES, key=f"mes_extra_{j}")
                    mes_extra = mes_numero(mes_extra_txt)
                with e3:
                    anio_extra = st.selectbox(f"Año extra {j+1}", list(range(anio_inicio, 2027)), key=f"anio_extra_{j}")

                aportes_extra.append({
                    "monto": float(monto_extra),
                    "anio": int(anio_extra),
                    "mes": int(mes_extra),
                })

    # Fecha del reporte
    st.subheader("Fecha del reporte")
    modo_reporte = st.radio(
        "Generar resultados",
        ["A la última fecha disponible", "A una fecha específica"],
        horizontal=True,
    )

    if modo_reporte == "A una fecha específica":
        r1, r2 = st.columns(2)
        with r1:
            mes_rep_txt = st.selectbox("Mes del reporte", LISTA_MESES, key="rep_mes")
            mes_rep = mes_numero(mes_rep_txt)
        with r2:
            anio_rep = st.selectbox("Año del reporte", list(range(anio_inicio, 2027)), key="rep_anio")
        fecha_reporte = month_end(int(anio_rep), int(mes_rep))
    else:
        fecha_reporte = None

    cambios_validos = limpiar_cambios(raw_cambios, fecha_inicio)

    if fecha_reporte is not None:
        cambios_validos = [c for c in cambios_validos if c["fecha"] <= fecha_reporte]

    df_port, segmentos = portafolio_con_cambios(
        fondos,
        asignaciones,
        cambios_validos,
        fecha_inicio,
    )

    if fecha_reporte is not None:
        df_port = df_port[df_port["Date"] <= fecha_reporte].copy()

    if producto == "MIS":
        df_resultado = simular_mis(
            df_port,
            float(monto_inicial),
            int(anio_inicio),
            int(mes_inicio),
            [],
            [],
        )
        capital_base = float(monto_inicial)
    else:
        df_resultado = simular_mss(
            df_port,
            int(plazo),
            float(aporte),
            freq,
            int(anio_inicio),
            int(mes_inicio),
            [],
        )

        if aportes_extra:
            aportes_extra_filtrados = aportes_extra
            if fecha_reporte is not None:
                aportes_extra_filtrados = [
                    a for a in aportes_extra
                    if month_end(a["anio"], a["mes"]) <= fecha_reporte
                ]

            df_extras = simular_mis(
                df_port,
                0.0,
                int(anio_inicio),
                int(mes_inicio),
                aportes_extra_filtrados,
                [],
            )

            for col in ["Aporte_Acum", "Valor_Cuenta", "Valor_Rescate", "Retiro"]:
                df_resultado[col] = df_resultado[col].fillna(0) + df_extras[col].fillna(0)

        capital_base = float(df_resultado["Aporte_Acum"].iloc[-1])

    fecha_final_resultado = pd.to_datetime(df_resultado["Date"].max())
    if fecha_reporte is None:
        fecha_reporte_real = fecha_final_resultado
    else:
        fecha_reporte_real = min(fecha_reporte, fecha_final_resultado)

    capital_evol = float(monto_inicial) if producto == "MIS" else max(capital_base, 10000.0)
    df_evol_fondos = construir_evolucion_por_fondo(fondos, segmentos, capital_evol)
    df_evol_fondos = df_evol_fondos[df_evol_fondos["Date"] <= fecha_reporte_real].copy()

    resumen_anual = construir_resumen_anual(df_resultado, int(anio_inicio), int(mes_inicio))

    hay_cambios = len(cambios_validos) > 0

    if hay_cambios:
        tabla_portafolio = construir_composicion_con_cambios(
            df_evol_fondos,
            total_valor_real=float(df_resultado["Valor_Cuenta"].iloc[-1]),
            fecha_objetivo=fecha_reporte_real,
        )
        tabla_tipo = "composicion"
    else:
        tabla_portafolio = construir_estado_final_sin_cambios(
            df_evol_fondos,
            asignaciones,
            capital_evol,
        )
        tabla_tipo = "clasico"

    # =========================
    # RESULTADOS EN APP
    # =========================
    st.subheader("Evolución de la ilustración")

    fig_app, ax_app = plt.subplots(figsize=(10, 4))
    df_plot_app = df_resultado.set_index("Date")[["Aporte_Acum", "Valor_Cuenta", "Valor_Rescate"]].rename(
        columns={
            "Aporte_Acum": "Aporte acumulado",
            "Valor_Cuenta": "Valor en cuenta",
            "Valor_Rescate": "Valor de rescate",
        }
    )
    df_plot_app.plot(ax=ax_app, linewidth=2)

    for seg in segmentos[1:]:
        if seg["inicio"] <= fecha_reporte_real:
            ax_app.axvline(seg["inicio"], linestyle="--", alpha=0.45)

    ax_app.grid(True, alpha=0.25)
    ax_app.set_ylabel("USD")
    ax_app.legend(loc="upper left")
    st.pyplot(fig_app)
    plt.close(fig_app)

    c1, c2, c3 = st.columns(3)
    c1.metric("Aporte acumulado", fmt_usd(float(df_resultado["Aporte_Acum"].iloc[-1])))
    c2.metric("Valor en cuenta", fmt_usd(float(df_resultado["Valor_Cuenta"].iloc[-1])))
    c3.metric("Valor de rescate", fmt_usd(float(df_resultado["Valor_Rescate"].iloc[-1])))

    st.subheader("Timeline de estrategia")
    for i, seg in enumerate(segmentos, start=1):
        if seg["inicio"] > fecha_reporte_real:
            continue
        fin_real = seg["fin"]
        if fin_real is None or fin_real > fecha_reporte_real:
            fin_txt = "en adelante" if fecha_reporte is None else fecha_reporte_real.strftime("%Y-%m")
        else:
            fin_txt = fin_real.strftime("%Y-%m")
        st.write(f"**Tramo {i}** — {seg['inicio'].strftime('%Y-%m')} → {fin_txt}")
        st.caption(", ".join([f"{k}: {v}%" for k, v in seg["asig"].items() if v > 0]))

    st.subheader("Resumen anual")
    st.dataframe(
        style_table(
            resumen_anual,
            money_cols=["Aporte_Acum", "Retiro", "Valor_Cuenta", "Valor_Rescate"],
            pct_cols=["Rendimiento", "Rendimiento_Acumulado"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Detalle mensual de la ilustración")
    mensual = df_resultado.copy()
    mensual["Date"] = mensual["Date"].dt.strftime("%Y-%m")
    st.dataframe(
        style_table(
            mensual[["Date", "Aporte_Acum", "Valor_Cuenta", "Valor_Rescate"]],
            money_cols=["Aporte_Acum", "Valor_Cuenta", "Valor_Rescate"],
            pct_cols=[],
        ),
        use_container_width=True,
        hide_index=True,
    )

    titulo_tabla = "Composición actual del portafolio" if hay_cambios else "Estado final por fondo"
    st.subheader(titulo_tabla)

    if tabla_tipo == "clasico":
        st.dataframe(
            style_table(
                tabla_portafolio,
                money_cols=["Capital inicial asignado", "Valor actual", "Ganancia / pérdida no realizada"],
                pct_cols=["Asignación inicial", "Rentabilidad acumulada", "Participación actual"],
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.dataframe(
            style_table(
                tabla_portafolio,
                money_cols=["Valor actual"],
                pct_cols=["Participación actual"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Evolución por fondo")
    if not df_evol_fondos.empty:
        wide = df_evol_fondos.pivot_table(index="Date", columns="Fondo", values="Valor", aggfunc="last")
        st.line_chart(wide)

        anual_fondo = df_evol_fondos.copy()
        anual_fondo["Año"] = anual_fondo["Date"].dt.year
        anual_fondo = (
            anual_fondo.sort_values("Date")
            .groupby(["Año", "Fondo"], as_index=False)
            .last()[["Año", "Fondo", "Valor"]]
        )

        st.dataframe(
            style_table(
                anual_fondo,
                money_cols=["Valor"],
                pct_cols=[],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Estado en fecha")
    s1, s2 = st.columns(2)
    with s1:
        mes_s_txt = st.selectbox("Mes snapshot", LISTA_MESES, key="snap_mes")
        mes_s = mes_numero(mes_s_txt)
    with s2:
        anio_s = st.selectbox("Año snapshot", sorted(df_resultado["Date"].dt.year.unique()), key="snap_anio")

    fecha_s = month_end(int(anio_s), int(mes_s))
    df_res_snap = df_resultado[df_resultado["Date"] <= fecha_s]

    if not df_res_snap.empty:
        fila_s = df_res_snap.iloc[-1]
        s31, s32, s33 = st.columns(3)
        s31.metric("Aporte acumulado", fmt_usd(float(fila_s["Aporte_Acum"])))
        s32.metric("Valor en cuenta", fmt_usd(float(fila_s["Valor_Cuenta"])))
        s33.metric("Valor de rescate", fmt_usd(float(fila_s["Valor_Rescate"])))

        if hay_cambios:
            tabla_fecha = construir_composicion_con_cambios(
                df_evol_fondos,
                total_valor_real=float(fila_s["Valor_Cuenta"]),
                fecha_objetivo=fecha_s,
            )
            st.dataframe(
                style_table(
                    tabla_fecha,
                    money_cols=["Valor actual"],
                    pct_cols=["Participación actual"],
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            tabla_fecha = construir_estado_en_fecha_sin_cambios(
                df_evol_fondos,
                asignaciones,
                capital_evol,
                fecha_s,
            )
            st.dataframe(
                style_table(
                    tabla_fecha,
                    money_cols=["Capital inicial asignado", "Valor actual", "Ganancia / pérdida no realizada"],
                    pct_cols=["Asignación inicial", "Rentabilidad acumulada", "Participación actual"],
                ),
                use_container_width=True,
                hide_index=True,
            )

    pdf_bytes = generar_pdf_premium(
        cliente=cliente,
        producto=producto,
        fecha_inicio=fecha_inicio,
        fecha_reporte=fecha_reporte_real,
        df_resultado=df_resultado,
        resumen_anual=resumen_anual,
        tabla_portafolio=tabla_portafolio,
        tabla_tipo=tabla_tipo,
        df_evol_fondos=df_evol_fondos,
        segmentos=segmentos,
    )

    nombre_archivo = f"Ilustracion_{cliente.replace(' ', '_')}_{fecha_reporte_real.strftime('%Y_%m')}.pdf"
    st.download_button(
        "📄 Descargar PDF",
        data=pdf_bytes,
        file_name=nombre_archivo,
        mime="application/pdf",
        use_container_width=True,
    )
else:
    st.info("Selecciona fondos y define una asignación inicial de 100% para generar la ilustración.")