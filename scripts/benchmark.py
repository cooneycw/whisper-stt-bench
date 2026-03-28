#!/usr/bin/env python3
"""Multi-model benchmark runner.

Runs a test corpus through all Whisper model sizes and reports:
- Transcription accuracy (WER against reference transcripts)
- Latency (time-to-result per utterance)
- GPU memory usage per model
- Real-time factor (processing time / audio duration)

Usage:
    python scripts/benchmark.py --corpus-dir /path/to/artifacts
    python scripts/benchmark.py --corpus-dir /path/to/artifacts --models base,small
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from whisper_bench.transcriber import AVAILABLE_MODELS, Transcriber


@dataclass
class UtteranceResult:
    file: str
    reference: str
    hypothesis: str
    wer: float
    duration_audio_s: float
    duration_process_s: float
    rtf: float


@dataclass
class ModelResult:
    model: str
    utterances: list[UtteranceResult] = field(default_factory=list)
    avg_wer: float = 0.0
    avg_rtf: float = 0.0
    total_audio_s: float = 0.0
    total_process_s: float = 0.0
    load_time_s: float = 0.0
    gpu_memory_mb: float = 0.0


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate between reference and hypothesis."""
    try:
        from jiwer import wer

        return wer(reference, hypothesis) if reference.strip() else 0.0
    except ImportError:
        # Fallback: simple word-level edit distance ratio
        ref_words = reference.lower().split()
        hyp_words = hypothesis.lower().split()
        if not ref_words:
            return 0.0
        # Levenshtein on words
        d = _levenshtein(ref_words, hyp_words)
        return d / len(ref_words)


def _levenshtein(s1: list[str], s2: list[str]) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row
    return prev_row[-1]


def get_gpu_memory_mb() -> float:
    """Get current GPU memory usage in MB via nvidia-smi."""
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip().split("\n")[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


def discover_corpus(corpus_dir: str) -> list[tuple[Path, str]]:
    """Discover WAV files and their reference transcripts from local-talk-artifacts.

    Returns list of (wav_path, reference_text) tuples.
    """
    corpus_path = Path(corpus_dir)
    items: list[tuple[Path, str]] = []

    for run_dir in sorted(corpus_path.iterdir()):
        if not run_dir.is_dir():
            continue

        wav_file = run_dir / "inbound.wav"
        if not wav_file.exists():
            pcm_file = run_dir / "inbound.raw.pcm"
            if pcm_file.exists():
                wav_file = pcm_file
            else:
                continue

        # Extract reference transcript from messages.json
        reference = ""
        messages_file = run_dir / "messages.json"
        if messages_file.exists():
            try:
                messages = json.loads(messages_file.read_text())
                user_texts = [
                    m["text"]
                    for m in messages
                    if m.get("sender") == "user" and m.get("text")
                ]
                reference = " ".join(user_texts)
            except (json.JSONDecodeError, KeyError):
                pass

        items.append((wav_file, reference))

    return items


def run_benchmark(
    corpus_dir: str,
    models: list[str],
    device: str = "auto",
    compute_type: str = "float16",
    results_dir: str = ".runtime/results",
) -> list[ModelResult]:
    """Run benchmark across specified models."""
    corpus = discover_corpus(corpus_dir)
    if not corpus:
        print(f"No audio files found in {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(corpus)} utterances from {corpus_dir}")
    print(f"Models: {', '.join(models)}")
    print()

    results: list[ModelResult] = []

    for model_name in models:
        print(f"{'=' * 60}")
        print(f"Model: {model_name}")
        print(f"{'=' * 60}")

        # Load model
        t0 = time.perf_counter()
        transcriber = Transcriber(
            model_size=model_name,
            device=device,
            compute_type=compute_type,
        )
        load_time = time.perf_counter() - t0
        gpu_mem = get_gpu_memory_mb()

        model_result = ModelResult(
            model=model_name,
            load_time_s=load_time,
            gpu_memory_mb=gpu_mem,
        )

        print(f"  Loaded in {load_time:.1f}s, GPU memory: {gpu_mem:.0f} MB")

        for wav_path, reference in corpus:
            audio_bytes = wav_path.read_bytes()
            result = transcriber.transcribe(audio_bytes)

            wer_score = compute_wer(reference, result.text) if reference else -1.0

            utt = UtteranceResult(
                file=str(wav_path.relative_to(corpus_dir)),
                reference=reference,
                hypothesis=result.text,
                wer=wer_score,
                duration_audio_s=result.duration_audio_s,
                duration_process_s=result.duration_process_s,
                rtf=result.rtf,
            )
            model_result.utterances.append(utt)

            wer_display = f"{wer_score:.1%}" if wer_score >= 0 else "N/A"
            print(
                f"  {wav_path.name}: {result.duration_audio_s:.1f}s audio, "
                f"{result.duration_process_s:.2f}s process, "
                f"RTF={result.rtf:.3f}, WER={wer_display}"
            )

        # Compute averages
        valid = [u for u in model_result.utterances if u.wer >= 0]
        model_result.avg_wer = sum(u.wer for u in valid) / len(valid) if valid else 0.0
        model_result.avg_rtf = (
            sum(u.rtf for u in model_result.utterances) / len(model_result.utterances)
            if model_result.utterances
            else 0.0
        )
        model_result.total_audio_s = sum(u.duration_audio_s for u in model_result.utterances)
        model_result.total_process_s = sum(u.duration_process_s for u in model_result.utterances)

        results.append(model_result)

        # Free GPU memory
        del transcriber

        print(
            f"  Summary: avg WER={model_result.avg_wer:.1%}, "
            f"avg RTF={model_result.avg_rtf:.3f}, "
            f"total audio={model_result.total_audio_s:.1f}s"
        )
        print()

    # Save results
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_file = out_dir / f"benchmark-{ts}.json"
    out_file.write_text(json.dumps([asdict(r) for r in results], indent=2))
    print(f"Results saved to {out_file}")

    # Print comparison table
    print()
    print(f"{'Model':<20} {'Avg WER':>10} {'Avg RTF':>10} {'GPU MB':>10} {'Load (s)':>10}")
    print("-" * 62)
    for r in results:
        print(
            f"{r.model:<20} {r.avg_wer:>9.1%} {r.avg_rtf:>10.3f} "
            f"{r.gpu_memory_mb:>10.0f} {r.load_time_s:>10.1f}"
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper STT Benchmark Runner")
    parser.add_argument(
        "--corpus-dir",
        required=True,
        help="Path to directory with WAV/PCM files (e.g. .runtime/local-talk-artifacts)",
    )
    parser.add_argument(
        "--models",
        default=",".join(AVAILABLE_MODELS),
        help=f"Comma-separated model sizes (default: {','.join(AVAILABLE_MODELS)})",
    )
    parser.add_argument(
        "--device", default="auto", help="Device: auto, cuda, cpu"
    )
    parser.add_argument(
        "--compute-type", default="float16",
        help="Compute type: float16, int8, float32",
    )
    parser.add_argument("--results-dir", default=".runtime/results", help="Output directory")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    run_benchmark(
        corpus_dir=args.corpus_dir,
        models=models,
        device=args.device,
        compute_type=args.compute_type,
        results_dir=args.results_dir,
    )


if __name__ == "__main__":
    main()
