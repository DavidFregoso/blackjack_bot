# Biblioteca de Imágenes Objetivo para M4

Esta carpeta **no** incluye imágenes binarias en el repositorio. En su lugar, actúa como un recordatorio de los recortes necesarios que deben prepararse en cada entorno local.

## Cómo preparar las imágenes objetivo

1. Abre la mesa de "All Bets Blackjack" en Caliente.mx con la misma resolución que usarás con el bot.
2. Captura recortes nítidos en formato PNG de los botones y fichas listados abajo.
3. Guarda cada recorte en esta carpeta (`m4_actuacion/target_images/`).
4. Asegúrate de que los nombres de archivo coincidan exactamente, ya que el bot los buscará durante la fase de pre-vuelo.

### Lista de archivos requeridos

- [ ] `hit_button.png` (Botón verde `+` de **PEDIR**)
- [ ] `stand_button.png` (Botón rojo `Ø` de **PLANTARSE**)
- [ ] `double_button.png` (Botón amarillo `x2` de **DOBLAR**)
- [ ] `chip_25.png` (Ficha principal de apuesta mínima)
- [ ] `chip_100.png` (Ficha de apuesta alta para escalado rápido)
- [ ] `chip_500.png` (Ficha premium para apuestas escalonadas)
- [ ] `betting_area.png` (Círculo principal donde se depositan las fichas)

> ⚠️ **Importante:** estos archivos deben existir localmente antes de intentar iniciar el bot desde la interfaz web. El flujo de pre-vuelo marcará la calibración como incompleta si alguno falta.
