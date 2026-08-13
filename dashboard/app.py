"""
dashboard/app.py — Dashboard interactivo de LatamPulse.

Lee de data/processed/ (mismo dato que el notebook, mismo origen que
Postgres) — no depende de que Docker/Postgres estén corriendo, lo que
lo hace apto para deploy en Streamlit Community Cloud sin config extra.

Corré con: streamlit run dashboard/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="LatamPulse — Costo de vida en LATAM",
    page_icon="🌎",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

COUNTRY_NAMES = {"AR": "Argentina", "BR": "Brasil", "UY": "Uruguay", "CO": "Colombia"}
COUNTRY_COLORS = {"AR": "#75AADB", "BR": "#009C3B", "UY": "#0038A8", "CO": "#FCD116"}


@st.cache_data
def load_data():
    prices = pd.read_csv(PROCESSED_DIR / "prices.csv")
    ppp_factors = pd.read_csv(PROCESSED_DIR / "ppp_factors.csv")
    inflation = pd.read_csv(PROCESSED_DIR / "inflation_indices.csv")
    inflation["period"] = pd.to_datetime(inflation["period"])
    return prices, ppp_factors, inflation


def compute_monthly_pct(country_code: str, config: dict, df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza las 4 fuentes de inflación a variación mensual (%) comparable.
    Ver AGENTS.md para el detalle de por qué esto no es trivial: 2 de las
    4 fuentes dan nivel de índice (no variación), y hay que detectar
    huecos de meses faltantes para no calcular una "variación mensual"
    que en realidad es de 2+ meses.
    """
    ind_name, ind_type = config["name"], config["type"]
    sub = df[(df["country_code"] == country_code) & (df["indicator"] == ind_name)].copy()
    sub = sub.sort_values("period").reset_index(drop=True)

    if ind_type == "direct_pct":
        return sub[["country_code", "period", "value"]].dropna()

    sub["value"] = sub["value"].pct_change() * 100
    period_m = sub["period"].dt.to_period("M").astype("int64")
    gap = period_m.diff()
    sub.loc[gap != 1, "value"] = pd.NA
    return sub[["country_code", "period", "value"]].dropna()


INDICATOR_MAP = {
    "BR": {"name": "ipca_variacao_mensal", "type": "direct_pct"},
    "AR": {"name": "indec_0_variacion_mensual", "type": "direct_pct"},
    "CO": {"name": "ipc_indice", "type": "level"},
    "UY": {"name": "ipc_indice", "type": "level"},
}


try:
    prices, ppp_factors, inflation = load_data()
except FileNotFoundError as e:
    st.error(
        f"No encontré los archivos de datos ({e}). "
        f"Corré `python -m src.run_pipeline` primero para generar "
        f"data/processed/."
    )
    st.stop()

st.title("🌎 LatamPulse")
st.markdown(
    "**Costo de vida y poder adquisitivo en Argentina, Brasil, Uruguay y Colombia.** "
    "Comparación en USD nominal (tipo de cambio del día) vs. USD PPP "
    "(ajustado por poder de compra real) — la brecha entre ambos es la historia."
)

col_a, col_b = st.columns(2)
with col_a:
    st.info(
        "**💵 USD nominal**\n\n"
        "El precio convertido al tipo de cambio oficial del día — "
        "lo que pagaría alguien con dólares reales, hoy."
    )
with col_b:
    st.info(
        "**⚖️ USD PPP** (Paridad de Poder de Compra)\n\n"
        "El precio ajustado por lo que ese dinero realmente rinde "
        "*dentro* de cada país. Corrige el hecho de que un dólar no "
        "compra lo mismo en Buenos Aires que en Montevideo — es la "
        "métrica que usan organismos como el Banco Mundial para "
        "comparar economías de forma justa."
    )

st.header("📊 Resumen ejecutivo")

items_por_pais_resumen = prices.groupby("item_name")["country"].nunique()
items_comparables_resumen = items_por_pais_resumen[items_por_pais_resumen >= 2].index.tolist()
canasta_df = prices[prices["item_name"].isin(items_comparables_resumen)]

if canasta_df.empty:
    st.info("Todavía no hay suficientes ítems comparables entre países para un resumen.")
