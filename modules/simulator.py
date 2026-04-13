import pandas as pd

FACTORES_COSTOS = {
    5: (0.2475, 0.0619),
    6: (0.2970, 0.0743),
    7: (0.3465, 0.0866),
    8: (0.3960, 0.0990),
    9: (0.4455, 0.1114),
    10: (0.4950, 0.1238),
    11: (0.5445, 0.1361),
    12: (0.5940, 0.1485),
    13: (0.6435, 0.1609),
    14: (0.6930, 0.1733),
    15: (0.7425, 0.1856),
    16: (0.7920, 0.1980),
    17: (0.8415, 0.2104),
    18: (0.8910, 0.2228),
    19: (0.9405, 0.2351),
    20: (0.9900, 0.2475),
}

LISTA_MESES = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sept", "oct", "nov", "dic"
]


def fmt_usd(x):
    return f"USD {x:,.2f}"


def fmt_pct(x):
    return f"{x:+.2f}%"


def xnpv(rate, cashflows):
    total = 0.0
    t0 = cashflows[0][0]
    for fecha, monto in cashflows:
        dias = (fecha - t0).days
        total += monto / ((1 + rate) ** (dias / 365.25))
    return total


def xirr(cashflows, guess=0.08):
    if not cashflows or len(cashflows) < 2:
        return None

    positivos = any(m > 0 for _, m in cashflows)
    negativos = any(m < 0 for _, m in cashflows)

    if not positivos or not negativos:
        return None

    low, high = -0.9999, 10.0

    try:
        npv_low = xnpv(low, cashflows)
        npv_high = xnpv(high, cashflows)
    except Exception:
        return None

    intentos = 0
    while npv_low * npv_high > 0 and intentos < 50:
        high *= 2
        try:
            npv_high = xnpv(high, cashflows)
        except Exception:
            return None
        intentos += 1

    if npv_low * npv_high > 0:
        return None

    for _ in range(200):
        mid = (low + high) / 2
        npv_mid = xnpv(mid, cashflows)

        if abs(npv_mid) < 1e-7:
            return mid

        if npv_low * npv_mid < 0:
            high = mid
            npv_high = npv_mid
        else:
            low = mid
            npv_low = npv_mid

    return (low + high) / 2


def calcular_rendimiento_resumen(df: pd.DataFrame, resumen: pd.DataFrame, tipo_plan: str):
    if resumen.empty or df.empty:
        return "Rendimiento anual", 0.0

    val_final = float(resumen["Valor_Cuenta"].iloc[-1])

    if tipo_plan == "MIS":
        inv_total = float(resumen["Aporte_Acum"].iloc[-1])

        if inv_total <= 0 or val_final <= 0 or len(df) < 2:
            return "Rendimiento anual promedio", 0.0

        años = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days / 365.25
        if años <= 0:
            return "Rendimiento anual promedio", 0.0

        tasa = ((val_final / inv_total) ** (1 / años) - 1) * 100
        return "Rendimiento anual promedio", tasa

    cashflows = []

    aporte_prev = 0.0
    for _, row in df.iterrows():
        fecha = pd.Timestamp(row["Date"]).to_pydatetime()

        aporte_acum = float(row["Aporte_Acum"])
        aporte_nuevo = aporte_acum - aporte_prev
        aporte_prev = aporte_acum

        if aporte_nuevo > 0:
            cashflows.append((fecha, -aporte_nuevo))

        retiro = float(row["Retiro"])
        if retiro > 0:
            cashflows.append((fecha, retiro))

    fecha_final = pd.Timestamp(df["Date"].iloc[-1]).to_pydatetime()
    cashflows.append((fecha_final, val_final))

    tasa_xirr = xirr(cashflows)

    if tasa_xirr is None:
        return "Rendimiento anual equivalente del plan", 0.0

    return "Rendimiento anual equivalente del plan", tasa_xirr * 100


