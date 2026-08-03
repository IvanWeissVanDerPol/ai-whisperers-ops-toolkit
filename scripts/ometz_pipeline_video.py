#!/usr/bin/env python3
"""
ometz_pipeline_video.py — Pipeline de post-producción para Luana
Automatiza: transcripción con Whisper + normalización de audio + variantes de formato

Uso:
    python3 ometz_pipeline_video.py video-hero-3min.mp4
    python3 ometz_pipeline_video.py video.mp4 --lang en --model large-v3

Output:
    subs/{nombre}.srt              ← Subtítulos en español (SRT)
    subs/{nombre}.txt              ← Transcripción en texto plano
    {nombre}-normalized.mp4        ← Audio normalizado (loudnorm -16 LUFS)
    {nombre}-ig-vertical.mp4       ← Versión IG vertical 9:16
    {nombre}-ig-square.mp4         ← Versión IG cuadrada 1:1
    {nombre}-web.mp4               ← Versión web horizontal 16:9
"""

import subprocess
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime


def run(cmd, description=""):
    """Ejecuta un comando y muestra el output."""
    print(f"  → {description or ' '.join(cmd[:3])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  Error: {result.stderr[:200]}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline post-producción Ometz · Luana"
    )
    parser.add_argument("video", help="Path al video de entrada (MP4/MOV)")
    parser.add_argument("--lang", default="Spanish", help="Idioma (Spanish/English)")
    parser.add_argument("--model", default="medium", help="Modelo Whisper (tiny/base/small/medium/large-v3)")
    parser.add_argument("--out-dir", default=".", help="Directorio de salida")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"❌ Video no encontrado: {video}")
        sys.exit(1)

    nombre = video.stem
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subs_dir = out_dir / "subs"
    subs_dir.mkdir(exist_ok=True)

    print(f"\n🎬 Ometz Pipeline · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Video: {video}")
    print(f"📁 Output dir: {out_dir}")
    print(f"🌍 Idioma: {args.lang} · Modelo Whisper: {args.model}\n")

    # 1. Transcripción con Whisper
    print("━" * 50)
    print("📝 1/4 · Transcribiendo con Whisper...")
    print("━" * 50)
    run([
        "whisper", str(video),
        "--language", args.lang,
        "--model", args.model,
        "--output_format", "srt",
        "--output_format", "txt",
        "--output_dir", str(subs_dir)
    ], "Whisper → SRT + TXT")

    # Renombrar para incluir nombre original
    for ext in ["srt", "txt"]:
        src = subs_dir / f"{video.stem}.{ext}"
        if src.exists():
            dst = subs_dir / f"{nombre}.{ext}"
            if src != dst:
                src.rename(dst)

    # 2. Normalización de audio
    print("\n" + "━" * 50)
    print("🔊 2/4 · Normalizando audio (-16 LUFS)...")
    print("━" * 50)
    normalized = out_dir / f"{nombre}-normalized.mp4"
    run([
        "ffmpeg", "-y", "-i", str(video),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "copy",
        str(normalized)
    ], "ffmpeg loudnorm")

    # 3. Variante IG vertical 9:16
    print("\n" + "━" * 50)
    print("📱 3/4 · Generando variantes...")
    print("━" * 50)
    ig_vertical = out_dir / f"{nombre}-ig-vertical.mp4"
    run([
        "ffmpeg", "-y", "-i", str(normalized if normalized.exists() else video),
        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        "-c:a", "copy",
        str(ig_vertical)
    ], "IG vertical 9:16")

    # 4. Variante IG cuadrada 1:1
    ig_square = out_dir / f"{nombre}-ig-square.mp4"
    run([
        "ffmpeg", "-y", "-i", str(normalized if normalized.exists() else video),
        "-vf", "crop=ih:ih,scale=1080:1080",
        "-c:a", "copy",
        str(ig_square)
    ], "IG cuadrado 1:1")

    # 5. Variante web horizontal 16:9
    web = out_dir / f"{nombre}-web.mp4"
    run([
        "ffmpeg", "-y", "-i", str(normalized if normalized.exists() else video),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:a", "copy",
        str(web)
    ], "Web 16:9")

    # Resumen final
    print("\n" + "═" * 50)
    print("✅ PIPELINE COMPLETADO")
    print("═" * 50)
    archivos = [
        f"📝 {subs_dir}/{nombre}.srt",
        f"📄 {subs_dir}/{nombre}.txt",
        f"🔊 {normalized}",
        f"📱 {ig_vertical}",
        f"📱 {ig_square}",
        f"🌐 {web}",
    ]
    for archivo in archivos:
        path = Path(archivo.split(" ", 1)[1])
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  ✅ {archivo} ({size_mb:.1f} MB)")
        else:
            print(f"  ❌ {archivo} (no generado)")

    print(f"\n💡 Próximos pasos:")
    print(f"  1. Abrir {normalized} en DaVinci Resolve")
    print(f"  2. Importar {subs_dir}/{nombre}.srt como subtítulos")
    print(f"  3. Aplicar paleta lila (#7251b5) en Color")
    print(f"  4. Exportar versión final")
    print()


if __name__ == "__main__":
    main()
