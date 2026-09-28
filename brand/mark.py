# FinanceHubW brand mark: an "F" whose middle arm becomes rising market bars + trend arrow
NAVY1,NAVY2,GREEN,GREEN2,GOLD,WHITE="#0A1A33","#0F2B55","#18C98B","#0FA870","#F2B233","#FFFFFF"

def mark(x=0,y=0,s=1.0,fg=WHITE):
    # drawn in a 1000x1000 box
    g=f'<g transform="translate({x},{y}) scale({s})">'
    # F stem + top arm (rounded, geometric)
    g+=f'<rect x="250" y="220" width="130" height="560" rx="22" fill="{fg}"/>'
    g+=f'<rect x="250" y="220" width="470" height="120" rx="22" fill="{fg}"/>'
    # middle arm (green, the "growth" arm)
    g+=f'<rect x="250" y="450" width="370" height="110" rx="22" fill="url(#gg)"/>'
    # rising trend line with arrowhead in the open lower-right
    g+=f'<path d="M430 740 L545 655 L625 690 L770 575" fill="none" stroke="{GOLD}" stroke-width="36" stroke-linecap="round" stroke-linejoin="round"/>'
    g+=f'<path d="M690 560 L785 560 L785 655" fill="none" stroke="{GOLD}" stroke-width="36" stroke-linecap="round" stroke-linejoin="round"/>'
    return g+'</g>'

DEFS=f'''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{NAVY2}"/><stop offset="1" stop-color="{NAVY1}"/></linearGradient>
<linearGradient id="gg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{GREEN}"/><stop offset="1" stop-color="{GREEN2}"/></linearGradient>
<radialGradient id="glow" cx=".7" cy=".3" r=".7"><stop offset="0" stop-color="{GREEN}" stop-opacity=".18"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></radialGradient>
</defs>'''

def grid(w,h,step=80):
    s=''.join(f'<line x1="{x}" y1="0" x2="{x}" y2="{h}"/>' for x in range(0,w,step))
    s+=''.join(f'<line x1="0" y1="{y}" x2="{w}" y2="{y}"/>' for y in range(0,h,step))
    return f'<g stroke="#FFFFFF" stroke-opacity=".04" stroke-width="2">{s}</g>'

def svg(w,h,body): return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{DEFS}{body}</svg>'

# 1. profile picture (safe inside circle crop used by X, Instagram, YouTube)
pfp=svg(1000,1000,f'<rect width="1000" height="1000" fill="url(#bg)"/><rect width="1000" height="1000" fill="url(#glow)"/>'+mark(-15,10,1.0))
# 2. icon transparent (for watermarks)
icon=svg(1000,1000,mark())

WORD=lambda x,y,size,anchor="start": (f'<text x="{x}" y="{y}" font-family="Poppins" font-weight="700" font-size="{size}" fill="{WHITE}" text-anchor="{anchor}" letter-spacing="-1">Finance<tspan fill="{GREEN}">Hub</tspan><tspan fill="{GOLD}">W</tspan></text>')
TAG=lambda x,y,size,anchor="start": f'<text x="{x}" y="{y}" font-family="Poppins" font-weight="500" font-size="{size}" fill="#9FB3CC" text-anchor="{anchor}" letter-spacing="{size*0.18:.0f}">MARKETS · CRYPTO · POLICY · ECONOMY</text>'

def spark(w,h,y0):
    import math
    pts=[(x, y0-60*math.sin(x/170)-x*0.06) for x in range(0,w+20,20)]
    d="M"+" L".join(f"{x:.0f} {y:.0f}" for x,y in pts)
    return f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-opacity=".22" stroke-width="5"/>'

# 3. X header 1500x500 (avatar overlaps bottom-left, keep content right)
xh=svg(1500,500,f'<rect width="1500" height="500" fill="url(#bg)"/><rect width="1500" height="500" fill="url(#glow)"/>'+grid(1500,500)+spark(1500,500,420)
       +mark(420,70,0.3)+WORD(740,245,104)+TAG(745,315,26))
# 4. YouTube banner 2560x1440 (safe area 1546x423 centred)
yt=svg(2560,1440,f'<rect width="2560" height="1440" fill="url(#bg)"/><rect width="2560" height="1440" fill="url(#glow)"/>'+grid(2560,1440,100)+spark(2560,1440,1050)
       +mark(715,555,0.33)+WORD(1075,745,130)+TAG(1080,830,32))
# 5. horizontal logo (transparent, for videos/thumbnails)
lockup=svg(1600,400,mark(0,0,0.4)+WORD(400,245,150)+TAG(405,320,30))

import cairosvg
for name,s,sz in [("financehubw-profile",pfp,(1000,1000)),("financehubw-icon",icon,(1000,1000)),
                  ("financehubw-x-header",xh,(1500,500)),("financehubw-youtube-banner",yt,(2560,1440)),
                  ("financehubw-logo-horizontal",lockup,(1600,400))]:
    open(name+".svg","w").write(s)
    cairosvg.svg2png(bytestring=s.encode(),write_to=name+".png",output_width=sz[0],output_height=sz[1])
# circle-crop preview
cairosvg.svg2png(bytestring=svg(1000,1000,f'<clipPath id="c"><circle cx="500" cy="500" r="500"/></clipPath><g clip-path="url(#c)"><rect width="1000" height="1000" fill="url(#bg)"/><rect width="1000" height="1000" fill="url(#glow)"/>'+mark(-15,10,1.0)+'</g>').encode(),write_to="preview-circle.png",output_width=400)