else:
    canasta_por_pais = canasta_df.groupby("country")["price_usd_ppp"].mean().sort_values(ascending=False)
    n_items = len(items_comparables_resumen)

    pais_mas_caro = canasta_por_pais.index[0]
    pais_mas_barato = canasta_por_pais.index[-1]
    palabra_items = "ítem" if n_items == 1 else "ítems"

    st.markdown(
        f"**{COUNTRY_NAMES[pais_mas_caro]}** tiene el costo de vida más alto en términos de "
        f"poder adquisitivo real (USD PPP), con un promedio de **USD {canasta_por_pais.iloc[0]:,.0f}** "
        f"en una canasta de {n_items} {palabra_items} comparables entre los 4 países. "
        f"**{COUNTRY_NAMES[pais_mas_barato]}** es el más económico, con un promedio de "
        f"**USD {canasta_por_pais.iloc[-1]:,.0f}**."
    )

    cols = st.columns(len(canasta_por_pais))
    for col, (country_code, valor) in zip(cols, canasta_por_pais.items()):
        with col:
            st.metric(
                COUNTRY_NAMES[country_code],
                f"USD {valor:,.0f}",
                help=f"Promedio USD PPP sobre {n_items} ítems comparables",
            )

    st.caption(
        f"Metodología: promedio simple de USD PPP sobre los {n_items} ítems presentes en 2 o más "
        f"países (de un total de {items_por_pais_resumen.shape[0]} ítems investigados). "
        f"Los ítems que todavía no están confirmados en todos los países quedan fuera de este "
        f"promedio hasta completarse — ver pestaña 'Precios comparables' para el detalle."
    )

st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "💵 Precios comparables", "⚖️ Nominal vs PPP", "📈 Inflación", "🌍 Poder adquisitivo"
])

with tab1:
    st.subheader("Precio en USD PPP por ítem y país")

    items_por_pais = prices.groupby("item_name")["country"].nunique()
    items_comparables = items_por_pais[items_por_pais >= 2].index.tolist()

    if not items_comparables:
        st.warning("No hay ítems presentes en 2 o más países todavía.")
    else:
        comparables_base = prices[prices["item_name"].isin(items_comparables)].copy()

        categorias_disponibles = sorted(comparables_base["category"].dropna().unique().tolist())
        categoria_labels = {
            "vivienda": "🏠 Vivienda",
            "transporte": "🚌 Transporte",
            "entretenimiento": "🎭 Entretenimiento",
            "salud": "🏥 Salud",
        }

        categoria_elegida = st.selectbox(
            "Categoría",
            options=categorias_disponibles,
            format_func=lambda c: categoria_labels.get(c, c.capitalize()),
        )

        items_de_la_categoria = sorted(
            comparables_base[comparables_base["category"] == categoria_elegida]["item_name"].unique().tolist()
        )

        seleccion = st.multiselect(
            "Filtrar ítems dentro de la categoría (vacío = todos)",
            options=items_de_la_categoria,
            default=items_de_la_categoria,
        )
        seleccion = seleccion or items_de_la_categoria

        comparables_df = comparables_base[comparables_base["item_name"].isin(seleccion)].copy()
        comparables_df["País"] = comparables_df["country"].map(COUNTRY_NAMES)

        fig = px.bar(
            comparables_df,
            x="item_name",
            y="price_usd_ppp",
            color="País",
            barmode="group",
            color_discrete_map={COUNTRY_NAMES[k]: v for k, v in COUNTRY_COLORS.items()},
            labels={"item_name": "", "price_usd_ppp": "USD (PPP)"},
        )
        fig.update_layout(xaxis_tickangle=-30, height=500)
        st.plotly_chart(fig, width='stretch')

        st.caption(
            "**Nota metodológica:** el factor PPP usado acá es un ajuste a nivel de "
            "toda la economía (Banco Mundial), no específico por producto. Esto significa "
            "que un ítem puntual —sobre todo uno de bajo costo, como una entrada de cine o "
            "un café— puede mostrar un valor en USD PPP que parece desproporcionado incluso "
            "cuando el cálculo es correcto: refleja que ese ítem puntual es relativamente más "
            "caro en ese país respecto a su propia canasta de consumo promedio, no un error "
            "de datos. Para una lectura más estable, el Resumen Ejecutivo usa el promedio de "
            "toda la canasta comparable, no un ítem aislado."
        )

    with st.expander("Ver tabla completa"):
        tabla_detalle = prices[
            ["country", "category", "item_name", "price_local", "currency", "price_usd_ppp", "source"]
        ].sort_values(["item_name", "country"]).copy()
        tabla_detalle.columns = [
            "País", "Categoría", "Ítem", "Precio local", "Moneda", "USD (PPP)", "Fuente"
        ]
        tabla_detalle["País"] = tabla_detalle["País"].map(COUNTRY_NAMES)

        tabla_detalle["Fuente"] = tabla_detalle["Fuente"].replace(
            {"Fuente sin confirmar — pedir a Juani": "En proceso de verificación"}
        )

        st.dataframe(tabla_detalle, width='stretch')

