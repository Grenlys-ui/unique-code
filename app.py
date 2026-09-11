import csv
import ctypes
import gc
import json
import os
import platform
import random
import string
import shutil
import tempfile
import zipfile
import sqlite3
from flask import Flask, render_template_string, request, send_file
from PIL import Image, ImageDraw, ImageFont
import qrcode

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# OSレベルでメモリを強制解放する関数
def trim_memory():
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

DB_PATH = "uuid_only_codes.db"
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS uuid_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

def generate_uuid():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    while True:
        code = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        c.execute("SELECT id FROM uuid_codes WHERE uuid = ?", (code,))
        if not c.fetchone():
            c.execute("INSERT INTO uuid_codes (uuid) VALUES (?)", (code,))
            conn.commit()
            conn.close()
            return code

def get_font(font_size):
    system = platform.system()
    font_paths = []
    if system == "Windows":
        font_paths = ["C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\msgothic.ttc"]
    elif system == "Darwin":
        font_paths = ["/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]
    else:
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=font_size)
            except Exception:
                pass
    return ImageFont.load_default()

def create_qr_image(uuid_code, fill_color="black", back_color="white"):
    qr = qrcode.QRCode(version=1, box_size=6, border=2) # box_sizeを小さくして軽量化
    qr.add_data(uuid_code)
    qr.make(fit=True)

    if back_color == "transparent":
        img = qr.make_image(fill_color=fill_color, back_color="white").convert("RGBA")
        datas = img.getdata()
        new_data = []
        for item in datas:
            if item[0] > 200 and item[1] > 200 and item[2] > 200:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
        return img
    else:
        return qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")

