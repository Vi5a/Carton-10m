"""Image globale de la séance : cible ISSF dessinée + tous les plombs + centre fictif."""

from PIL import Image, ImageDraw, ImageFont

import cible
from cible import R_PLOMB, R_VISUEL, R_X, rayon_zone, fr

PALETTE = [(29, 124, 242), (230, 57, 70), (255, 170, 0), (40, 180, 160),
           (150, 90, 230), (250, 120, 30), (60, 170, 70), (235, 90, 150),
           (120, 120, 120), (0, 150, 210)]

PAPIER = (246, 244, 238)
NOIR = (22, 22, 22)


def couleur(i):
    return PALETTE[i % len(PALETTE)]


# Polices prioritaires (chemins complets), utilisées par la version Android
POLICE_NORMALE = None
POLICE_GRAS = None


def police(taille, gras=False):
    prio = POLICE_GRAS if gras else POLICE_NORMALE
    noms = ([prio] if prio else []) + (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if gras
                                       else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for n in noms:
        try:
            return ImageFont.truetype(n, taille)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=taille)
    except TypeError:
        return ImageFont.load_default()


def dessiner_cible(dr, cx, cy, s, demi_mm, epaisseur=2):
    """Cible ISSF à l'échelle s (px/mm), centrée en (cx, cy)."""
    def cercle(r_mm, **kw):
        r = r_mm * s
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)

    cercle(rayon_zone(1), fill=(255, 255, 255), outline=NOIR, width=epaisseur)
    for n in range(2, 7):
        cercle(rayon_zone(n), outline=NOIR, width=epaisseur)
    cercle(R_VISUEL, fill=NOIR)
    for n in range(8, 11):
        cercle(rayon_zone(n), outline=(255, 255, 255), width=epaisseur)
    cercle(R_X, outline=(255, 255, 255), width=max(1, epaisseur // 2))

    f = police(max(10, int(3.2 * s)), gras=True)
    for n in range(1, 9):
        rm = (rayon_zone(n) + rayon_zone(n + 1)) / 2
        if rm > demi_mm - 2:
            continue
        coul = NOIR if n <= 6 else (235, 235, 235)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            dr.text((cx + dx * rm * s, cy + dy * rm * s), str(n), fill=coul, font=f, anchor="mm")


def image_seance(groupes, titre="", taille=1000, superech=2):
    """groupes : liste de (nom_carton, [(x, y), ...], [ignoré ?, ...]) ; renvoie une image PIL RGB.
    Les impacts ignorés comptent dans le score mais pas dans le centre fictif."""
    groupes = [(g[0], g[1], g[2] if len(g) > 2 else [False] * len(g[1])) for g in groupes]
    tous = [t for _, ts, _ in groupes for t in ts]
    b = cible.bilan(tous, [ig for _, _, igs in groupes for ig in igs])

    # zoom automatique : montrer tous les plombs, au moins le visuel noir
    etendue = max([abs(c) for t in tous for c in t] + [0.0]) + R_PLOMB + 5
    demi_mm = min(max(etendue, R_VISUEL + 6), rayon_zone(1) + 4)

    S = superech
    L = taille * S
    s = L / (2 * demi_mm)
    hauteur_texte = (282 if b and b["n_ignores"] else 250) * S
    img = Image.new("RGB", (L, L), PAPIER)
    dr = ImageDraw.Draw(img)
    cx = cy = L / 2
    dessiner_cible(dr, cx, cy, s, demi_mm, epaisseur=max(2, int(0.25 * s)))

    # plombs (semi-transparents)
    calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(calque)
    rp = R_PLOMB * s
    for i, (_, ts, igs) in enumerate(groupes):
        r_, g_, b_ = couleur(i)
        for (x, y), ig in zip(ts, igs):
            px, py = cx + x * s, cy + y * s
            if ig:
                # impact ignoré dans l'analyse : contour en pointillés de sa couleur, barré
                dc.ellipse([px - rp, py - rp, px + rp, py + rp], fill=(150, 150, 150, 90))
                lw = max(2, int(0.22 * s))
                for k in range(0, 360, 30):
                    dc.arc([px - rp, py - rp, px + rp, py + rp], k, k + 18, fill=(r_, g_, b_, 255), width=lw)
                e = rp * 0.55
                dc.line([px - e, py - e, px + e, py + e], fill=(r_, g_, b_, 255), width=lw)
                dc.line([px - e, py + e, px + e, py - e], fill=(r_, g_, b_, 255), width=lw)
            else:
                dc.ellipse([px - rp, py - rp, px + rp, py + rp], fill=(r_, g_, b_, 175),
                           outline=(255, 255, 255, 230), width=max(2, int(0.12 * s)))
    img = Image.alpha_composite(img.convert("RGBA"), calque).convert("RGB")
    dr = ImageDraw.Draw(img)

    if b:
        # centre fictif
        mx, my = cx + b["centre_x"] * s, cy + b["centre_y"] * s
        rouge = (220, 20, 30)
        lw = max(3, int(0.3 * s))
        dr.line([cx, cy, mx, my], fill=rouge, width=max(2, lw // 2))
        bras = 3.5 * s
        for dx, dy in ((1, 0), (0, 1)):
            dr.line([mx - dx * bras, my - dy * bras, mx + dx * bras, my + dy * bras],
                    fill=(255, 255, 255), width=lw + 4 * S)
            dr.line([mx - dx * bras, my - dy * bras, mx + dx * bras, my + dy * bras],
                    fill=rouge, width=lw)
        r_moy = b["rayon_moyen"] * s
        dr.ellipse([mx - r_moy, my - r_moy, mx + r_moy, my + r_moy], outline=rouge, width=max(2, lw // 2))

    # bandeau de texte sous la cible
    fond = Image.new("RGB", (L, L + hauteur_texte), PAPIER)
    fond.paste(img, (0, 0))
    img = fond
    dr = ImageDraw.Draw(img)
    y0 = L + 18 * S
    x0 = 30 * S
    f_titre, f_txt = police(30 * S, gras=True), police(22 * S)
    dr.line([0, L, L, L], fill=(200, 200, 200), width=2 * S)
    dr.text((x0, y0), titre or "Séance", fill=NOIR, font=f_titre)
    y = y0 + 46 * S
    if b:
        lignes = [
            f"{b['n']} plombs   •   Score : {b['entier']}   •   Décimal : {fr(b['dixieme'])}"
            f"   •   Mouches : {b['mouches']}",
            f"Moyenne par plomb : {fr(b['entier'] / b['n'], 2)}  /  {fr(b['dixieme'] / b['n'], 2)}",
            f"Centre fictif (croix rouge) : {cible.decrire_decalage(b['centre_x'], b['centre_y'])}"
            f"   →   {fr(cible.valeur_dixieme(b['centre_d']))}",
            f"Si recentré : {b['entier_centre']}  /  {fr(b['dixieme_centre'])}"
            f"   •   Rayon moyen : {fr(b['rayon_moyen'])} mm   •   Groupement : {fr(b['groupement'])} mm",
        ]
        if b["n_ignores"]:
            pl = "s" if b["n_ignores"] > 1 else ""
            lignes.append(f"Analyse sur {b['n_analyse']} impacts : {b['n_ignores']} impact{pl} ignoré{pl} "
                          f"(barré{pl}), compté{pl} dans le score")
    else:
        lignes = ["Aucun plomb."]
    for l in lignes:
        dr.text((x0, y), l, fill=(40, 40, 40), font=f_txt)
        y += 32 * S

    # légende des cartons
    if len(groupes) > 1:
        f_leg = police(17 * S)
        lx = x0
        y += 8 * S
        for i, (nom, ts, _) in enumerate(groupes):
            etiquette = f"{nom[:18]} ({len(ts)})"
            w = dr.textlength(etiquette, font=f_leg) + 40 * S
            if lx + w > L - x0:
                lx = x0
                y += 26 * S
            if y > L + hauteur_texte - 24 * S:
                break
            dr.rectangle([lx, y + 3 * S, lx + 16 * S, y + 19 * S], fill=couleur(i))
            dr.text((lx + 22 * S, y), etiquette, fill=(60, 60, 60), font=f_leg)
            lx += w

    if S > 1:
        img = img.resize((img.width // S, img.height // S), Image.LANCZOS)
    # correspondance mm -> pixels de l'image finale (pour cliquer sur les impacts)
    img.cadrage = (cx / S, cy / S, s / S, L / S)
    return img
