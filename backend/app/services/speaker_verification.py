"""Speaker verification — Phase 2.2.

Compares each answer's voice embedding against the candidate's first
answer to catch proxy-interview cases (someone else takes the
interview). Cannot be defeated by relay tools that play the candidate's
own voice — a different speaker on a later answer will show a high
cosine distance from the reference.

Optional dependency: `speechbrain` (which pulls `torch` + `torchaudio`,
~2-3 GB on disk). Intentionally NOT in `requirements.txt` — operators
who want this feature install it themselves and flip
`settings.ENABLE_SPEAKER_VERIFICATION`. If the import fails or the
runtime call raises, every public function in this module returns
`None` / a sentinel and the rest of the system continues unchanged.

Surface:
- `is_available()` — True iff speechbrain imports cleanly.
- `extract_embedding(audio_path)` — list[float] embedding, or None on
  any failure path.
- `cosine_distance(a, b)` — 0.0–2.0, or None if either input is
  unusable. Lower = same speaker; ECAPA-TDNN typically separates
  same-speaker (≤0.25) from different-speaker (≥0.4) on clean audio.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


# Module-level lazy state. The model is large; we load on first use and
# guard with a lock so concurrent requests don't double-load.
_MODEL = None
_LOCK = threading.Lock()
_IMPORT_ATTEMPTED = False
_IMPORT_OK = False


def _try_import() -> bool:
    """Import speechbrain on demand. Cache the result so we don't
    re-attempt on every call; if the operator hasn't installed it, we
    log once and stay quiet thereafter."""
    global _IMPORT_ATTEMPTED, _IMPORT_OK
    if _IMPORT_ATTEMPTED:
        return _IMPORT_OK
    _IMPORT_ATTEMPTED = True
    try:
        # Imported here to avoid pulling torch into the module graph
        # for everyone who imports this file.
        from speechbrain.pretrained import EncoderClassifier  # noqa: F401
        _IMPORT_OK = True
    except Exception:
        logger.warning(
            "Speaker verification disabled: speechbrain import failed "
            "(install with `pip install speechbrain torch torchaudio` "
            "to enable)."
        )
        _IMPORT_OK = False
    return _IMPORT_OK


def is_available() -> bool:
    return _try_import()


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not _try_import():
        return None
    with _LOCK:
        if _MODEL is None:
            from speechbrain.pretrained import EncoderClassifier
            _MODEL = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                # Cache under a project-local path so the 80MB download
                # doesn't surprise people with $HOME quota issues.
                savedir="pretrained_models/spkrec-ecapa-voxceleb",
            )
    return _MODEL


def extract_embedding(audio_path: str) -> Optional[List[float]]:
    """Return a list-of-floats speaker embedding for the given audio,
    or None if the model isn't available, the file doesn't exist, or
    inference raises. Soft-fails on every error path so the caller's
    pipeline is never blocked by speaker verification."""
    if not _try_import():
        return None
    try:
        import torchaudio  # type: ignore
    except Exception:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        signal, _sr = torchaudio.load(audio_path)
        # speechbrain returns a [batch, time, dim] tensor; squeeze.
        emb = model.encode_batch(signal)
        emb = emb.squeeze().tolist()
        if isinstance(emb, float):
            # Defensive: 1-D embedding shouldn't happen with ECAPA but
            # handle it just in case so downstream code doesn't crash.
            return [emb]
        return [float(x) for x in emb]
    except Exception:
        logger.exception("Speaker embedding extraction failed for %s", audio_path)
        return None


def cosine_distance(a: Optional[List[float]], b: Optional[List[float]]) -> Optional[float]:
    """1 - cosine similarity. Range [0, 2]. Lower = more similar
    speakers. Returns None when either embedding is missing or
    malformed (different lengths, zero norm, etc.) — caller treats
    None as "no signal here", not as "definitely different speakers"."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return None
    similarity = dot / (norm_a * norm_b)
    # Clamp to handle minor float drift outside [-1, 1].
    similarity = max(-1.0, min(1.0, similarity))
    return round(1.0 - similarity, 4)
