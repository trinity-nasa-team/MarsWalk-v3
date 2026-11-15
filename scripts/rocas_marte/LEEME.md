# Rocas en Marte (estilo Fig. 13 LisseMars)

1. Python 3.10+ y (recomendado) GPU NVIDIA. En CPU funciona pero tarda ~1-2 min por foto.
2. pip install -r requirements.txt
3. python rocas_marte.py carpeta_con_fotos carpeta_salida
   - Genera por foto: *_mascara.png (roca amarilla #FFFF00 sobre negro) y *_overlay.png.
   - La primera vez descarga de Hugging Face Grounding DINO base y SAM ViT-H (~3.5 GB).

Componentes:
- Grounding DINO (IDEA-Research/grounding-dino-base) + SAM (facebook/sam-vit-huge): modelos públicos; revisar sus licencias antes de uso comercial.
- Mars_AI4Mars_Unet_mbv2_int8.onnx: modelo propio entrenado con AI4Mars (NASA/JPL, CC0); quita rover y cielo/lejano.
- Ajustes en rocas_marte.py: THR (sensibilidad; más bajo = más rocas y más falsos positivos), GRID (mosaico; más alto = piedras más chicas).

Limitación: es para análisis y etiquetado en computadora con GPU, no para un dispositivo embebido. Para el dispositivo,
usar estas máscaras como etiquetas y entrenar el modelo ligero (U-Net MobileNetV2 del notebook).
