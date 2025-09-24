import pyautogui
import random
import numpy as np
import time


class HumanLikeMouse:
    """Genera movimientos de mouse realistas usando curvas de Bézier."""

    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.01

    def _generate_bezier_curve(self, start_point, end_point, control_point_offset=100):
        """Genera los puntos de una curva de Bézier cuadrática para un movimiento natural."""
        mid_point = (start_point + end_point) / 2
        # El punto de control se desvía aleatoriamente para que cada curva sea única
        control_point = mid_point + np.random.uniform(-control_point_offset, control_point_offset, size=2)

        points = []
        num_points = max(10, int(np.linalg.norm(end_point - start_point)) // 15)

        for i in range(num_points + 1):
            t = i / num_points
            point = (1 - t)**2 * start_point + 2 * (1 - t) * t * control_point + t**2 * end_point
            points.append(tuple(point.astype(int)))
        return points

    def move_to(self, target_x, target_y, duration_factor=0.3):
        """Mueve el mouse a un punto de forma humana."""
        start_pos = pyautogui.position()
        path = self._generate_bezier_curve(np.array(start_pos), np.array([target_x, target_y]))

        duration = random.uniform(duration_factor * 0.8, duration_factor * 1.2)
        for x, y in path:
            pyautogui.moveTo(x, y)
            time.sleep(duration / len(path))

    def click(self, target_x, target_y):
        """Mueve y hace clic de forma humana, añadiendo imprecisiones."""
        self.move_to(target_x, target_y)

        # Simula el "jitter" (ligero temblor) antes del clic
        pyautogui.moveRel(random.randint(-2, 2), random.randint(-2, 2))

        # Simula latencia humana
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.click()
        time.sleep(random.uniform(0.07, 0.18))
