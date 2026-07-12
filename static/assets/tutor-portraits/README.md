# Tutor Portrait Asset Manifest

This folder is the expected drop location for the real layered Tutor portrait assets used by the main Tutor stage.

If any required files are missing, the app should continue to show the current safe placeholder state. No placeholder images should be added here unless they are real final portrait assets.

## Persona Routing

- `studio` uses the shared `woman` portrait set
- `coach` uses the shared `man` portrait set
- `examiner` uses the shared `man` portrait set

## Required Filenames

### Woman
- `woman-base.webp`
- `woman-blink.webp`
- `woman-mouth-1.webp`
- `woman-mouth-2.webp`
- `woman-mouth-3.webp`
- `woman-mouth-4.webp`

### Man
- `man-base.webp`
- `man-blink.webp`
- `man-mouth-1.webp`
- `man-mouth-2.webp`
- `man-mouth-3.webp`
- `man-mouth-4.webp`

## File Purpose

- `*-base.webp`
  - The full base portrait for that shared portrait set.
  - This is the main visible portrait layer.

- `*-blink.webp`
  - Transparent overlay for eye blink / eyelid closure.
  - Must align exactly with the matching base portrait.

- `*-mouth-1.webp`
  - Slight open / soft speech mouth shape.

- `*-mouth-2.webp`
  - Medium open mouth shape.

- `*-mouth-3.webp`
  - Wider open / stronger vowel mouth shape.

- `*-mouth-4.webp`
  - Rounded mouth shape for "o/u" style articulation.

## Technical Recommendations

- Format: `WebP` with alpha transparency
- Color profile: `sRGB`
- Keep each portrait set on the exact same canvas size
- Recommended canvas size per portrait set: `1024 x 1280`
- All overlays must align perfectly with the matching base portrait
- Do not crop overlays differently from the matching base portrait
- Do not shift head position, eye line, or mouth position between the matching files

## Consistency Rules

- All files for one persona must share the exact same canvas size
- All layers for one persona must be pixel-aligned
- `woman` and `man` should look like one product family
- The visual identity should differ by persona, but the framing and alignment rules should remain consistent

## Safe Fallback Behavior

- Missing files must not break the Tutor UI
- If the shared base portrait is missing, the current neutral placeholder should remain visible for every persona mapped to that set
- If the base exists but blink or mouth overlays are missing, the app should still render the base portrait and fall back gracefully

## Validation

Run the root-level validator to check readiness:

```powershell
python .\validate_tutor_portraits.py
```

The validator reports:
- whether the folder exists
- which files are present
- which files are missing
- which persona maps to which shared portrait set
- whether each portrait set is complete
- whether the full Tutor portrait asset pack is ready
