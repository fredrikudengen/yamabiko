"""Write the Yamabiko logo SVGs: a yamabiko calling, with its echo.

Usage: python3 logo/make_logo.py <out_dir>

Writes logo_light.svg, logo_dark.svg and the wide full_light.svg / full_dark.svg.
The repo copies were then made with Inkscape:
  inkscape full_light.svg --export-text-to-path --export-plain-svg -o brand_full_logo_light_theme.svg
  inkscape logo_light.svg -o logo_light.png -w 500   (favicons: -w 16/32/180/192/512)
"""
import math, sys
out = sys.argv[1]

def mark(tile, fig):
    def outlined(d, w=14):
        return (f'<path d="{d}" fill="none" stroke="{tile}" stroke-width="{w+12}" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="{d}" fill="none" stroke="{fig}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')
    body = '<path d="M-44 0 Q-54 -56 -12 -72 Q28 -74 34 -34 Q38 -12 30 0 Z"/>'
    head = ('<circle cx="0" cy="-100" r="33"/><ellipse cx="30" cy="-92" rx="17" ry="14"/>'
            '<ellipse cx="-16" cy="-131" rx="10" ry="16" transform="rotate(-22 -16 -131)"/>')
    face = f'<g fill="{tile}"><circle cx="13" cy="-108" r="5.5"/><path d="M30 -91 L50 -101 L50 -79 Z"/></g>'
    arm = outlined('M2 -56 Q30 -50 44 -78') + outlined('M46 -110 Q58 -92 46 -74', 12)
    s, tx, ty = 2.0, 175, 410
    mx, my = tx + 52 * s, ty - 90 * s
    arcs = ''
    for i, op in enumerate((1, .7, .4)):
        r = 55 + i * 45
        a0, a1 = math.radians(-35), math.radians(35)
        arcs += (f'<path d="M{mx+r*math.cos(a0):.1f} {my+r*math.sin(a0):.1f} A{r} {r} 0 0 1 '
                 f'{mx+r*math.cos(a1):.1f} {my+r*math.sin(a1):.1f}" opacity="{op}"/>')
    return (f'<rect width="500" height="500" fill="{tile}"/>'
            f'<path d="M-10 510 L-10 430 Q250 370 510 430 L510 510 Z" fill="{fig}"/>'
            f'<g transform="translate({tx} {ty}) scale({s})"><g fill="{fig}">{body}{head}</g>{face}{arm}</g>'
            f'<g fill="none" stroke="{fig}" stroke-width="16" stroke-linecap="round">{arcs}</g>')

LIGHT = ('#2f5d8c', '#ffffff')
DARK = ('#8fb3dc', '#0f2236')
for name, (tile, fig) in {'light': LIGHT, 'dark': DARK}.items():
    open(f'{out}/logo_{name}.svg', 'w').write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">{mark(tile, fig)}</svg>\n')
    text = '#2c2c2a' if name == 'light' else '#f4f4f5'
    open(f'{out}/full_{name}.svg', 'w').write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1620 500">'
        f'<defs><clipPath id="r"><rect width="500" height="500" rx="70"/></clipPath></defs>'
        f'<g clip-path="url(#r)">{mark(tile, fig)}</g>'
        f'<rect x="6" y="6" width="488" height="488" rx="66" fill="none" stroke="{tile}" stroke-width="12"/>'
        f'<text x="580" y="318" font-family="Noto Sans" font-weight="700" font-size="200" fill="{text}">Yamabiko</text></svg>\n')
