import pandas as pd


def construir_estado_cuenta_final(
    fondos_disponibles: dict,
    asignaciones: dict,
    anio_inicio: int,
    mes_inicio: int,
    capital_base: float
) -> pd.DataFrame:
    """
    Construye un estado de cuenta final por fondo usando:
    - asignación inicial
    - capital inicial aplicado
    - valor actual
    - ganancia/pérdida no realizada
    - participación actual
    - rentabilidad acumulada
    """

    fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1) + pd.offsets.MonthEnd(0)

    filas = []

    for fondo, porcentaje in asignaciones.items():
        if porcentaje <= 0:
            continue

        info = fondos_disponibles[fondo]
        df = info["df_monthly"].copy()
        df = df[df["Date"] >= fecha_inicio].copy().reset_index(drop=True)

        if df.empty:
            continue

        capital_inicial = capital_base * (porcentaje / 100.0)

        precio_inicial = float(df["Price"].iloc[0])
        precio_final = float(df["Price"].iloc[-1])

        if precio_inicial <= 0:
            continue

        factor_crecimiento = precio_final / precio_inicial
        valor_actual = capital_inicial * factor_crecimiento
        ganancia_no_realizada = valor_actual - capital_inicial
        rentabilidad_acumulada = ((valor_actual / capital_inicial) - 1) * 100 if capital_inicial > 0 else 0

        filas.append({
            "Fondo": fondo,
            "Asignación inicial": porcentaje,
            "Capital inicial asignado": capital_inicial,
            "Valor actual": valor_actual,
            "Ganancia / pérdida no realizada": ganancia_no_realizada,
            "Rentabilidad acumulada": rentabilidad_acumulada
        })

    df_estado = pd.DataFrame(filas)

    if df_estado.empty:
        return df_estado

    total_valor = df_estado["Valor actual"].sum()

    if total_valor > 0:
        df_estado["Participación actual"] = (df_estado["Valor actual"] / total_valor) * 100
    else:
        df_estado["Participación actual"] = 0.0

    total_row = pd.DataFrame([{
        "Fondo": "Total",
        "Asignación inicial": df_estado["Asignación inicial"].sum(),
        "Capital inicial asignado": df_estado["Capital inicial asignado"].sum(),
        "Valor actual": df_estado["Valor actual"].sum(),
        "Ganancia / pérdida no realizada": df_estado["Ganancia / pérdida no realizada"].sum(),
        "Rentabilidad acumulada": (
            ((df_estado["Valor actual"].sum() / df_estado["Capital inicial asignado"].sum()) - 1) * 100
            if df_estado["Capital inicial asignado"].sum() > 0 else 0
        ),
        "Participación actual": 100.0
    }])

    df_estado = pd.concat([df_estado, total_row], ignore_index=True)

    return df_estado