def simular_mis(
    df_base: pd.DataFrame,
    monto_inicial: float,
    anio_inicio: int,
    mes_inicio: int,
    aportes_extra: list,
    retiros_programados: list
) -> pd.DataFrame:
    df = df_base.copy()
    fecha_filtro = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1) + pd.offsets.MonthEnd(0)
    df = df[df["Date"] >= fecha_filtro].copy().reset_index(drop=True)

    if df.empty:
        raise ValueError("No hay datos históricos disponibles desde la fecha seleccionada.")

    df["Year"] = df["Date"].dt.year
    retornos = df["Return"].values

    cubetas = [{
        "monto": float(monto_inicial),
        "saldo": 0.0,
        "edad": 0,
        "activa": False,
        "ini": (anio_inicio, mes_inicio)
    }]

    for extra in aportes_extra:
        cubetas.append({
            "monto": float(extra["monto"]),
            "saldo": 0.0,
            "edad": 0,
            "activa": False,
            "ini": (int(extra["anio"]), int(extra["mes"]))
        })

    lista_vn, lista_vr, lista_aportes_acum, lista_retiros = [], [], [], []
    acumulado_aportes = 0.0

    for i in range(len(df)):
        fecha_act = df["Date"].iloc[i]
        anio_act, mes_act = fecha_act.year, fecha_act.month

        retiro_mes = 0.0
        for r in retiros_programados:
            if int(r["anio"]) == anio_act and int(r["mes"]) == mes_act:
                retiro_mes += float(r["monto"])
        lista_retiros.append(retiro_mes)

        saldo_total_previo = sum(c["saldo"] for c in cubetas if c["activa"])

        vn_mes_total = 0.0
        vr_mes_total = 0.0

        for c in cubetas:
            if not c["activa"] and (
                anio_act > c["ini"][0] or
                (anio_act == c["ini"][0] and mes_act >= c["ini"][1])
            ):
                c["activa"] = True
                c["saldo"] = c["monto"]
                acumulado_aportes += c["monto"]
                saldo_total_previo += c["monto"]

            if c["activa"]:
                if c["edad"] > 0:
                    c["saldo"] *= (1 + retornos[i])

                if retiro_mes > 0 and saldo_total_previo > 0:
                    peso = c["saldo"] / saldo_total_previo if saldo_total_previo > 0 else 0
                    deduccion_retiro = retiro_mes * peso
                    c["saldo"] = max(0.0, c["saldo"] - deduccion_retiro)

                costo_establecimiento = (c["monto"] * 0.016) / 12.0
                if c["edad"] < 60:
                    c["saldo"] -= costo_establecimiento
                else:
                    c["saldo"] -= (c["saldo"] * (0.01 / 12.0))

                c["saldo"] = max(0.0, c["saldo"])

                penalizacion = 0.0
                if c["edad"] < 60:
                    meses_restantes = 60 - (c["edad"] + 1)
                    penalizacion = meses_restantes * costo_establecimiento

                vr_cubeta = max(0.0, c["saldo"] - penalizacion)

                vn_mes_total += c["saldo"]
                vr_mes_total += vr_cubeta
                c["edad"] += 1

        lista_vn.append(vn_mes_total)
        lista_vr.append(vr_mes_total)
        lista_aportes_acum.append(acumulado_aportes)

    df["Aporte_Acum"] = lista_aportes_acum
    df["Valor_Cuenta"] = lista_vn
    df["Valor_Rescate"] = lista_vr
    df["Retiro"] = lista_retiros
    df["Mes_Plan"] = range(1, len(df) + 1)
    return df


def simular_mss(
    df_base: pd.DataFrame,
    plazo_anios: int,
    monto_aporte: float,
    frecuencia_pago: str,
    anio_inicio: int,
    mes_inicio: int,
    retiros_programados: list
) -> pd.DataFrame:
    df = df_base.copy()
    fecha_filtro = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1) + pd.offsets.MonthEnd(0)
    df = df[df["Date"] >= fecha_filtro].copy().reset_index(drop=True)

    if df.empty:
        raise ValueError("No hay datos históricos disponibles desde la fecha seleccionada.")

    df["Year"] = df["Date"].dt.year
    retornos = df["Return"].values

    mapa_pasos = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    step_meses = mapa_pasos[frecuencia_pago]
    pagos_anio = 12 / step_meses
    aporte_anual = monto_aporte * pagos_anio

    factor1, factor2 = FACTORES_COSTOS.get(plazo_anios, (0, 0))
    costo_total_apertura = (aporte_anual * factor1) + (aporte_anual * factor2)
    meses_totales = plazo_anios * 12
    deduccion_mensual = costo_total_apertura / meses_totales if meses_totales > 0 else 0

    lista_vn, lista_vr, lista_aportes_acum, lista_retiros, lista_etapa = [], [], [], [], []
    saldo_actual = 0.0
    aporte_acumulado = 0.0

    for i in range(len(df)):
        fecha_act = df["Date"].iloc[i]

        if i < meses_totales and i % step_meses == 0:
            saldo_actual += monto_aporte
            aporte_acumulado += monto_aporte

        if i > 0:
            saldo_actual *= (1 + retornos[i])

        retiro_mes = 0.0
        for r in retiros_programados:
            if int(r["anio"]) == fecha_act.year and int(r["mes"]) == fecha_act.month:
                retiro_mes += float(r["monto"])
        lista_retiros.append(retiro_mes)

        if retiro_mes > 0:
            saldo_actual = max(0.0, saldo_actual - retiro_mes)

        if i < meses_totales:
            saldo_actual -= deduccion_mensual
            meses_restantes = meses_totales - (i + 1)
            penalizacion = meses_restantes * deduccion_mensual if meses_restantes > 0 else 0
            valor_rescate = max(0.0, saldo_actual - penalizacion)
            etapa = "Acumulación"
        else:
            saldo_actual -= (saldo_actual * (0.01 / 12.0))
            valor_rescate = max(0.0, saldo_actual)
            etapa = "Post-maduración"

        saldo_actual = max(0.0, saldo_actual)

        lista_vn.append(saldo_actual)
        lista_vr.append(valor_rescate)
        lista_aportes_acum.append(aporte_acumulado)
        lista_etapa.append(etapa)

    df["Aporte_Acum"] = lista_aportes_acum
    df["Valor_Cuenta"] = lista_vn
    df["Valor_Rescate"] = lista_vr
    df["Retiro"] = lista_retiros
    df["Etapa"] = lista_etapa
    df["Mes_Plan"] = range(1, len(df) + 1)
    return df


