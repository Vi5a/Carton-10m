"""Géométrie et règles de comptage de la cible ISSF 10 m pistolet.

Toutes les distances sont en millimètres.
Repère interne : origine au centre de la cible, x vers la droite, y vers le BAS
(même sens que les images). Pour l'affichage, « haut » correspond à y < 0.
"""
import math

# --- Dimensions officielles ISSF (cible pistolet 10 m) ---------------------
DIAM_PLOMB = 4.5
R_PLOMB = DIAM_PLOMB / 2          # 2,25 mm (calibre 4,5)
DIAM_10 = 11.5                    # diamètre du 10
PAS = 8.0                         # écart de rayon entre deux zones (16 mm en diamètre)
DIAM_X = 5.0                      # 10 intérieur (mouche)
DIAM_VISUEL = 59.5                # visuel noir = zones 7 à 10
R_VISUEL = DIAM_VISUEL / 2
R_X = DIAM_X / 2


def rayon_zone(n):
    """Rayon extérieur de la zone n (1..10), en mm."""
    return DIAM_10 / 2 + (10 - n) * PAS


def valeur_dixieme(d):
    """Valeur décimale d'un impact dont le CENTRE est à d mm du centre.

    Règle ISSF : le plomb compte la zone dès qu'il touche la ligne, donc le 10
    commence à d = 5,75 + 2,25 = 8,0 mm. Chaque point vaut 8 mm de rayon,
    chaque dixième 0,8 mm. Maximum 10,9 ; en dessous de 1,0 : zéro.
    """
    v = math.floor((11.0 - d / PAS) * 10 + 1e-6) / 10
    if v < 1.0:
        return 0.0
    return round(min(v, 10.9), 1)


def valeur_entiere(d):
    """Valeur entière (1..10, 0 = hors cible)."""
    return int(valeur_dixieme(d))


def est_mouche(d):
    """10 intérieur (X) : le plomb touche le cercle de 5 mm."""
    return d <= R_X + R_PLOMB


def heure_horloge(dx, dy):
    """Direction « horloge » d'un décalage (12 h = en haut)."""
    if math.hypot(dx, dy) < 1e-9:
        return None
    ang = math.degrees(math.atan2(dx, -dy)) % 360
    h = int(round(ang / 30)) % 12
    return 12 if h == 0 else h


def decrire_decalage(dx, dy):
    """Texte lisible : « 2,3 mm à droite, 1,1 mm en haut (2,5 mm, à 2 h) »."""
    d = math.hypot(dx, dy)
    if d < 0.05:
        return "centré"
    morceaux = []
    if abs(dx) >= 0.05:
        morceaux.append(f"{fr(abs(dx))} mm à {'droite' if dx > 0 else 'gauche'}")
    if abs(dy) >= 0.05:
        morceaux.append(f"{fr(abs(dy))} mm {'en bas' if dy > 0 else 'en haut'}")
    return f"{', '.join(morceaux)} ({fr(d)} mm, à {heure_horloge(dx, dy)} h)"


def fr(x, n=1):
    """Nombre formaté à la française."""
    return f"{x:.{n}f}".replace(".", ",")


def bilan(tirs, ignores=None):
    """Statistiques d'une liste d'impacts [(x, y), ...] en mm.

    ignores : liste de booléens parallèle à tirs. Un impact ignoré compte dans le
    score mais pas dans l'analyse (centre fictif, rayon moyen, groupement).
    """
    if not tirs:
        return None
    n = len(tirs)
    ignores = list(ignores) if ignores is not None else [False] * n
    gardes = [t for t, ig in zip(tirs, ignores) if not ig] or list(tirs)
    k = len(gardes)
    ds = [math.hypot(x, y) for x, y in tirs]
    mx = sum(x for x, _ in gardes) / k
    my = sum(y for _, y in gardes) / k
    # score si les organes de visée ramenaient le centre fictif au centre (tous les impacts)
    ds_c = [math.hypot(x - mx, y - my) for x, y in tirs]
    groupement = 0.0
    for i in range(k):
        for j in range(i + 1, k):
            groupement = max(groupement, math.hypot(gardes[i][0] - gardes[j][0],
                                                    gardes[i][1] - gardes[j][1]))
    return {
        "n": n,
        "n_analyse": k,
        "n_ignores": n - k,
        "entier": sum(valeur_entiere(d) for d in ds),
        "dixieme": round(sum(valeur_dixieme(d) for d in ds), 1),
        "mouches": sum(1 for d in ds if est_mouche(d)),
        "centre_x": mx,
        "centre_y": my,
        "centre_d": math.hypot(mx, my),
        "entier_centre": sum(valeur_entiere(d) for d in ds_c),
        "dixieme_centre": round(sum(valeur_dixieme(d) for d in ds_c), 1),
        "rayon_moyen": sum(math.hypot(x - mx, y - my) for x, y in gardes) / k,
        # groupement extérieur (bord à bord des plombs les plus éloignés)
        "groupement": groupement + DIAM_PLOMB,
    }
