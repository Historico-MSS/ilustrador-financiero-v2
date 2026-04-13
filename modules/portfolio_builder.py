import pandas as pd


def construir_portafolio(fondos_disponibles: dict, asignaciones: dict) -> pd.DataFrame:
    """
    Construye una serie mensual combinada del portafolio a partir de los fondos seleccionados y sus pesos.
    Usa los retornos mensuales de cada fondo y crea un NAV base 100.
    """

    fondos_activos = {
        fondo: peso / 100.0
        for fondo, peso in asignaciones.items()
        if peso > 0
    }

    if not fondos_activos:
        raise ValueError("No hay fondos con asignación mayor a 0%.")

    if sum(fondos_activos.values()) <= 0:
        raise ValueError("La suma de asignaciones activas debe ser mayor a 0.")

    # Construir tabla base con Date y Return de cada fondo
    dataframes = []
    for fondo, peso in fondos_activos.items():
        if fondo not in fondos_disponibles:
            raise ValueError(f"El fondo '{fondo}' no está en fondos_disponibles.")

        df = fondos_disponibles[fondo]["df_monthly"].copy()
        df = df[["Date", "Return"]].rename(columns={"Return": fondo})
        dataframes.append(df)

    # Unir por fecha usando intersección de fechas disponibles
    df_merged = dataframes[0]
    for df in dataframes[1:]:
        df_merged = df_merged.merge(df, on="Date", how="inner")

    if df_merged.empty:
        raise ValueError("No hay fechas comunes entre los fondos seleccionados.")

    # Retorno combinado
    df_merged["Portfolio_Return"] = 0.0
    for fondo, peso in fondos_activos.items():
        df_merged["Portfolio_Return"] += df_merged[fondo] * peso

    # NAV base 100
    navs = []
    nav_actual = 100.0

    for i, row in df_merged.iterrows():
        if i == 0:
            navs.append(nav_actual)
        else:
            nav_actual = nav_actual * (1 + row["Portfolio_Return"])
            navs.append(nav_actual)

    df_merged["Portfolio_Price"] = navs

    df_portafolio = df_merged[["Date", "Portfolio_Price", "Portfolio_Return"]].copy()
    df_portafolio = df_portafolio.rename(columns={
        "Portfolio_Price": "Price",
        "Portfolio_Return": "Return"
    })

    return df_portafolio