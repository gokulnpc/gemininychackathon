#!/usr/bin/env python3
"""
Flow 2 (text) — interactive test script
========================================
1. User fills in video config manually
2. Calls POST /generate-script  (source=text)
3. Displays the returned script for review
4. User confirms → calls POST /generate-video
5. Displays final video URLs

Usage:
    python test_flow2_text.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import textwrap
import uuid

import httpx

# ── helpers ───────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
CYAN  = "\033[36m"
GREEN = "\033[32m"
YELLOW= "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"


def h(label: str) -> str:
    return f"{CYAN}{BOLD}{label}{RESET}"


def ask(prompt: str, default: str = "", choices: list[str] | None = None) -> str:
    if choices:
        choices_str = " / ".join(f"{BOLD}{c}{RESET}" for c in choices)
        full = f"{prompt} [{choices_str}]"
        if default:
            full += f" (default: {BOLD}{default}{RESET})"
        full += ": "
    else:
        full = f"{prompt}"
        if default:
            full += f" (default: {BOLD}{default}{RESET})"
        full += ": "
    while True:
        raw = input(full).strip()
        val = raw or default
        if choices and val not in choices:
            print(f"  {RED}Invalid — choose one of: {', '.join(choices)}{RESET}")
            continue
        return val


def ask_multi(prompt: str, choices: list[str], default: list[str]) -> list[str]:
    default_str = ",".join(default)
    print(f"{prompt}")
    for i, c in enumerate(choices, 1):
        print(f"  {i}. {c}")
    raw = input(f"  Enter numbers separated by commas (default: {BOLD}{default_str}{RESET}): ").strip()
    if not raw:
        return default
    try:
        selected = [choices[int(x.strip()) - 1] for x in raw.split(",")]
        return selected
    except (ValueError, IndexError):
        print(f"  {RED}Invalid — using defaults.{RESET}")
        return default


def pp_json(data: dict) -> str:
    return json.dumps(data, indent=2, default=str)


# ── collect config ─────────────────────────────────────────────────────────────

def collect_config() -> dict:
    print(f"\n{h('═══ VoiceVid — Flow 2: Text → Script → Video ═══')}\n")

    print(f"{h('── Step 1: Your idea ──')}")
    print("Paste or type your video idea / topic (end with a blank line):")
    lines = []
    while True:
        line = input()
        if line == "" and lines:
            break
        lines.append(line)
    transcript = "\n".join(lines).strip()
    if not transcript:
        print(f"{RED}No idea entered — exiting.{RESET}")
        sys.exit(1)

    print(f"\n{h('── Step 2: Platforms ──')}")
    platform_choices = ["instagram_reels", "youtube_shorts", "tiktok"]
    platforms = ask_multi(
        "Which platforms do you want to target?",
        platform_choices,
        ["instagram_reels"],
    )

    print(f"\n{h('── Step 3: Video style ──')}")
    style = ask(
        "Video style",
        default="modern_energetic",
        choices=["modern_energetic", "corporate", "fun", "dramatic", "minimal"],
    )

    video_format = ask(
        "Video format",
        default="storytelling",
        choices=["storytelling", "what_if", "five_things", "random_fact", "custom"],
    )

    duration = ask(
        "Duration (seconds)",
        default="30",
        choices=["15", "25", "30", "60"],
    )

    print(f"\n{h('── Step 4: Visuals ──')}")
    art_style = ask(
        "Art style",
        default="realism",
        choices=["realism", "comic", "creepy_comic", "painting", "ghibli", "polaroid", "disney"],
    )

    caption_style = ask(
        "Caption style",
        default="bold_stroke",
        choices=["bold_stroke", "red_highlight", "sleek", "karaoke", "majestic", "beast", "elegant", "clarity"],
    )

    print(f"\n{h('── Step 5: Audio ──')}")
    music = ask(
        "Background music",
        default="none",
        choices=["none", "happy_rhythm", "quiet_before_storm", "peaceful_vibes", "brilliant_symphony", "breathing_shadows"],
    )

    print(f"\n{h('── Step 6: Optional ──')}")
    brand_voice = input("Brand voice / personality (leave blank to skip): ").strip() or None
    cta = input("Call-to-action preference (leave blank to let AI decide): ").strip() or None

    return {
        "transcript":       transcript,
        "platforms":        platforms,
        "style":            style,
        "video_format":     video_format,
        "video_duration":   int(duration),
        "art_style":        art_style,
        "caption_style":    caption_style,
        "background_music": music,
        "brand_voice":      brand_voice,
        "cta_preference":   cta,
    }


# ── display script ─────────────────────────────────────────────────────────────

def display_script(script: dict) -> None:
    print(f"\n{h('══════════════════════════════════════')}")
    print(f"{h('GENERATED SCRIPT')}")
    print(f"{h('══════════════════════════════════════')}\n")

    meta = script.get("metadata", {})
    print(f"{BOLD}Quality score:{RESET}  {meta.get('agent_quality_score', 'n/a')}/100")
    print(f"{BOLD}Target duration:{RESET} {meta.get('video_duration', '?')}s")
    print()

    hook = script.get("hook", {})
    print(f"{BOLD}HOOK ({hook.get('duration', 3)}s):{RESET}")
    print(f"  {YELLOW}{hook.get('text', '')}{RESET}\n")

    scenes = script.get("scenes", [])
    print(f"{BOLD}SCENES ({len(scenes)} total):{RESET}")
    for s in scenes:
        print(f"  {BOLD}Scene {s['scene_id']}{RESET} [{s.get('duration_seconds', '?')}s | {s.get('emotion', '')}]")
        print(f"    Voiceover : {s.get('voiceover_text', '')}")
        if s.get("visual_prompt"):
            wrapped = textwrap.fill(s["visual_prompt"], width=70, initial_indent="    Visual    : ", subsequent_indent="               ")
            print(wrapped)
        if s.get("text_overlay"):
            print(f"    Overlay   : {s['text_overlay'].get('text', '')}")
        print()

    cta = script.get("cta", {})
    print(f"{BOLD}CTA:{RESET}")
    print(f"  {cta.get('text', '')}\n")

    social = script.get("social_copy", {})
    if social:
        print(f"{BOLD}SOCIAL COPY:{RESET}")
        for platform, copy in social.items():
            print(f"  {BOLD}{platform}:{RESET}")
            if copy.get("title"):
                print(f"    Title   : {copy['title']}")
            print(f"    Caption : {copy.get('caption', '')}")
            tags = copy.get("hashtags") or copy.get("tags") or []
            if tags:
                print(f"    Tags    : {' '.join(tags[:8])}")
        print()

    print(f"{BOLD}Full voiceover script:{RESET}")
    wrapped_vo = textwrap.fill(
        script.get("voiceover_full_script", ""),
        width=80,
        initial_indent="  ",
        subsequent_indent="  ",
    )
    print(f"{wrapped_vo}\n")


# ── main flow ─────────────────────────────────────────────────────────────────

def main(base_url: str) -> None:
    cfg = collect_config()

    project_id = str(uuid.uuid4())
    print(f"\n{BOLD}Project ID:{RESET} {project_id}\n")

    # ── Phase 1: generate-script ───────────────────────────────────────────────
    while True:
        script_payload = {
            "source":           "text",
            "transcript":       cfg["transcript"],
            "target_platforms": cfg["platforms"],
            "style":            cfg["style"],
            "video_format":     cfg["video_format"],
            "video_duration":   cfg["video_duration"],
            "art_style":        cfg["art_style"],
            "caption_style":    cfg["caption_style"],
            "background_music": cfg["background_music"],
            "brand_voice":      cfg["brand_voice"],
            "cta_preference":   cfg["cta_preference"],
        }

        print(f"{CYAN}Calling POST /api/v1/projects/{project_id}/generate-script …{RESET}")
        try:
            resp = httpx.post(
                f"{base_url}/api/v1/projects/{project_id}/generate-script",
                json=script_payload,
                timeout=120.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"{RED}HTTP {e.response.status_code}: {e.response.text}{RESET}")
            sys.exit(1)
        except httpx.RequestError as e:
            print(f"{RED}Connection error: {e}{RESET}")
            sys.exit(1)

        script = resp.json()
        display_script(script)

        action = ask(
            "Action",
            default="confirm",
            choices=["confirm", "regenerate", "quit"],
        )
        if action == "confirm":
            break
        if action == "quit":
            print("Exiting.")
            sys.exit(0)
        # regenerate — loop again

    # ── Phase 2: generate-video ────────────────────────────────────────────────
    print(f"\n{CYAN}Calling POST /api/v1/projects/{project_id}/generate-video …{RESET}")
    print(f"{YELLOW}This may take several minutes (Veo 3 clips + FFmpeg composition).{RESET}\n")

    video_payload = {
        "script":           script,
        "target_platforms": cfg["platforms"],
        "caption_style":    cfg["caption_style"],
        "video_duration":   cfg["video_duration"],
        "art_style_override":    cfg["art_style"],
        "music_preset_override": cfg["background_music"],
    }

    try:
        resp = httpx.post(
            f"{base_url}/api/v1/projects/{project_id}/generate-video",
            json=video_payload,
            timeout=600.0,   # up to 10 minutes
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"{RED}HTTP {e.response.status_code}: {e.response.text}{RESET}")
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"{RED}Connection error: {e}{RESET}")
        sys.exit(1)

    pipeline = resp.json()

    print(f"\n{h('══════════════════════════════════════')}")
    print(f"{h('PIPELINE RESULT')}")
    print(f"{h('══════════════════════════════════════')}\n")

    status_color = GREEN if pipeline.get("status") == "completed" else RED
    print(f"{BOLD}Status:{RESET} {status_color}{pipeline.get('status', '?')}{RESET}\n")

    for stage in pipeline.get("stages", []):
        icon = "✓" if stage.get("status") == "completed" else ("✗" if stage.get("status") == "failed" else "…")
        detail = f"  — {stage.get('detail', '')}" if stage.get("detail") else ""
        print(f"  {icon}  {stage.get('stage', '?'):25s}{detail}")

    urls = pipeline.get("video_urls", {})
    if urls:
        print(f"\n{h('Video URLs:')}")
        for platform, url in urls.items():
            print(f"  {BOLD}{platform:<22}{RESET}  {url}")

    if pipeline.get("error"):
        print(f"\n{RED}Error: {pipeline['error']}{RESET}")

    print(f"\n{GREEN}Done! Project: {project_id}{RESET}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VoiceVid Flow 2 test script")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the FastAPI server (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    main(args.base_url)
