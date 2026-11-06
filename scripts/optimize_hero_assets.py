import os
import shutil
import subprocess
from PIL import Image
import numpy as np

src_hero_dir = r"e:\projects\Raphael\frontend\assets-src\hero"
public_hero_dir = r"e:\projects\Raphael\frontend\public\hero"
os.makedirs(src_hero_dir, exist_ok=True)

orig_png = os.path.join(public_hero_dir, "ribbon.png")
orig_mp4 = os.path.join(public_hero_dir, "ribbon.mp4")

# Copy originals to assets-src/hero
shutil.copy2(orig_png, os.path.join(src_hero_dir, "ribbon.png"))
shutil.copy2(orig_mp4, os.path.join(src_hero_dir, "ribbon.mp4"))
print(f"Originals backed up to {src_hero_dir}")

# Check first frame of video vs poster
frame0_path = os.path.join(src_hero_dir, "frame0.png")
subprocess.run([
    "ffmpeg", "-y", "-i", orig_mp4, "-vframes", "1", "-f", "image2", frame0_path
], check=True)

img_poster = Image.open(orig_png).convert("RGB")
img_frame0 = Image.open(frame0_path).convert("RGB")
print(f"Poster size: {img_poster.size}, Frame0 size: {img_frame0.size}")

# Resize frame0 to poster size if different for MSE check
if img_poster.size != img_frame0.size:
    img_frame0_resized = img_frame0.resize(img_poster.size, Image.Resampling.LANCZOS)
else:
    img_frame0_resized = img_frame0

arr_poster = np.array(img_poster, dtype=np.float32)
arr_frame0 = np.array(img_frame0_resized, dtype=np.float32)
diff = np.abs(arr_poster - arr_frame0)
mse = np.mean(diff ** 2)
mae = np.mean(diff)
print(f"Difference between poster and video frame 0: MAE={mae:.2f}, MSE={mse:.2f}")

# Generate ribbon.webp (desktop, quality ~82, target < 400KB)
out_webp = os.path.join(public_hero_dir, "ribbon.webp")
img_poster.save(out_webp, "WEBP", quality=82, method=6)
size_webp = os.path.getsize(out_webp)
print(f"Desktop ribbon.webp (q=82): {size_webp / 1024:.1f} KB")

# If > 400KB, adjust quality or resize slightly
q = 82
while size_webp > 400 * 1024 and q > 50:
    q -= 5
    img_poster.save(out_webp, "WEBP", quality=q, method=6)
    size_webp = os.path.getsize(out_webp)
    print(f"Desktop ribbon.webp (q={q}): {size_webp / 1024:.1f} KB")

# Generate ribbon@mobile.webp (width ~800px, quality ~82, target < 150KB)
out_mobile_webp = os.path.join(public_hero_dir, "ribbon@mobile.webp")
aspect = img_poster.height / img_poster.width
mobile_w = 800
mobile_h = int(800 * aspect)
img_mobile = img_poster.resize((mobile_w, mobile_h), Image.Resampling.LANCZOS)
img_mobile.save(out_mobile_webp, "WEBP", quality=82, method=6)
size_mobile = os.path.getsize(out_mobile_webp)
print(f"Mobile ribbon@mobile.webp (q=82): {size_mobile / 1024:.1f} KB")
q_m = 82
while size_mobile > 150 * 1024 and q_m > 50:
    q_m -= 5
    img_mobile.save(out_mobile_webp, "WEBP", quality=q_m, method=6)
    size_mobile = os.path.getsize(out_mobile_webp)
    print(f"Mobile ribbon@mobile.webp (q={q_m}): {size_mobile / 1024:.1f} KB")

# Encode ribbon.webm with VP9 under 2MB
out_webm = os.path.join(public_hero_dir, "ribbon.webm")
# 2-pass or crf VP9
cmd_webm = [
    "ffmpeg", "-y", "-i", orig_mp4,
    "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "33",
    "-an", out_webm
]
print("Encoding VP9 ribbon.webm...")
subprocess.run(cmd_webm, check=True)
size_webm = os.path.getsize(out_webm)
print(f"ribbon.webm: {size_webm / 1024 / 1024:.2f} MB")
if size_webm > 2 * 1024 * 1024:
    cmd_webm_crf = [
        "ffmpeg", "-y", "-i", orig_mp4,
        "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "38",
        "-an", out_webm
    ]
    subprocess.run(cmd_webm_crf, check=True)
    size_webm = os.path.getsize(out_webm)
    print(f"ribbon.webm (crf 38): {size_webm / 1024 / 1024:.2f} MB")

# Also check ribbon.mp4 size
size_mp4 = os.path.getsize(orig_mp4)
print(f"ribbon.mp4: {size_mp4 / 1024 / 1024:.2f} MB")
