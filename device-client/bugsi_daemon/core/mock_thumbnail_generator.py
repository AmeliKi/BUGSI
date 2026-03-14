from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import datetime, timezone

from PIL import Image, ImageDraw

from bugsi_daemon.buffer.store import BufferStore

logger = logging.getLogger(__name__)


class MockThumbnailGenerator:
    """Generates mock camera thumbnails for testing."""

    def __init__(self, buffer: BufferStore, thumbnail_dir: str):
        self._buffer = buffer
        self._thumbnail_dir = thumbnail_dir
        self._pictures_taken = 0
        os.makedirs(thumbnail_dir, exist_ok=True)

    @property
    def pictures_taken(self) -> int:
        return self._pictures_taken

    async def maybe_generate(self, probability: float = 0.5) -> bool:
        """Generate a mock thumbnail with the given probability. Returns True if generated."""
        if random.random() > probability:
            return False

        now = datetime.now(timezone.utc)
        thumbnail_path = self._generate_thumbnail(now)
        await self._buffer.push_thumbnail(thumbnail_path, now.isoformat())
        self._pictures_taken += 1
        logger.info("Mock thumbnail generated: %s (total: %d)", thumbnail_path, self._pictures_taken)
        return True

    def _generate_thumbnail(self, timestamp: datetime) -> str:
        """Generate a mock field/nature thumbnail image."""
        # Random green/brown background (field scene)
        bg_r = random.randint(30, 80)
        bg_g = random.randint(60, 120)
        bg_b = random.randint(20, 60)
        img = Image.new("RGB", (160, 120), color=(bg_r, bg_g, bg_b))
        draw = ImageDraw.Draw(img)

        # Sky gradient at top
        for y in range(40):
            sky_b = 140 + random.randint(-10, 10)
            sky_g = 160 + random.randint(-10, 10)
            draw.line([(0, y), (160, y)], fill=(100, sky_g, sky_b))

        # Ground line
        draw.line([(0, 40), (160, 40)], fill=(bg_r - 10, bg_g - 10, bg_b - 10), width=2)

        # Random grass tufts
        for _ in range(20):
            x = random.randint(0, 160)
            y = random.randint(45, 120)
            h = random.randint(5, 15)
            green = random.randint(80, 160)
            draw.line([(x, y), (x + random.randint(-3, 3), y - h)], fill=(30, green, 20), width=1)

        # Timestamp overlay
        draw.text((4, 106), timestamp.strftime("%H:%M:%S"), fill=(255, 255, 255))

        filename = f"cap_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(self._thumbnail_dir, filename)
        img.save(filepath, "JPEG", quality=70)
        return filepath

    async def capture_snapshot(self) -> bytes:
        """Capture a single JPEG frame for the webserver live view."""
        import io

        now = datetime.now(timezone.utc)
        img = Image.new("RGB", (160, 120), color=(
            random.randint(30, 80), random.randint(60, 120), random.randint(20, 60),
        ))
        draw = ImageDraw.Draw(img)
        for y in range(40):
            draw.line([(0, y), (160, y)], fill=(100, 160 + random.randint(-10, 10), 140 + random.randint(-10, 10)))
        draw.line([(0, 40), (160, 40)], fill=(50, 80, 30), width=2)
        for _ in range(20):
            x, y_ = random.randint(0, 160), random.randint(45, 120)
            draw.line([(x, y_), (x + random.randint(-3, 3), y_ - random.randint(5, 15))],
                      fill=(30, random.randint(80, 160), 20), width=1)
        draw.text((4, 106), now.strftime("%H:%M:%S"), fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        return buf.getvalue()
