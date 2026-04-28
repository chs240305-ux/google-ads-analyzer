from __future__ import annotations

import yt_dlp
import cv2
import os
import tempfile
import numpy as np
from PIL import Image


def get_video_info(url: str) -> dict | None:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "channel": info.get("uploader", ""),
                "duration": info.get("duration", 0),
                "view_count": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
                "upload_date": info.get("upload_date", ""),
                "thumbnail": info.get("thumbnail", ""),
                "description": info.get("description", ""),
            }
    except Exception as e:
        return None


def download_video(url: str, output_dir: str) -> str | None:
    output_path = os.path.join(output_dir, "video.mp4")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path if os.path.exists(output_path) else None
    except Exception:
        return None


def extract_frames(video_path: str, interval_seconds: float = 2.0) -> list[dict]:
    """
    Extract frames at regular intervals.
    Returns list of {timestamp, frame (PIL Image)}.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    frame_interval = max(1, int(fps * interval_seconds))
    frames = []

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            timestamp = frame_idx / fps if fps > 0 else 0
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            frames.append({"timestamp": timestamp, "image": pil_image})
        frame_idx += 1

    cap.release()
    return frames


def format_view_count(count: int) -> str:
    if count >= 10000:
        return f"{count // 10000}만"
    if count >= 1000:
        return f"{count / 1000:.1f}천"
    return str(count)


def format_upload_date(date_str: str) -> str:
    if len(date_str) == 8:
        return f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"
    return date_str
