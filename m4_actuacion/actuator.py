import time
import pyautogui
import random
from pathlib import Path
from .human_like_mouse import HumanLikeMouse


class Actuator:
    """Recibe órdenes del M3 y las ejecuta buscando imágenes en pantalla."""
    def __init__(self, image_path: str = "m4_actuacion/target_images/"):
        self.mouse = HumanLikeMouse()
        self.image_path = Path(image_path)
        self.action_map = {
            "HIT": "hit_button.png",
            "STAND": "stand_button.png",
            "DOUBLE": "double_button.png",
            "BET_20": "chip_20.png" # Mapeo para una apuesta de 20
        }

    def _find_image_on_screen(self, image_name: str, confidence=0.85) -> tuple | None:
        """Busca una imagen en la pantalla y devuelve las coordenadas de su centro."""
        try:
            image_file = self.image_path / image_name
            location = pyautogui.locateCenterOnScreen(str(image_file), confidence=confidence)
            return location
        except pyautogui.ImageNotFoundException:
            return None # Es normal no encontrar una imagen si no es el momento de la acción
        except Exception as e:
            print(f"⚠️ [M4 Actuator] Error inesperado buscando imagen: {e}")
            return None

    def execute_action(self, action_request: dict):
        action_type = action_request.get('type')
        payload = action_request.get('payload', {})
        start_time = time.time()

        try:
            image_name = None
            action_description = ""

            if action_type == 'PLAY':
                move = payload.get('move')
                image_name = self.action_map.get(move)
                action_description = f"Jugada: {move}"
            elif action_type == 'BET':
                # Lógica para apuestas más complejas podría ir aquí
                # Por ahora, se asume una apuesta simple con una ficha.
                units = payload.get('units')
                if 1 <= units < 2: # Asumimos que 1 unidad es la ficha de 20
                    image_name = self.action_map.get("BET_20")
                    action_description = f"Apuesta de {units} unidades (ficha de 20)"
                # Se pueden añadir más condiciones para otras fichas (ej. "BET_100")

            if not image_name:
                raise ValueError(f"Acción no mapeada o payload inválido: {action_request}")

            target_location = self._find_image_on_screen(image_name)
            if not target_location:
                raise Exception(f"No se pudo localizar el objetivo visual '{image_name}' en pantalla.")

            self.mouse.click(target_location[0], target_location[1])
            latency_ms = (time.time() - start_time) * 1000
            return self._create_confirmation(True, latency_ms, reason=action_description)

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return self._create_confirmation(False, latency_ms, error=str(e))

    def _create_confirmation(self, ok: bool, latency: float, reason: str = "", error=None):
        """Crea el evento ACTION_CONFIRMED estandarizado."""
        confirmation = {
            "t": time.time(), "event": "ACTION_CONFIRMED", "ok": ok,
            "latency_ms": latency, "reason": reason,
            "trace_id": f"trace-{random.randint(1000, 9999)}"
        }
        if error:
            confirmation["error"] = error
        return confirmation
