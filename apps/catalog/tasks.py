"""Video pipeline: transcode uploaded lesson video to HLS renditions + audio-only track + poster (blueprint Module 7)."""
import logging
import shutil
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings

log = logging.getLogger("apps.catalog")

RENDITIONS = [("240p", 426, 240, "400k"), ("360p", 640, 360, "800k"), ("720p", 1280, 720, "2500k")]


def _run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600)


@shared_task
def transcode_lesson(lesson_id):
    from .models import Lesson

    lesson = Lesson.objects.get(pk=lesson_id)
    ffmpeg = shutil.which(settings.FFMPEG_BINARY)
    if not lesson.video:
        return
    if not ffmpeg:
        log.warning("ffmpeg not found; serving original file for lesson %s", lesson_id)
        Lesson.objects.filter(pk=lesson_id).update(media_status="ready")
        return
    src = Path(lesson.video.path)
    out = Path(settings.MEDIA_ROOT) / "hls" / f"lesson-{lesson.pk}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    try:
        master = ["#EXTM3U"]
        for name, w, h, rate in RENDITIONS:
            _run([ffmpeg, "-y", "-i", str(src), "-vf", f"scale=w={w}:h={h}:force_original_aspect_ratio=decrease,"
                  f"pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast", "-b:v", rate,
                  "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-hls_time", "6", "-hls_playlist_type", "vod",
                  "-hls_segment_filename", str(out / f"{name}_%03d.ts"), str(out / f"{name}.m3u8")])
            bw = int(rate.rstrip("k")) * 1000 + 64000
            master += [f"#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={w}x{h},NAME=\"{name}\"", f"{name}.m3u8"]
        (out / "master.m3u8").write_text("\n".join(master) + "\n")
        audio_rel = f"lessons/audio/lesson-{lesson.pk}.m4a"
        audio_path = Path(settings.MEDIA_ROOT) / audio_rel
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        _run([ffmpeg, "-y", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "48k", "-ac", "1", str(audio_path)])
        poster_rel = f"lessons/posters/lesson-{lesson.pk}.jpg"
        poster_path = Path(settings.MEDIA_ROOT) / poster_rel
        poster_path.parent.mkdir(parents=True, exist_ok=True)
        _run([ffmpeg, "-y", "-ss", "1", "-i", str(src), "-frames:v", "1", "-vf", "scale=640:-2", str(poster_path)])
        Lesson.objects.filter(pk=lesson_id).update(
            hls_playlist=f"hls/lesson-{lesson.pk}/master.m3u8", audio=audio_rel, poster=poster_rel,
            media_status="ready",
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log.error("transcode failed for lesson %s: %s", lesson_id, getattr(exc, "stderr", b"")[-500:])
        Lesson.objects.filter(pk=lesson_id).update(media_status="failed")
