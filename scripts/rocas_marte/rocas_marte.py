"""
rocas_marte.py - Segmentación de rocas en fotos reales de Marte (estilo Fig. 13 de LisseMars: roca amarilla, fondo negro)
Grounding DINO (texto "rock" -> cajas) + SAM (cajas -> contorno) + modelo AI4Mars ONNX (quita rover y cielo/lejano).
Uso:  python rocas_marte.py CARPETA_FOTOS CARPETA_SALIDA
"""
import os, sys, glob, inspect
import numpy as np, cv2, torch, torchvision, onnxruntime as ort
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection, SamModel, SamProcessor

DEV = 'cuda' if torch.cuda.is_available() else 'cpu'
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT, THR, GRID, OV = 'rock. boulder. stone.', 0.18, 3, 0.25
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])

gproc = AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-base')
gdet = AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base').to(DEV).eval()
sproc = SamProcessor.from_pretrained('facebook/sam-vit-huge')
samm = SamModel.from_pretrained('facebook/sam-vit-huge').to(DEV).eval()
onx = ort.InferenceSession(os.path.join(HERE, 'Mars_AI4Mars_Unet_mbv2_int8.onnx'), providers=['CPUExecutionProvider'])
_pp = gproc.post_process_grounded_object_detection
_kw = 'threshold' if 'threshold' in inspect.signature(_pp).parameters else 'box_threshold'

def terreno(img):  # 0 suelo,1 bedrock,2 arena,3 roca grande,4 rover,5 lejano/cielo
    h0, w0 = img.shape[:2]; g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    x = np.repeat(cv2.resize(g, (384, 384), interpolation=cv2.INTER_AREA)[..., None], 3, -1)
    x = ((x / 255.0 - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    p = onx.run(None, {'x': x})[0].argmax(1)[0].astype(np.uint8)
    return cv2.resize(p, (w0, h0), interpolation=cv2.INTER_NEAREST)

def detect(pil):
    W0, H0 = pil.size
    inp = gproc(images=pil, text=PROMPT, return_tensors='pt').to(DEV)
    with torch.no_grad(): out = gdet(**inp)
    r = _pp(out, inp.input_ids, **{_kw: THR}, text_threshold=0.15, target_sizes=[(H0, W0)])[0]
    return [(b, s) for b, s in zip(r['boxes'].tolist(), r['scores'].tolist()) if (b[2] - b[0]) * (b[3] - b[1]) < 0.20 * H0 * W0]

def rocas(img):
    H0, W0 = img.shape[:2]; pil = Image.fromarray(img); allb = detect(pil)
    th, tw = int(H0 / GRID * (1 + OV)), int(W0 / GRID * (1 + OV))
    for gy in range(GRID):
        for gx in range(GRID):
            y0 = min(int(gy * H0 / GRID), H0 - th); x0 = min(int(gx * W0 / GRID), W0 - tw)
            for b, s in detect(Image.fromarray(img[y0:y0 + th, x0:x0 + tw])):
                allb.append(([b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0], s))
    m = np.zeros((H0, W0), bool)
    if allb:
        b = torch.tensor([x[0] for x in allb]); s = torch.tensor([x[1] for x in allb])
        boxes = b[torchvision.ops.nms(b, s, 0.5)].tolist()
        for i in range(0, len(boxes), 64):
            si = sproc(pil, input_boxes=[boxes[i:i + 64]], return_tensors='pt').to(DEV)
            with torch.no_grad(): so = samm(**si, multimask_output=False)
            ms = sproc.image_processor.post_process_masks(so.pred_masks.cpu(), si['original_sizes'].cpu(), si['reshaped_input_sizes'].cpu())[0]
            m |= ms[:, 0].any(0).numpy()
    m = m.astype(np.uint8); t = terreno(img); m[(t == 4) | (t == 5)] = 0
    return m

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]; os.makedirs(dst, exist_ok=True)
    YEL = np.array([[0, 0, 0], [255, 255, 0]], np.uint8)
    fs = sorted(f for e in ('png', 'jpg', 'jpeg', 'PNG', 'JPG') for f in glob.glob(os.path.join(src, '*.' + e)))
    for f in fs:
        img = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB); m = rocas(img)
        n = os.path.splitext(os.path.basename(f))[0]
        cv2.imwrite(os.path.join(dst, n + '_mascara.png'), cv2.cvtColor(YEL[m], cv2.COLOR_RGB2BGR))
        over = img.copy(); over[m == 1] = (0.5 * over[m == 1] + 0.5 * np.array([255, 255, 0])).astype(np.uint8)
        cv2.imwrite(os.path.join(dst, n + '_overlay.png'), cv2.cvtColor(over, cv2.COLOR_RGB2BGR))
        print(f'{n}: rocas {m.mean():.1%} de la imagen')
