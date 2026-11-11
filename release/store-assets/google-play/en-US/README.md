# Vipi Google Play assets — en-US

The four PNG assets were approved and saved to the private Vipi Play listing on November 10, 2026. The title and descriptions were preserved. No binary was uploaded and nothing was submitted or published.

The icon is rendered directly from the existing vector brand. The feature graphic is an original SVG composition using the same paths and colors. Render with `rsvg-convert -w 512 -h 512 -o vipi-icon-512.png vipi-icon.svg` and `rsvg-convert -o vipi-feature-1024x500.png vipi-feature-1024x500.svg`; the feature text uses DejaVu Sans. Opaque alpha was removed only after proving all RGB pixels unchanged.

The phone screenshots are actual 1080 × 2160 captures from the existing signed-in 007 QA app. They establish visual parity, not execution of the final signed bundle. The original account title and two existing messages are unchanged. Original RGBA captures are retained for pixel comparison. The emulator returned to 1080 × 2400 at 420 dpi and the first message returned to Latin reading.

The saved phone order is Latin reading, then Japanese script, matching the default reading experience. Server previews are downscaled; the uploaded originals retain their full dimensions. `provenance.json` binds all source and image hashes and records the limits. These release-only files do not change the frozen application inputs.
