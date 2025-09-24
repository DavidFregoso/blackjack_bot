import streamlit as st
import pandas as pd
import altair as alt
from simulation_core import BlackjackSystem


st.set_page_config(page_title="Blackjack Simulator", page_icon="🎰", layout="wide")

st.sidebar.header("⚙️ Parámetros de Simulación")
initial_bankroll = st.sidebar.number_input("Bankroll Inicial ($)", 100, 100000, 10000, 500)
stop_loss_pct = st.sidebar.slider("Stop-Loss (%)", 0.05, 1.0, 0.20, 0.05, "%.0f%%")

st.title("🎰 Simulador Comparativo de Estrategias de Blackjack")

if st.button("▶️ Ejecutar Comparación (Hi-Lo vs. Zen)"):
    hilo_system = BlackjackSystem(initial_bankroll, "hilo", stop_loss_pct)
    hilo_results = hilo_system.run()

    zen_system = BlackjackSystem(initial_bankroll, "zen", stop_loss_pct)
    zen_results = zen_system.run()

    df_hilo = pd.DataFrame(
        {
            'Ronda': range(len(hilo_results['bankroll_history'])),
            'Bankroll': hilo_results['bankroll_history'],
            'Estrategia': 'Hi-Lo'
        }
    )
    df_zen = pd.DataFrame(
        {
            'Ronda': range(len(zen_results['bankroll_history'])),
            'Bankroll': zen_results['bankroll_history'],
            'Estrategia': 'Zen'
        }
    )
    df_combined = pd.concat([df_hilo, df_zen])

    st.subheader("📈 Evolución del Bankroll")
    chart = alt.Chart(df_combined).mark_line().encode(
        x='Ronda',
        y=alt.Y('Bankroll', title='Bankroll ($)'),
        color='Estrategia',
        tooltip=['Ronda', 'Bankroll', 'Estrategia']
    ).interactive()
    st.altair_chart(chart, use_container_width=True)

    st.subheader("📊 Resumen de Rendimiento")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Estrategia Hi-Lo")
        st.metric("P&L Final", f"${hilo_results['session_pnl']:,.2f}", f"{hilo_results['session_pnl_pct']:.2%}")
    with col2:
        st.markdown("#### Estrategia Zen")
        st.metric("P&L Final", f"${zen_results['session_pnl']:,.2f}", f"{zen_results['session_pnl_pct']:.2%}")