def construir_resumen_anual(df: pd.DataFrame, anio_inicio: int, mes_inicio: int) -> pd.DataFrame:
    df = df.copy().sort_values("Date").reset_index(drop=True)

    if df.empty:
        return pd.DataFrame()

    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month

    ultimo_anio = int(df["Year"].max())
    ultimo_mes = int(df.loc[df["Year"] == ultimo_anio, "Month"].max())

    periodos = []
    idx_periodo = 1

    for anio in sorted(df["Year"].unique()):
        if anio == anio_inicio:
            mes_desde = mes_inicio
            mes_hasta = 12
        elif anio == ultimo_anio:
            mes_desde = 1
            mes_hasta = ultimo_mes
        else:
            mes_desde = 1
            mes_hasta = 12

        sub = df[(df["Year"] == anio) & (df["Month"] >= mes_desde) & (df["Month"] <= mes_hasta)].copy()

        if sub.empty:
            continue

        fila = {
            "Periodo_N": idx_periodo,
            "Periodo_Label": f"{LISTA_MESES[mes_desde - 1]} - {LISTA_MESES[mes_hasta - 1]} {anio}",
            "Aporte_Acum": sub["Aporte_Acum"].iloc[-1],
            "Retiro": sub["Retiro"].sum(),
            "Valor_Cuenta": sub["Valor_Cuenta"].iloc[-1],
            "Valor_Rescate": sub["Valor_Rescate"].iloc[-1],
        }

        if "Etapa" in sub.columns:
            fila["Etapa"] = sub["Etapa"].iloc[-1]

        periodos.append(fila)
        idx_periodo += 1

    resumen = pd.DataFrame(periodos)

    if resumen.empty:
        return resumen

    resumen["Saldo_Inicial"] = resumen["Valor_Cuenta"].shift(1).fillna(0)
    resumen["Aporte_Nuevo"] = resumen["Aporte_Acum"] - resumen["Aporte_Acum"].shift(1).fillna(0)

    resumen["Ganancia"] = (
        resumen["Valor_Cuenta"]
        - resumen["Saldo_Inicial"]
        - resumen["Aporte_Nuevo"]
        + resumen["Retiro"]
    )

    resumen["Base_Calculo"] = (resumen["Saldo_Inicial"] + resumen["Aporte_Nuevo"]).replace(0, pd.NA)
    resumen["Rendimiento"] = (resumen["Ganancia"] / resumen["Base_Calculo"]) * 100
    resumen["Rendimiento"] = resumen["Rendimiento"].fillna(0)

    resumen["Retiro_Acumulado"] = resumen["Retiro"].cumsum()
    base_acumulada = resumen["Aporte_Acum"].replace(0, pd.NA)

    resumen["Rendimiento_Acumulado"] = (
        (resumen["Valor_Cuenta"] + resumen["Retiro_Acumulado"] - resumen["Aporte_Acum"])
        / base_acumulada
    ) * 100
    resumen["Rendimiento_Acumulado"] = resumen["Rendimiento_Acumulado"].fillna(0)

    columnas_finales = [
        "Periodo_N",
        "Periodo_Label",
        "Aporte_Acum",
        "Retiro",
        "Valor_Cuenta",
        "Valor_Rescate",
        "Rendimiento",
        "Rendimiento_Acumulado"
    ]

    if "Etapa" in resumen.columns:
        columnas_finales.append("Etapa")

    return resumen[columnas_finales]