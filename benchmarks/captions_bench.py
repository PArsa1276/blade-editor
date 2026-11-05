"""Persian captions benchmark: word/character error rate and timing of Blade's transcript.

Ground truth: truth.json = [{"start", "end", "text"}, ...] (utterances in one audio file, e.g.
Google FLEURS fa_ir, CC BY 4.0). Transcript: the dict that captions.transcribe() returns (or a
fixed transcript file).

    python benchmarks/captions_bench.py truth.json transcript.json

Metrics:
- WER: word error rate after Persian normalisation (ي->ی, ك->ک, digits, diacritics and
  punctuation removed, half-space = space). CER: the same on characters without spaces.
- in_window: share of transcript words (matched to a reference word) whose start time is
  inside the time of the sentence they belong to (+-0.5 s). This is what captions need.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata

TABLE = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا",
                       "‌": " ", "‏": "", "‎": "",
                       **{c: str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")},
                       **{c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}})


def norm(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text).translate(TABLE)
    t = re.sub(r"[ً-ْٰـ]", "", t)          # diacritics, tatweel
    t = re.sub(r"[^\w\s]|_", " ", t)                            # punctuation
    return t.lower().split()


def _edits(a: list, b: list) -> tuple[int, list[tuple[int, int]]]:
    """Levenshtein distance and the matched (equal) index pairs."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    pairs, i, j = [], n, m
    while i and j:
        if a[i - 1] == b[j - 1] and d[i][j] == d[i - 1][j - 1]:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif d[i][j] == d[i - 1][j - 1] + 1:
            i -= 1; j -= 1
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return d[n][m], pairs[::-1]


def score(truth: list[dict], transcript: dict) -> dict:
    ref, ref_utt = [], []
    for k, u in enumerate(truth):
        w = norm(u["text"]); ref += w; ref_utt += [k] * len(w)
    hyp, hyp_t = [], []
    for s in transcript["segments"]:
        words = s.get("words") or []
        if words:
            for w in words:
                for tok in norm(w["word"]):
                    hyp.append(tok); hyp_t.append(w["start"])
        else:
            toks = norm(s["text"]); hyp += toks; hyp_t += [s["start"]] * len(toks)
    dist, pairs = _edits(ref, hyp)
    cref, chyp = list("".join(ref)), list("".join(hyp))
    cdist, _ = _edits(cref, chyp) if len(cref) * len(chyp) < 4e7 else (None, None)
    inside = sum(truth[ref_utt[i]]["start"] - 0.5 <= hyp_t[j] <= truth[ref_utt[i]]["end"] + 0.5 for i, j in pairs)
    return {"ref_words": len(ref), "hyp_words": len(hyp), "wer": round(dist / len(ref), 4),
            "cer": round(cdist / len(cref), 4) if cdist is not None else None,
            "matched_words": len(pairs), "in_window": round(inside / max(1, len(pairs)), 4)}


if __name__ == "__main__":
    truth = json.load(open(sys.argv[1], encoding="utf-8"))
    tr = json.load(open(sys.argv[2], encoding="utf-8"))
    print(json.dumps(score(truth, tr), ensure_ascii=False))
