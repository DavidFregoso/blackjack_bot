import argparse
from simulation_core import BlackjackSystem


def print_summary(title: str, results: dict):
    """Imprime un resumen formateado en la consola."""
    print("\n" + "=" * 60)
    print(f"📊 RESUMEN FINAL: {title.upper()}")
    print("=" * 60)
    print(f"   Bankroll final: ${results['bankroll']:,.2f}")
    print(f"   P&L Total: ${results['session_pnl']:+,.2f} ({results['session_pnl_pct']:+.2%})")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Controlador de Terminal para el Simulador de Blackjack'
    )
    parser.add_argument('--bankroll', type=float, default=10000, help='Bankroll inicial')
    parser.add_argument(
        '--system',
        type=str,
        default='hilo',
        choices=['hilo', 'zen'],
        help='Sistema de conteo a usar'
    )
    parser.add_argument(
        '--stoploss',
        type=float,
        default=0.20,
        help='Porcentaje de Stop-Loss (ej. 0.2 para 20%)'
    )

    args = parser.parse_args()

    print(f"🚀 Iniciando simulación con sistema: {args.system.upper()}...")

    system = BlackjackSystem(
        initial_bankroll=args.bankroll,
        counting_system=args.system,
        stop_loss_pct=args.stoploss
    )

    results = system.run()
    print_summary(args.system, results)
