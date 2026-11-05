"""Draw the default login image (logo figure calling at night). Usage: python3 logo/make_login_image.py; writes natt.svg, skumring.svg and daggry.svg; the app uses natt.svg as frontend/src/assets/login.svg."""
import math, random, sys

def figure(fig, gap, eye):
    def outlined(d, w=14):
        return (f'<path d="{d}" fill="none" stroke="{gap}" stroke-width="{w+8}" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="{d}" fill="none" stroke="{fig}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')
    body = '<path d="M-44 0 Q-54 -56 -12 -72 Q28 -74 34 -34 Q38 -12 30 0 Z"/>'
    head = ('<circle cx="0" cy="-100" r="33"/><ellipse cx="30" cy="-92" rx="17" ry="14"/>'
            '<ellipse cx="-16" cy="-131" rx="10" ry="16" transform="rotate(-22 -16 -131)"/>')
    face = f'<g fill="{eye}"><circle cx="13" cy="-108" r="5.5"/></g><path d="M30 -91 L50 -101 L50 -79 Z" fill="{gap}"/>'
    arm = outlined('M2 -56 Q30 -50 44 -78') + outlined('M46 -110 Q58 -92 46 -74', 12)
    return f'<g fill="{fig}">{body}{head}</g>{face}{arm}'

def arcs(cx, cy, radii, w, col, ops, a=(-32, 32), flip=False):
    out = ''
    for r, op in zip(radii, ops):
        a0, a1 = map(math.radians, a)
        sx = -1 if flip else 1
        x0, y0 = cx + sx*r*math.cos(a0), cy + r*math.sin(a0)
        x1, y1 = cx + sx*r*math.cos(a1), cy + r*math.sin(a1)
        out += f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 {0 if flip else 1} {x1:.1f} {y1:.1f}" opacity="{op}"/>'
    return f'<g fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round">{out}</g>'

def scene(sky, far, mid, near, fig_col, eye, glow=None, stars=True, moon=None):
    random.seed(4)
    st = ''.join(f'<circle cx="{random.randint(0,1000)}" cy="{random.randint(0,420)}" r="{random.choice([1.2,1.6,2.2])}" fill="#fff" opacity="{random.choice([.35,.5,.8])}"/>' for _ in range(60)) if stars else ''
    stops = ''.join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in sky)
    g = f'<radialGradient id="glow" cx="0.72" cy="0.62" r="0.5"><stop offset="0" stop-color="{glow}" stop-opacity=".75"/><stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient>' if glow else ''
    mn = f'<circle cx="{moon[0]}" cy="{moon[1]}" r="34" fill="#eef3fa" opacity=".9"/>' if moon else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">{stops}</linearGradient>{g}</defs>
<rect width="1000" height="1000" fill="url(#sky)"/>{'<rect width="1000" height="1000" fill="url(#glow)"/>' if glow else ''}{st}{mn}
<path d="M0 640 L120 560 L210 600 L330 500 L420 560 L520 470 L640 560 L760 430 L860 520 L1000 470 L1000 1000 L0 1000 Z" fill="{far}"/>
{arcs(745, 455, [40, 70], 8, '#ffffff', [.45, .25], flip=True)}
<path d="M0 760 L140 690 L260 730 L380 650 L520 720 L660 660 L800 720 L1000 640 L1000 1000 L0 1000 Z" fill="{mid}"/>
<path d="M-10 1010 L-10 760 Q90 720 180 690 L250 660 Q300 650 340 680 L470 790 Q600 860 1010 870 L1010 1010 Z" fill="{near}"/>
<g transform="translate(275 664) scale(1.05)">{figure(fig_col, sky[len(sky)//2][1], eye)}</g>
{arcs(330, 570, [60, 105, 150], 9, '#ffffff', [.9, .6, .35])}
</svg>'''

V = {
 'natt': scene([(0,'#0e1830'),(0.45,'#1f3558'),(0.75,'#3b5f8f'),(1,'#5b82b3')], '#2f5d8c', '#1d3557', '#0d1a2c', '#0d1a2c', '#8fb3dc', moon=(820,180)),
 'skumring': scene([(0,'#1a2740'),(0.45,'#2f5d8c'),(0.8,'#8fb3dc'),(1,'#e9c7b0')], '#4f76a6', '#2c4a75', '#14243d', '#14243d', '#e9c7b0', glow='#f4c9a4', stars=True),
 'daggry': scene([(0,'#5b82b3'),(0.5,'#a9c3e2'),(0.85,'#f1dcc8'),(1,'#f6e7d6')], '#8aa9cf', '#4f76a6', '#2f5d8c', '#18344f', '#f6e7d6', glow='#ffd9b0', stars=False),
}
for k, v in V.items():
    open(f'{k}.svg', 'w').write(v)
