"""Build an actual-size comparison from the Vipi artwork available in the shelf."""
from html import escape
import os
from PIL import Image

CANDIDATES = (
    ("Borrowed Word", "speech-symbols", "borrowed", "A new piece completes a familiar message."),
    ("Shared Meaning", "speech-symbols", "shared", "Two replies share a word-shaped opening."),
)
COLORS = {"guava": "Guava", "marigold": "Marigold", "black": "One ink"}


def render(output):
    available = [(name, folder, mark, description) for name, folder, mark, description in CANDIDATES
                 if all((output / folder / f"{mark}-{color}-launcher.svg").is_file() for color in COLORS)]
    if not available:
        return None
    modes = "".join(f'<input type="radio" name="color" id="{key}" value="{key}" '
                    f'aria-label="{title}" {"checked" if key=="guava" else ""}>'
                    for key, title in COLORS.items())
    labels = "".join(f'<label for="{key}">{title}</label>' for key, title in COLORS.items())
    def artwork(folder, mark, size):
        # Each image retains a real CSS-pixel size, including on a narrow phone.
        return "".join(f'<img class="art {color}" alt="" width="{size}" height="{size}" '
                       f'src="{folder}/{mark}-{color}-launcher.svg">' for color in COLORS)
    cards = []
    for name, folder, mark, description in available:
        small = "".join(f'<figure>{artwork(folder,mark,px)}<figcaption>{px} px</figcaption></figure>'
                        for px in (24,32,60))
        cards.append(f'<article><div class="large">{artwork(folder,mark,140)}</div>'
                     f'<h2>{escape(name)}</h2><p>{escape(description)}</p><div class="sizes">{small}</div></article>')
    rules = "".join(f'#{key}:checked ~ .choices label[for={key}]{{background:var(--ink);color:var(--paper)}}'
                    f'#{key}:checked ~ .cards .art.{key}{{display:block}}'
                    f'#{key}:focus-visible ~ .choices label[for={key}]{{outline:3px solid #A66C36;outline-offset:3px}}'
                    for key in COLORS)
    head = """<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vipi · App icon studies</title><style>
:root{--ink:#352233;--paper:#fff8ef;color-scheme:light;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
*{box-sizing:border-box}body{max-width:980px;margin:0 auto;padding:24px clamp(18px,5vw,64px) 48px}
a{color:#73435d;text-underline-offset:3px}h1{font-size:clamp(30px,5vw,48px);line-height:1.04;letter-spacing:-.035em;margin:32px 0 16px}
h2{font-size:24px;letter-spacing:-.025em;margin:18px 0 2px}p{margin:0}
fieldset{border:0;margin:24px 0;padding:0;min-width:0}.choices{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px}
fieldset>input,legend{position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden}
label{border:1px solid #937b85;border-radius:24px;padding:9px 16px;cursor:pointer;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(255px,100%),1fr));gap:28px}article{border-top:1px solid #cfbfb7;padding-top:22px}.art{display:none;border-radius:23%}
.large{display:flex;justify-content:flex-start;padding-left:2px}.large img{outline:1px solid #c5b4a9;outline-offset:-1px}.sizes{display:flex;gap:28px;margin-top:26px;align-items:flex-end}figure{margin:0;text-align:center}
figcaption{font-size:14px;margin-top:6px;color:#6d5263}.chat{display:inline-block;border-radius:16px 16px 16px 4px;background:#eee1db;padding:12px 18px}.chat mark{color:#56380c;background:#f6db8d;padding:1px 4px;border-radius:4px}
"""
    return (head + rules + '</style></head><body><a href="review.html">Vipi gallery</a><h1>App icon studies</h1>'
            '<p class="chat">See you <mark>mañana</mark>.</p><fieldset><legend>Icon color</legend>' + modes +
            '<div class="choices">' + labels + '</div><div class="cards">' + "".join(cards) +
            '</div></fieldset></body></html>').encode()


