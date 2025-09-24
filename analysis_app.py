"""Aplicación Streamlit para analizar sesiones registradas por el módulo 5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st


st.set_page_config(page_title="Blackjack Analysis Dashboard", page_icon="🔬", layout="wide")
alt.data_transformers.disable_max_rows()

st.title("🔬 Dashboard de Análisis y Replayer de Sesiones")

st.sidebar.header("Opciones de la sesión")
log_dir = Path("logs/")

if not log_dir.exists():
    st.warning("La carpeta 'logs/' no existe. Ejecuta una simulación primero.")
else:
    log_files = sorted([f.name for f in log_dir.glob("*.jsonl")], reverse=True)
    if not log_files:
        st.warning("No se encontraron archivos de log en la carpeta 'logs/'.")
    else:
        selected_log = st.selectbox("Selecciona una sesión para analizar:", log_files)

        @st.cache_data
        def load_data(file_path: Path) -> pd.DataFrame:
            with file_path.open("r", encoding="utf-8") as handler:
                records = [json.loads(line) for line in handler]
            dataframe = pd.DataFrame(records)
            if "timestamp" in dataframe.columns:
                dataframe["timestamp"] = pd.to_datetime(
                    dataframe["timestamp"], unit="s", errors="coerce"
                )
            return dataframe

        if selected_log:
            df_raw = load_data(log_dir / selected_log)

            if df_raw.empty:
                st.info("El archivo de log seleccionado no contiene eventos.")
            else:
                st.success(f"Se cargaron {len(df_raw)} eventos de la sesión '{selected_log}'.")

                if "data" in df_raw.columns:
                    normalized_data = pd.json_normalize(
                        df_raw["data"].apply(lambda value: value if isinstance(value, dict) else {})
                    )
                    normalized_data.index = df_raw.index
                    df_expanded = pd.concat([df_raw.drop(columns=["data"]), normalized_data], axis=1)
                else:
                    df_expanded = df_raw.copy()

                df_expanded = df_expanded.sort_values("timestamp") if "timestamp" in df_expanded.columns else df_expanded

                detected_initial = (
                    df_expanded["initial_bankroll"].dropna().iloc[0]
                    if "initial_bankroll" in df_expanded.columns and not df_expanded["initial_bankroll"].dropna().empty
                    else 0.0
                )

                initial_bankroll = st.sidebar.number_input(
                    "Bankroll inicial",
                    value=float(detected_initial),
                    step=100.0,
                    help="Valor usado para calcular la evolución del bankroll.",
                )

                if "event_type" not in df_expanded.columns:
                    st.error(
                        "El log cargado no contiene la columna 'event_type', por lo que no se pueden calcular métricas."
                    )
                else:
                    st.header("📊 Métricas de la Sesión")

                    round_end_events = df_expanded[df_expanded["event_type"] == "ROUND_END"].copy()
                    if not round_end_events.empty:
                        round_end_events = (
                            round_end_events.sort_values("timestamp")
                            if "timestamp" in round_end_events.columns
                            else round_end_events
                        )
                        round_end_events = round_end_events.reset_index(drop=True)
                        round_end_events["round_number"] = round_end_events.index + 1

                        def _calculate_pnl(row: Dict[str, Any]) -> float:
                            amount = pd.to_numeric(row.get("amount", 0), errors="coerce")
                            if pd.isna(amount):
                                amount = 0.0
                            result = row.get("result")
                            if result == "win":
                                return float(amount)
                            if result == "loss":
                                return -float(amount)
                            return 0.0

                        round_end_events["pnl"] = round_end_events.apply(_calculate_pnl, axis=1)
                        round_end_events["cum_pnl"] = round_end_events["pnl"].cumsum()
                        round_end_events["bankroll"] = initial_bankroll + round_end_events["cum_pnl"]

                        total_pnl = round_end_events["pnl"].sum()
                        final_bankroll = initial_bankroll + total_pnl

                        running_max = round_end_events["bankroll"].cummax()
                        drawdown_series = (running_max - round_end_events["bankroll"]) / running_max.replace(0, np.nan)
                        max_drawdown_pct = (
                            float(drawdown_series.max(skipna=True))
                            if not drawdown_series.empty
                            else 0.0
                        )
                        max_drawdown_amt = (
                            float((running_max - round_end_events["bankroll"]).max())
                            if not running_max.empty
                            else 0.0
                        )
                        if np.isnan(max_drawdown_pct):
                            max_drawdown_pct = 0.0
                        if np.isnan(max_drawdown_amt):
                            max_drawdown_amt = 0.0

                        wins = int((round_end_events["result"] == "win").sum())
                        losses = int((round_end_events["result"] == "loss").sum())
                        pushes = int((round_end_events["result"] == "push").sum())
                        total_rounds = len(round_end_events)
                        win_rate = wins / total_rounds if total_rounds > 0 else 0.0

                        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
                        kpi_col1.metric("P&L total", f"${total_pnl:,.2f}")
                        kpi_col2.metric("Bankroll final", f"${final_bankroll:,.2f}")
                        kpi_col3.metric("Max Drawdown", f"{max_drawdown_pct:.1%}", f"${max_drawdown_amt:,.2f}")
                        kpi_col4.metric("Win Rate", f"{win_rate:.1%}", f"{wins}-{losses}-{pushes}")

                        st.subheader("📈 Evolución del Bankroll")
                        bankroll_chart = (
                            alt.Chart(round_end_events)
                            .mark_line(point=True)
                            .encode(
                                x=
                                alt.X("timestamp:T", title="Tiempo")
                                if "timestamp" in round_end_events.columns
                                else alt.X("round_number:Q", title="Ronda"),
                                y=alt.Y("bankroll:Q", title="Bankroll ($)"),
                                tooltip=["round_id", "round_number", "bankroll", "result", "pnl"],
                            )
                            .interactive()
                        )
                        st.altair_chart(bankroll_chart, use_container_width=True)
                    else:
                        st.info(
                            "El log no contiene eventos de fin de ronda (ROUND_END), por lo que no hay métricas de bankroll disponibles."
                        )

                    st.subheader("📊 Distribución del True Count")
                    tc_columns = [col for col in df_expanded.columns if "tc" in col.lower()]
                    tc_values = pd.Series(dtype="float64")
                    for column in tc_columns:
                        series = pd.to_numeric(df_expanded[column], errors="coerce")
                        tc_values = pd.concat([tc_values, series.dropna()])

                    if not tc_values.empty:
                        tc_df = pd.DataFrame({"True Count": tc_values})
                        tc_chart = (
                            alt.Chart(tc_df)
                            .mark_bar()
                            .encode(
                                x=alt.X("True Count:Q", bin=alt.Bin(maxbins=25)),
                                y=alt.Y("count()", title="Frecuencia"),
                            )
                            .properties(height=300)
                        )
                        st.altair_chart(tc_chart, use_container_width=True)
                    else:
                        st.info("No se encontraron datos de True Count en el log seleccionado.")

                    st.header("🔄 Replayer de Rondas")
                    if "round_id" in df_raw.columns:
                        round_ids = pd.Index(df_raw["round_id"].dropna()).unique().tolist()
                    else:
                        round_ids = []

                    if round_ids:
                        selected_round_id = st.selectbox("Selecciona una ronda para ver en detalle:", round_ids)
                        if selected_round_id:
                            round_events = df_raw[df_raw["round_id"] == selected_round_id][
                                [col for col in ["timestamp", "event_type", "data"] if col in df_raw.columns]
                            ]
                            st.dataframe(round_events, use_container_width=True)
                    else:
                        st.info("El log no contiene identificadores de ronda para reproducir eventos.")
