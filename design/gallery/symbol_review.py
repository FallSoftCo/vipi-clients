"""Build an actual-size comparison from the Vipi artwork available in the shelf."""
from html import escape

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