def render_launchers(output, *, greeting=False):
    options = {"signature": "Vipi signature", "voice": "Songbird", "corner": "Speech mark"}
    folder = "wrapped-greeting" if greeting else "home-screen"
    if greeting:
        options = {"wrap": "Question wrap", "signature": "Original signature"}
    sources = {key: folder for key in options}
    if greeting and (output / "guava-dots/iphone-home-guava.png").is_file():
        options = {"guava": "Guava i dots", "wrap": "Cream i dots", "signature": "Original signature"}
        sources["guava"] = "guava-dots"
    scenes = (("iphone-grid", "iPhone", 277), ("pixel-home", "Pixel dock", 393), ("pixel-drawer", "Pixel app drawer", 393))
    newer = output / folder / "iphone-home-signature.png"
    if newer.is_file():
        scenes = (("iphone-home", "iPhone", 402), *scenes[1:])
    if not all((output / sources[symbol] / f"{prefix}-{symbol}.png").is_file() for prefix, _, _ in scenes for symbol in options):
        return None
    radios = "".join(f'<input id="{k}" type="radio" name="symbol" value="{k}" aria-label="{v}" '
                     f'{"checked" if k==next(iter(options)) else ""}>' for k,v in options.items())
    buttons = "".join(f'<label for="{k}">{v}</label>' for k,v in options.items())
    style = "".join(f'#{k}:checked ~ .options label[for={k}]{{background:#45233f;color:#fff3de}}'
                    f'#{k}:checked ~ .scenes .{k}{{display:block}}'
                    f'#{k}:focus-visible ~ .options label[for={k}]{{outline:3px solid #91602D;outline-offset:3px}}'
                    for k in options)
    cards = []
    for prefix, title, width in scenes:
        tags = []
        for key, name in options.items():
            original = output / sources[key] / f"{prefix}-{key}.png"
            preview = original.with_suffix(".webp")
            with Image.open(original) as image:
                height = round(width * image.height / image.width)
                if not preview.exists() or preview.stat().st_mtime_ns < original.stat().st_mtime_ns:
                    scaled = image.convert("RGB")
                    scaled.thumbnail((width * 2, height * 2), Image.Resampling.LANCZOS)
                    temporary = preview.with_suffix(".next")
                    scaled.save(temporary, "WEBP", quality=92, method=5)
                    temporary.chmod(0o644)
                    os.replace(temporary, preview)
            tags.append(f'<img class="{key}" src="{sources[key]}/{preview.name}" width="{width}" '
                        f'height="{height}" alt="{name} on the {title} launcher">')
        images = "".join(tags)
        cards.append(f'<section><h2>{title}</h2>{images}</section>')
    return ('''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vipi on your home screen</title><style>
:root{font:16px/1.45 system-ui,sans-serif;color:#352233;background:#fff8ef;color-scheme:light}*{box-sizing:border-box}
body{max-width:1340px;margin:auto;padding:20px clamp(12px,2.4vw,36px) 32px}a{color:#714059;text-underline-offset:3px}
h1{font-size:clamp(28px,4vw,42px);letter-spacing:-.04em;line-height:1.1;margin:25px 0 6px}p{margin:0;color:#65475b}
fieldset{min-width:0;border:0;margin:20px 0;padding:0}input,legend{position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden}
.options{display:flex;gap:6px;flex-wrap:wrap}label{border:1px solid #947f88;padding:9px 13px;border-radius:22px;cursor:pointer;font-weight:600}
.scenes{display:flex;gap:clamp(14px,3vw,42px);align-items:flex-start;flex-wrap:wrap}section{max-width:100%}h2{font-size:20px;letter-spacing:-.015em;margin:22px 0 8px}
img{display:none;max-width:100%;height:auto;border-radius:8px}''' + style +
            f'</style></head><body><a href="review.html#{folder}">Vipi gallery</a><h1>{"Vipi as a greeting" if greeting else "Vipi on the home screen"}</h1>'
            '<p>Choose a mark to see it in the same spot on each launcher.</p><fieldset><legend>Vipi mark</legend>' +
            radios + '<div class="options">' + buttons + '</div><div class="scenes">' + "".join(cards) +
            '</div></fieldset><p>Design studies placed on native simulator screenshots.</p></body></html>').encode()