with tab2:
    st.subheader("USD nominal vs USD PPP")
    st.caption(
        "⚠️ Gap conocido: solo hay tipo de cambio nominal extraído para Argentina. "
        "Para Brasil/Uruguay/Colombia, esta comparación no está disponible todavía."
    )

    ar_con_nominal = prices[(prices["country"] == "AR") & (prices["price_usd_nominal"].notna())].copy()

    if ar_con_nominal.empty:
        st.info("No hay filas de Argentina con USD nominal calculado todavía.")
    else:
        ar_con_nominal = ar_con_nominal.sort_values("price_usd_ppp", ascending=False)

        fig = go.Figure()
        fig.add_bar(name="USD nominal", x=ar_con_nominal["item_name"], y=ar_con_nominal["price_usd_nominal"])
        fig.add_bar(name="USD PPP", x=ar_con_nominal["item_name"], y=ar_con_nominal["price_usd_ppp"])
        fig.update_layout(barmode="group", xaxis_tickangle=-30, height=550, yaxis_title="USD")
        st.plotly_chart(fig, width='stretch')

        gap_promedio = (ar_con_nominal["price_usd_ppp"] / ar_con_nominal["price_usd_nominal"]).mean()
        st.metric(
            "Brecha promedio (PPP / nominal)",
            f"{gap_promedio:.1f}x",
            help="Cuántas veces más 'caro' se ve un ítem en PPP respecto al nominal — refleja el dólar oficial subvaluado.",
        )

with tab3:
    st.subheader("Inflación mensual comparada (%)")
    st.caption(
        "Normalizado a la misma unidad entre las 4 fuentes (2 dan el nivel del índice, "
        "no la variación — se calcula acá). Los huecos de meses faltantes se detectan "
        "y se excluyen en vez de mostrarse como variación mensual real."
    )

    meses_a_mostrar = st.slider("Meses a mostrar", min_value=6, max_value=48, value=24, step=6)

    series = [compute_monthly_pct(c, cfg, inflation) for c, cfg in INDICATOR_MAP.items()]
    unified_inflation = pd.concat(series, ignore_index=True)
    unified_inflation["País"] = unified_inflation["country_code"].map(COUNTRY_NAMES)

    fig = go.Figure()
    for country_code in INDICATOR_MAP:
        sub = unified_inflation[unified_inflation["country_code"] == country_code].sort_values("period")
        sub = sub.tail(meses_a_mostrar)
        fig.add_scatter(
            x=sub["period"], y=sub["value"], mode="lines+markers",
            name=COUNTRY_NAMES[country_code],
            line=dict(color=COUNTRY_COLORS[country_code]),
        )
    fig.add_hline(y=0, line_color="gray", line_width=0.8)
    fig.update_layout(height=550, yaxis_title="Variación mensual (%)", xaxis_title="")
    st.plotly_chart(fig, width='stretch')

with tab4:
    st.subheader("GDP per cápita, PPP (World Bank)")

    ppp_sorted = ppp_factors.sort_values("gdp_per_capita_ppp_current", ascending=False).copy()
    ppp_sorted["País"] = ppp_sorted["country_code"].map(COUNTRY_NAMES)

    fig = px.bar(
        ppp_sorted, x="País", y="gdp_per_capita_ppp_current",
        text=ppp_sorted["year"].astype(int).astype(str),
        color="country_code",
        color_discrete_map=COUNTRY_COLORS,
        labels={"gdp_per_capita_ppp_current": "USD (PPP)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=500, showlegend=False)
    st.plotly_chart(fig, width='stretch')

st.divider()
st.caption(
    "Fuentes: dolarapi.com, World Bank, IBGE/SIDRA, DANE, INE Uruguay (vía DGI), INDEC, "
    "y research manual verificado con fuente y fecha por precio. "
    "Metodología completa en AGENTS.md del repositorio."
)
