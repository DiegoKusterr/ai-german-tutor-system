from __future__ import annotations

from pathlib import Path
import sys


PORTRAIT_DIR = Path(__file__).resolve().parent / "static" / "assets" / "tutor-portraits"

PERSONA_PORTRAIT_SET = {
    "studio": "woman",
    "coach": "man",
    "examiner": "man",
}

EXPECTED_FILES = {
    "woman": [
        "woman-base.webp",
        "woman-blink.webp",
        "woman-mouth-1.webp",
        "woman-mouth-2.webp",
        "woman-mouth-3.webp",
        "woman-mouth-4.webp",
    ],
    "man": [
        "man-base.webp",
        "man-blink.webp",
        "man-mouth-1.webp",
        "man-mouth-2.webp",
        "man-mouth-3.webp",
        "man-mouth-4.webp",
    ],
}


def main() -> int:
    print("Tutor Portrait Readiness")
    print("========================")
    print(f"Folder: {PORTRAIT_DIR}")
    print()

    if not PORTRAIT_DIR.exists():
        print("Status: MISSING FOLDER")
        print("The portrait directory does not exist.")
        return 1

    print("Status: FOLDER PRESENT")
    print()

    total_expected = sum(len(files) for files in EXPECTED_FILES.values())
    total_present = 0
    all_complete = True

    print("Persona routing")
    print("---------------")
    for persona, portrait_set in PERSONA_PORTRAIT_SET.items():
        print(f"{persona} -> {portrait_set}")
    print()

    for portrait_set, filenames in EXPECTED_FILES.items():
        present = []
        missing = []
        for filename in filenames:
            path = PORTRAIT_DIR / filename
            if path.is_file():
                present.append(filename)
                total_present += 1
            else:
                missing.append(filename)

        portrait_set_complete = not missing
        all_complete = all_complete and portrait_set_complete

        print(f"{portrait_set.upper()}: {'COMPLETE' if portrait_set_complete else 'INCOMPLETE'}")
        print(f"  Present ({len(present)}/{len(filenames)}):")
        if present:
            for filename in present:
                print(f"    - {filename}")
        else:
            print("    - none")
        print("  Missing:")
        if missing:
            for filename in missing:
                print(f"    - {filename}")
        else:
            print("    - none")
        print()

    print("Overall")
    print("-------")
    print(f"Present files: {total_present}/{total_expected}")
    print(f"Portrait sets complete: {sum(1 for files in EXPECTED_FILES.values() if all((PORTRAIT_DIR / name).is_file() for name in files))}/{len(EXPECTED_FILES)}")
    print(f"Portrait pack ready: {'YES' if all_complete else 'NO'}")
    print()

    if all_complete:
        print("The Tutor can load the shared woman/man portrait layers for all personas without further code changes.")
        return 0

    print("The app will keep the current safe placeholder for any persona whose shared portrait layers are incomplete.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
