"""
Script para quitar el fondo blanco de los gifs de ejercicios y guardarlos
como .webp con transparencia real (fondo suave, sin bordes dentados),
invirtiendo solo los tonos grises/negros del contorno (el rojo de la zona
muscular se mantiene igual).

CMO USARLO:
1. Rellena las dos variables de abajo (CARPETA_ENTRADA y CARPETA_SALIDA)
   con las rutas reales de tu proyecto.
2. Instala las libreras necesarias (una sola vez):
       pip install pillow numpy
3. Ejecuta:
       python3 procesar_gifs.py
"""

import os
import numpy as np
from PIL import Image

# ============================================================
# RELLENA ESTAS DOS RUTAS ANTES DE EJECUTAR
# ============================================================
CARPETA_ENTRADA = "/Users/maxzawada/Proyectos/MarmotFitnessApp/media/exercises"
CARPETA_SALIDA = "/Users/maxzawada/Proyectos/MarmotFitnessApp/media/exercises/webp"
# ============================================================


def procesar_gif(ruta_entrada, ruta_salida):
    im = Image.open(ruta_entrada)
    n_frames = getattr(im, "n_frames", 1)
    frames_out = []
    durations = []

    for i in range(n_frames):
        im.seek(i)
        frame = im.convert("RGB")
        durations.append(im.info.get("duration", 100))
        arr = np.array(frame).astype(np.float32)
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        minc = np.minimum(np.minimum(r, g), b)
        alpha = 255.0 - minc
        alpha_frac = np.clip(alpha / 255.0, 1e-4, 1.0)

        fg_r = np.clip((r - (1 - alpha_frac) * 255.0) / alpha_frac, 0, 255)
        fg_g = np.clip((g - (1 - alpha_frac) * 255.0) / alpha_frac, 0, 255)
        fg_b = np.clip((b - (1 - alpha_frac) * 255.0) / alpha_frac, 0, 255)

        maxc = np.maximum(np.maximum(fg_r, fg_g), fg_b)
        minc2 = np.minimum(np.minimum(fg_r, fg_g), fg_b)
        is_gray = (maxc - minc2) < 18  # umbral para distinguir gris/negro del rojo

        out_r = np.where(is_gray, 255 - fg_r, fg_r)
        out_g = np.where(is_gray, 255 - fg_g, fg_g)
        out_b = np.where(is_gray, 255 - fg_b, fg_b)

        out = np.stack([out_r, out_g, out_b, alpha], axis=-1).astype(np.uint8)
        frames_out.append(Image.fromarray(out, "RGBA"))

    frames_out[0].save(
        ruta_salida, save_all=True, append_images=frames_out[1:],
        duration=durations, loop=0, format="WEBP"
    )


def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    archivos = [f for f in os.listdir(CARPETA_ENTRADA) if f.lower().endswith(".gif")]
    total = len(archivos)
    print(f"Encontrados {total} gifs en {CARPETA_ENTRADA}")

    for i, nombre in enumerate(archivos, 1):
        entrada = os.path.join(CARPETA_ENTRADA, nombre)
        salida = os.path.join(CARPETA_SALIDA, nombre.rsplit(".", 1)[0] + ".webp")
        try:
            procesar_gif(entrada, salida)
        except Exception as e:
            print(f"  ERROR en {nombre}: {e}")
        if i % 50 == 0 or i == total:
            print(f"Procesados {i}/{total}")

    print(f"Listo. Resultados en: {CARPETA_SALIDA}")


if __name__ == "__main__":
    main()
