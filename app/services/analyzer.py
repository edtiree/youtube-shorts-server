import json
import re
from openai import OpenAI
from loguru import logger
from app.config import settings

SYSTEM_PROMPT = """You are an expert YouTube Shorts content strategist and viral video analyst.
Your job is to analyze video transcripts and identify segments that have the
highest potential to go viral as YouTube Shorts (vertical, under 60 seconds).

You understand what makes content go viral:
- A powerful hook in the first 2-3 seconds that stops the scroll
- High emotional intensity (surprise, humor, controversy, inspiration, awe)
- A complete micro-narrative arc (setup → tension → payoff) within the clip
- High information density — every second delivers value
- A strong closing moment (punchline, revelation, cliffhanger, call to action)
- Content that triggers comments and shares (debatable takes, relatable moments)
- Natural replay value (the ending makes you want to rewatch)

You also know what to AVOID:
- Segments that start mid-sentence or mid-thought without context
- Content that requires extensive prior context to understand
- Long pauses, filler words, or low-energy stretches
- Segments that trail off without a satisfying endpoint"""


def analyze_transcript(
    transcript: list[dict],
    filename: str,
    duration: float,
    max_shorts: int = 5,
    min_duration: int = 15,
    max_duration: int = 58,
) -> list[dict]:
    """Use OpenAI GPT to analyze transcript and identify viral-worthy segments."""
    logger.info(f"Analyzing transcript with GPT ({len(transcript)} segments)")

    client = OpenAI(api_key=settings.openai_api_key)

    # Format transcript
    formatted = _format_transcript(transcript)

    user_prompt = f"""Analyze the following video transcript and identify up to {max_shorts} segments
that would perform best as standalone YouTube Shorts.

## Video Information
- Filename: {filename}
- Total Duration: {_format_time(duration)}

## Full Transcript (with timestamps)
{formatted}

## Requirements
- Each segment MUST be between {min_duration} and {max_duration} seconds
- Segments should be self-contained and understandable without prior context
- Prioritize segments with a strong natural hook in the opening line
- Prefer segments where the speaker's energy/emotion peaks
- If possible, align segment boundaries with natural sentence breaks
- Rank segments by virality potential (1 = lowest, 10 = highest)

## Output Format
Respond with a JSON object. Each element must have exactly these fields:
{{
  "segments": [
    {{
      "start_time": <float, seconds from start>,
      "end_time": <float, seconds from start>,
      "title": "<catchy, clickable title for this Short, under 50 chars>",
      "virality_score": <int, 1-10>,
      "hook_text": "<the exact opening line/phrase that serves as the hook>",
      "reasoning": "<2-3 sentences explaining why this segment has viral potential>"
    }}
  ]
}}

Return ONLY valid JSON. No markdown, no explanation outside the JSON."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    response_text = response.choices[0].message.content
    logger.info(f"GPT response (first 500 chars): {response_text[:500]}")
    segments = _parse_response(response_text, duration, min_duration, max_duration)

    # Snap to transcript word boundaries and add padding
    segments = _snap_boundaries(segments, transcript)

    # Sort by score descending
    segments.sort(key=lambda s: s["virality_score"], reverse=True)

    logger.info(f"Analysis complete: {len(segments)} segments identified")
    return segments


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for seg in transcript:
        start = _format_time(seg["start"])
        end = _format_time(seg["end"])
        lines.append(f"[{start} - {end}] {seg['text']}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    frac = int((seconds % 1) * 10)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}.{frac}"
    return f"{m:02d}:{s:02d}.{frac}"


def _parse_response(text: str, duration: float, min_dur: int, max_dur: int) -> list[dict]:
    """Parse GPT's JSON response with fallback for markdown-wrapped JSON."""
    # Try direct JSON parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code block
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            # Last resort: find the first { ... } block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                raise ValueError(f"Could not parse response as JSON: {text[:200]}")

    raw_segments = data.get("segments", data if isinstance(data, list) else [])
    logger.info(f"GPT returned {len(raw_segments)} raw segments")

    # Validate and filter
    valid = []
    for seg in raw_segments:
        start = float(seg.get("start_time", 0))
        end = float(seg.get("end_time", 0))
        seg_duration = end - start

        logger.debug(f"Segment: {start:.1f}-{end:.1f} ({seg_duration:.1f}s), duration limit: {min_dur}-{max_dur}, video duration: {duration:.1f}")

        if start >= end:
            logger.debug(f"  -> Skipped: start >= end")
            continue
        if seg_duration < max(5, min_dur - 5) or seg_duration > max_dur + 10:
            logger.debug(f"  -> Skipped: duration {seg_duration:.1f}s out of range")
            # If too long, try to trim to max_duration
            if seg_duration > max_dur + 10:
                continue
            if seg_duration < 5:
                continue
        if start < 0:
            start = 0
        if end > duration:
            end = duration

        valid.append({
            "start_time": start,
            "end_time": min(end, start + max_dur),
            "title": seg.get("title", "Untitled Short"),
            "virality_score": max(1, min(10, int(seg.get("virality_score", 5)))),
            "hook_text": seg.get("hook_text", ""),
            "reasoning": seg.get("reasoning", ""),
        })

    return valid


def _snap_boundaries(segments: list[dict], transcript: list[dict]) -> list[dict]:
    """Snap segment boundaries to nearest transcript boundaries and add padding."""
    if not transcript:
        return segments

    for seg in segments:
        # Find nearest transcript segment start that's close to our start
        best_start = seg["start_time"]
        for t in transcript:
            if abs(t["start"] - seg["start_time"]) < 2.0:
                best_start = t["start"]
                break

        # Find nearest transcript segment end that's close to our end
        best_end = seg["end_time"]
        for t in reversed(transcript):
            if abs(t["end"] - seg["end_time"]) < 2.0:
                best_end = t["end"]
                break

        # Add padding
        seg["start_time"] = max(0, best_start - 0.5)
        seg["end_time"] = best_end + 0.3

    return segments