def draw_outer_text_directional(img, text_str, outer_params):
    width, height = img.size
    txt_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))

    def create_text_image(text, size, color, angle):
        font = get_font(size)
        dummy_img = Image.new("RGBA", (1, 1))
        d_dummy = ImageDraw.Draw(dummy_img)
        bbox = d_dummy.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0] + 20
        th = bbox[3] - bbox[1] + 20

        t_img = Image.new("RGBA", (max(1, tw), max(1, th)), (255, 255, 255, 0))
        d = ImageDraw.Draw(t_img)
        d.text((tw//2, th//2), text, fill=color, font=font, anchor="mm")

        if angle != 0:
            t_img = t_img.rotate(angle, expand=True, resample=Image.BICUBIC)
        return t_img

    top_p = outer_params.get("top", {})
    if top_p:
        t_img = create_text_image(text_str, int(top_p.get("size", 14)), top_p.get("color", "#000000"), int(top_p.get("angle", 0)))
        tw, th = t_img.size
        off_x = int(top_p.get("offsetX", 0))
        off_y = int(top_p.get("offsetY", 15))
        for i in range(4):
            x = int(width * (i + 0.5) / 4) - tw // 2 + off_x
            txt_layer.paste(t_img, (x, off_y), t_img)

    btm_p = outer_params.get("bottom", {})
    if btm_p:
        t_img = create_text_image(text_str, int(btm_p.get("size", 14)), btm_p.get("color", "#000000"), int(btm_p.get("angle", 0)))
        tw, th = t_img.size
        off_x = int(btm_p.get("offsetX", 0))
        off_y = int(btm_p.get("offsetY", 15))
        for i in range(4):
            x = int(width * (i + 0.5) / 4) - tw // 2 + off_x
            txt_layer.paste(t_img, (x, height - th - off_y), t_img)

    lft_p = outer_params.get("left", {})
    if lft_p:
        t_img = create_text_image(text_str, int(lft_p.get("size", 14)), lft_p.get("color", "#000000"), int(lft_p.get("angle", 0)))
        tw, th = t_img.size
        off_x = int(lft_p.get("offsetX", 15))
        off_y = int(lft_p.get("offsetY", 0))
        for i in range(4):
            y = int(height * (i + 0.5) / 4) - th // 2 + off_y
            txt_layer.paste(t_img, (off_x, y), t_img)

    rgt_p = outer_params.get("right", {})
    if rgt_p:
        t_img = create_text_image(text_str, int(rgt_p.get("size", 14)), rgt_p.get("color", "#000000"), int(rgt_p.get("angle", 0)))
        tw, th = t_img.size
        off_x = int(rgt_p.get("offsetX", 15))
        off_y = int(rgt_p.get("offsetY", 0))
        for i in range(4):
            y = int(height * (i + 0.5) / 4) - th // 2 + off_y
            txt_layer.paste(t_img, (width - tw - off_x, y), t_img)

    img.alpha_composite(txt_layer)

HTML_TEMPLATE = """
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <title>QR Kod Generatori</title>
  <style>
    body { font-family: sans-serif; margin: 20px; display: flex; gap: 20px; align-items: flex-start; }
    .controls { width: 460px; }
    .section-box { border: 1px solid #ccc; padding: 12px; margin-bottom: 15px; border-radius: 5px; background: #fdfdfd; }
    .dir-box { border: 1px solid #eee; padding: 8px; margin-top: 6px; border-radius: 4px; background: #fff; }
    .qr-config { border: 1px dashed #888; padding: 10px; margin-top: 8px; border-radius: 5px; background: #fafafa; }
    
    .preview-container {
      position: sticky;
      top: 20px;
      flex: 1;
    }
    #preview-canvas { border: 1px solid #000; max-width: 100%; height: auto; background: #fff; }
  </style>
</head>
<body>

<div class="controls">
  <h2>QR Kod Sozlamalari</h2>
  <form id="qr-form" method="post" enctype="multipart/form-data">
    <label>Yaratiladigan soni (ZIP): <input type="number" name="qty" value="1" min="1" max="10000" required></label><br><br>
    <label>Ramka tasviri (Frame): <input type="file" id="frame-input" name="frame" accept="image/*"></label><br><br>

    <div class="section-box">
      <h3>Tashqi Atrof Matn Sozlamalari (Outer Text)</h3>
      
      <div class="dir-box">
        <b>Yuqori (Tepada):</b><br>
        Rangi: <input type="color" id="out-top-color" value="#000000" onchange="renderPreview()">
        O'lchami (px): <input type="number" id="out-top-size" value="14" min="1" onchange="renderPreview()"><br>
        Joylashuvi X: <input type="number" id="out-top-offx" value="0" style="width:50px" onchange="renderPreview()">
        Joylashuvi Y: <input type="number" id="out-top-offy" value="15" style="width:50px" onchange="renderPreview()">
        Yo'nalishi: 
        <select id="out-top-angle" onchange="renderPreview()">
          <option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option>
        </select>
      </div>

      <div class="dir-box">
        <b>Pastki (Pastda):</b><br>
        Rangi: <input type="color" id="out-bottom-color" value="#000000" onchange="renderPreview()">
        O'lchami (px): <input type="number" id="out-bottom-size" value="14" min="1" onchange="renderPreview()"><br>
        Joylashuvi X: <input type="number" id="out-bottom-offx" value="0" style="width:50px" onchange="renderPreview()">
        Joylashuvi Y: <input type="number" id="out-bottom-offy" value="15" style="width:50px" onchange="renderPreview()">
        Yo'nalishi: 
        <select id="out-bottom-angle" onchange="renderPreview()">
          <option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option>
        </select>
      </div>

      <div class="dir-box">
        <b>Chap tomon:</b><br>
        Rangi: <input type="color" id="out-left-color" value="#000000" onchange="renderPreview()">
        O'lchami (px): <input type="number" id="out-left-size" value="14" min="1" onchange="renderPreview()"><br>
        Joylashuvi X: <input type="number" id="out-left-offx" value="15" style="width:50px" onchange="renderPreview()">
        Joylashuvi Y: <input type="number" id="out-left-offy" value="0" style="width:50px" onchange="renderPreview()">
        Yo'nalishi: 
        <select id="out-left-angle" onchange="renderPreview()">
          <option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option>
        </select>
      </div>

      <div class="dir-box">
        <b>O'ng tomon:</b><br>
        Rangi: <input type="color" id="out-right-color" value="#000000" onchange="renderPreview()">
        O'lchami (px): <input type="number" id="out-right-size" value="14" min="1" onchange="renderPreview()"><br>
        Joylashuvi X: <input type="number" id="out-right-offx" value="15" style="width:50px" onchange="renderPreview()">
        Joylashuvi Y: <input type="number" id="out-right-offy" value="0" style="width:50px" onchange="renderPreview()">
        Yo'nalishi: 
        <select id="out-right-angle" onchange="renderPreview()">
          <option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option>
        </select>
      </div>
    </div>

    <div class="section-box">
      <label>Bitta ramkadagi QR kodlar soni: 
        <input type="number" id="qr-count" name="qr_count" value="1" min="1" max="10">
      </label>
      <div id="qr-configs-container"></div>
    </div>

    <input type="hidden" id="qr-params-json" name="qr_params">
    <input type="hidden" id="outer-params-json" name="outer_params">

    <input type="submit" value="ZIP Yuklab Olish" style="margin-top: 15px; padding: 12px 24px; cursor: pointer; font-weight: bold;">
  </form>
</div>

<div class="preview-container">
  <h2>Oldindan Ko'rish (Preview)</h2>
  <canvas id="preview-canvas" width="600" height="600"></canvas>
</div>

<script>
const qrCountInput = document.getElementById('qr-count');
const container = document.getElementById('qr-configs-container');
const canvas = document.getElementById('preview-canvas');
const ctx = canvas.getContext('2d');
const frameInput = document.getElementById('frame-input');
let loadedFrameImg = null;

let qrConfigs = [
  { 
    x: 200, y: 200, size: 150, 
    fillColor: '#000000', backColor: '#ffffff', isTransparent: false,
    textSize: 16, textColor: '#000000', textPosition: 'bottom', textMargin: 10
  }
];

frameInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) {
    const reader = new FileReader();
    reader.onload = (event) => {
      loadedFrameImg = new Image();
      loadedFrameImg.onload = () => {
        canvas.width = loadedFrameImg.width;
        canvas.height = loadedFrameImg.height;
        renderPreview();
      };
      loadedFrameImg.src = event.target.result;
    };
    reader.readAsDataURL(file);
  }
});

qrCountInput.addEventListener('input', () => {
  const count = parseInt(qrCountInput.value) || 1;
  while (qrConfigs.length < count) {
    qrConfigs.push({ 
      x: 100 + qrConfigs.length * 30, 
      y: 100 + qrConfigs.length * 30, 
      size: 150, 
      fillColor: '#000000', 
      backColor: '#ffffff',
      isTransparent: false,
      textSize: 16,
      textColor: '#000000',
      textPosition: 'bottom',
      textMargin: 10
    });
  }
  qrConfigs = qrConfigs.slice(0, count);
  buildUI();
  renderPreview();
});

function buildUI() {
  container.innerHTML = '';
  qrConfigs.forEach((config, index) => {
    const div = document.createElement('div');
    div.className = 'qr-config';
    div.innerHTML = `
      <h4>QR Kod #${index + 1}</h4>
      <label>X joylashuvi: <input type="number" value="${config.x}" onchange="updateConfig(${index}, 'x', this.value)"></label><br>
      <label>Y joylashuvi: <input type="number" value="${config.y}" onchange="updateConfig(${index}, 'y', this.value)"></label><br>
      <label>O'lchami (px): <input type="number" value="${config.size}" min="10" onchange="updateConfig(${index}, 'size', this.value)"></label><br>
      <label>QR rangi (Old): <input type="color" value="${config.fillColor}" onchange="updateConfig(${index}, 'fillColor', this.value)"></label><br>
      <label>Fon rangi (Orqa): 
        <input type="color" id="bg-color-${index}" value="${config.backColor}" ${config.isTransparent ? 'disabled' : ''} onchange="updateConfig(${index}, 'backColor', this.value)">
        <label><input type="checkbox" ${config.isTransparent ? 'checked' : ''} onchange="toggleTransparent(${index}, this.checked)"> Shaffof (Rangsiz)</label>
      </label><br>
      <hr style="border:0; border-top:1px dashed #ccc;">
      <b>QR UUID matni sozlamalari:</b><br>
      <label>Matn joylashuvi: 
        <select onchange="updateConfig(${index}, 'textPosition', this.value)">
          <option value="bottom" ${config.textPosition === 'bottom' ? 'selected' : ''}>Pastda (下)</option>
          <option value="top" ${config.textPosition === 'top' ? 'selected' : ''}>Tepada (上)</option>
          <option value="left" ${config.textPosition === 'left' ? 'selected' : ''}>Chapda (左)</option>
          <option value="right" ${config.textPosition === 'right' ? 'selected' : ''}>O'ngda (右)</option>
        </select>
      </label><br>
      <label>Matn masofasi (px): <input type="number" value="${config.textMargin}" onchange="updateConfig(${index}, 'textMargin', this.value)"></label><br>
      <label>Matn o'lchami (px): <input type="number" value="${config.textSize}" min="1" onchange="updateConfig(${index}, 'textSize', this.value)"></label><br>
      <label>Matn rangi: <input type="color" value="${config.textColor}" onchange="updateConfig(${index}, 'textColor', this.value)"></label>
    `;
    container.appendChild(div);
  });
}

function toggleTransparent(index, isChecked) {
  qrConfigs[index].isTransparent = isChecked;
  document.getElementById(`bg-color-${index}`).disabled = isChecked;
  renderPreview();
}

function updateConfig(index, key, value) {
  if (['fillColor', 'backColor', 'textColor', 'textPosition'].includes(key)) {
    qrConfigs[index][key] = value;
  } else {
    qrConfigs[index][key] = parseInt(value) || 0;
  }
  renderPreview();
}

function renderPreview() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  if (loadedFrameImg) {
    ctx.drawImage(loadedFrameImg, 0, 0);
  } else {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  const getOuterVal = (dir, prop) => document.getElementById(`out-${dir}-${prop}`).value;

  const drawRotatedText = (text, x, y, angle, size, color) => {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((angle * Math.PI) / 180);
    ctx.fillStyle = color;
    ctx.font = `${size}px monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 0, 0);
    ctx.restore();
  };

  ['top', 'bottom'].forEach(d => {
    const color = getOuterVal(d, 'color');
    const size = parseInt(getOuterVal(d, 'size')) || 14;
    const angle = parseInt(getOuterVal(d, 'angle')) || 0;
    const offX = parseInt(getOuterVal(d, 'offx')) || 0;
    const offY = parseInt(getOuterVal(d, 'offy')) || 15;
    const yPos = d === 'top' ? offY : canvas.height - offY;
    for(let i=0; i<4; i++) {
      drawRotatedText("sampleid", (canvas.width / 4) * (i + 0.5) + offX, yPos, angle, size, color);
    }
  });

  ['left', 'right'].forEach(d => {
    const color = getOuterVal(d, 'color');
    const size = parseInt(getOuterVal(d, 'size')) || 14;
    const angle = parseInt(getOuterVal(d, 'angle')) || 0;
    const offX = parseInt(getOuterVal(d, 'offx')) || 15;
    const offY = parseInt(getOuterVal(d, 'offy')) || 0;
    const xPos = d === 'left' ? offX : canvas.width - offX;
    for(let i=0; i<4; i++) {
      drawRotatedText("sampleid", xPos, (canvas.height / 4) * (i + 0.5) + offY, angle, size, color);
    }
  });

  qrConfigs.forEach((cfg) => {
    if (!cfg.isTransparent) {
      ctx.fillStyle = cfg.backColor;
      ctx.fillRect(cfg.x, cfg.y, cfg.size, cfg.size);
    }
    ctx.fillStyle = cfg.fillColor;
    ctx.fillRect(cfg.x + 10, cfg.y + 10, cfg.size - 20, cfg.size - 20);
    
    let tx = cfg.x + (cfg.size / 2);
    let ty = cfg.y + cfg.size + cfg.textSize;
    let align = "center";
    let baseline = "alphabetic";

    const margin = parseInt(cfg.textMargin) || 0;
    const pos = cfg.textPosition || 'bottom';

    if (pos === 'bottom') {
      tx = cfg.x + (cfg.size / 2);
      ty = cfg.y + cfg.size + margin + cfg.textSize;
      align = "center";
    } else if (pos === 'top') {
      tx = cfg.x + (cfg.size / 2);
      ty = cfg.y - margin;
      align = "center";
    } else if (pos === 'left') {
      tx = cfg.x - margin;
      ty = cfg.y + (cfg.size / 2);
      align = "right";
      baseline = "middle";
    } else if (pos === 'right') {
      tx = cfg.x + cfg.size + margin;
      ty = cfg.y + (cfg.size / 2);
      align = "left";
      baseline = "middle";
    }

    ctx.fillStyle = cfg.textColor;
    ctx.font = `${cfg.textSize}px monospace`;
    ctx.textAlign = align;
    ctx.textBaseline = baseline;
    ctx.fillText("sampleid", tx, ty);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
  });

  document.getElementById('qr-params-json').value = JSON.stringify(qrConfigs);
  document.getElementById('outer-params-json').value = JSON.stringify({
    top: { color: getOuterVal('top', 'color'), size: getOuterVal('top', 'size'), angle: getOuterVal('top', 'angle'), offsetX: getOuterVal('top', 'offx'), offsetY: getOuterVal('top', 'offy') },
    bottom: { color: getOuterVal('bottom', 'color'), size: getOuterVal('bottom', 'size'), angle: getOuterVal('bottom', 'angle'), offsetX: getOuterVal('bottom', 'offx'), offsetY: getOuterVal('bottom', 'offy') },
    left: { color: getOuterVal('left', 'color'), size: getOuterVal('left', 'size'), angle: getOuterVal('left', 'angle'), offsetX: getOuterVal('left', 'offx'), offsetY: getOuterVal('left', 'offy') },
    right: { color: getOuterVal('right', 'color'), size: getOuterVal('right', 'size'), angle: getOuterVal('right', 'angle'), offsetX: getOuterVal('right', 'offx'), offsetY: getOuterVal('right', 'offy') }
  });
}

buildUI();
renderPreview();
</script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        qty = int(request.form.get("qty", 1))
        qr_params = json.loads(request.form.get("qr_params", "[]"))
        outer_params = json.loads(request.form.get("outer_params", "{}"))
        frame_file = request.files.get("frame")

        temp_dir = tempfile.mkdtemp()
        frame_path = None

        if frame_file and frame_file.filename:
            frame_path = os.path.join(temp_dir, "base_frame.png")
            # メモリ高騰を防ぐため、受取時に画像をリサイズ・圧縮保存
            uploaded_img = Image.open(frame_file)
            uploaded_img.thumbnail((1000, 1000), Image.LANCZOS)
            uploaded_img.save(frame_path, format="PNG", optimize=True)
            uploaded_img.close()
            del uploaded_img

        zip_path = os.path.join(temp_dir, "qr_uuid_codes.zip")
        csv_data = [["UUID"]]

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for i in range(qty):
                uuid_code = generate_uuid()
                csv_data.append([uuid_code])

                if frame_path:
                    img = Image.open(frame_path).convert("RGBA")
                else:
                    img = Image.new("RGBA", (600, 600), (255, 255, 255, 255))

                draw_outer_text_directional(img, uuid_code, outer_params)
                draw = ImageDraw.Draw(img)

                for config in qr_params:
                    back_color = "transparent" if config.get("isTransparent") else config.get("backColor", "#ffffff")

                    qr_img = create_qr_image(
                        uuid_code,
                        fill_color=config.get("fillColor", "#000000"),
                        back_color=back_color
                    )
                    qr_size = int(config["size"])
                    qr_resized = qr_img.resize((qr_size, qr_size), Image.NEAREST) # 高速かつ低メモリなリサイズ

                    x = int(config["x"])
                    y = int(config["y"])

                    img.paste(qr_resized, (x, y), qr_resized)

                    text_size = int(config.get("textSize", 16))
                    font = get_font(text_size)
                    text_color = config.get("textColor", "#000000")
                    margin = int(config.get("textMargin", 10))
                    pos = config.get("textPosition", "bottom")

                    if pos == "bottom":
                        tx, ty, anchor = x + (qr_size // 2), y + qr_size + margin, "mt"
                    elif pos == "top":
                        tx, ty, anchor = x + (qr_size // 2), y - margin, "mb"
                    elif pos == "left":
                        tx, ty, anchor = x - margin, y + (qr_size // 2), "rm"
                    elif pos == "right":
                        tx, ty, anchor = x + qr_size + margin, y + (qr_size // 2), "lm"
                    else:
                        tx, ty, anchor = x + (qr_size // 2), y + qr_size + margin, "mt"

                    draw.text((tx, ty), uuid_code, fill=text_color, anchor=anchor, font=font)

                    qr_img.close()
                    qr_resized.close()

                # PNG保存せずに直接ZIPストリームに追記
                temp_img_path = os.path.join(temp_dir, f"{uuid_code}.png")
                final_img = img.convert("RGB")
                final_img.save(temp_img_path, format="PNG", optimize=True)
                
                zip_file.write(temp_img_path, arcname=f"{uuid_code}.png")

                final_img.close()
                img.close()
                os.remove(temp_img_path)

                del img, final_img
                
                # C言語層のメモリまで強制解放
                gc.collect()
                trim_memory()

            csv_path = os.path.join(temp_dir, "uuid_codes.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(csv_data)
            zip_file.write(csv_path, arcname="uuid_codes.csv")
            os.remove(csv_path)

        def cleanup():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

        response = send_file(
            zip_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name="qr_uuid_codes.zip"
        )
        response.call_on_close(cleanup)
        return response

    return render_template_string(HTML_TEMPLATE)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)