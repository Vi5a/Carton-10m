"""Traitement d'image : repérage du visuel noir, redressement, détection des plombs."""
import math

import cv2
import numpy as np

from cible import R_VISUEL, R_PLOMB, rayon_zone

PPM = 10.0                         # pixels par mm de l'image redressée
DEMI_COTE_MM = 82.0                # l'image redressée couvre ±82 mm (zone 1 = 77,75 mm)
TAILLE = int(round(2 * DEMI_COTE_MM * PPM))
CENTRE = TAILLE / 2.0
TAILLE_MAX_SOURCE = 3000           # les photos plus grandes sont réduites


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def lire_image(chemin):
    """Lit une image (chemins avec accents acceptés sous Windows)."""
    data = np.fromfile(chemin, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)   # applique l'orientation EXIF
    if img is None:
        raise ValueError(f"Image illisible : {chemin}")
    h, w = img.shape[:2]
    if max(h, w) > TAILLE_MAX_SOURCE:
        f = TAILLE_MAX_SOURCE / max(h, w)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return img


# ---------------------------------------------------------------------------
# Repérage du visuel noir (ellipse dans la photo)
# ---------------------------------------------------------------------------
def _affiner_ellipse(points, ellipse, iterations=3, tol=0.03):
    """Réajuste l'ellipse en écartant les points trop éloignés (chiffres collés,
    encoches dues aux plombs sur le bord)."""
    pts = points.reshape(-1, 2).astype(np.float32)
    for _ in range(iterations):
        (cx, cy), (w, h), ang = ellipse
        t = math.radians(ang)
        u = np.array([math.cos(t), math.sin(t)])
        v = np.array([-math.sin(t), math.cos(t)])
        p = pts - np.array([cx, cy])
        rho = np.hypot((p @ u) / (w / 2), (p @ v) / (h / 2))
        garde = pts[np.abs(rho - 1) < tol]
        if len(garde) < 20:
            break
        ellipse = cv2.fitEllipse(garde)
    return ellipse


def trouver_visuel(img):
    """Renvoie l'ellipse ((cx, cy), (largeur, hauteur), angle) du visuel noir
    dans l'image source, ou None si introuvable."""
    h0, w0 = img.shape[:2]
    f = min(1.0, 1600.0 / max(h0, w0))
    petit = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else img
    g = cv2.cvtColor(petit, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    seuil, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    H, W = g.shape
    meilleur, meilleure_aire = None, 0
    for c in contours:
        aire = cv2.contourArea(c)
        if aire < 0.002 * H * W or len(c) < 20:
            continue
        x, y, bw_, bh_ = cv2.boundingRect(c)
        if x <= 1 or y <= 1 or x + bw_ >= W - 1 or y + bh_ >= H - 1:
            continue
        coque = cv2.convexHull(c)
        try:
            ell = cv2.fitEllipse(coque)
        except cv2.error:
            continue
        (ex, ey), (ea, eb), _ = ell
        if min(ea, eb) < 1 or min(ea, eb) / max(ea, eb) < 0.5:
            continue
        aire_ell = math.pi * ea * eb / 4
        if not (0.85 < aire / aire_ell < 1.08):
            continue
        if not (0.9 < cv2.contourArea(coque) / aire_ell < 1.08):
            continue
        # doit être plein et sombre à l'intérieur (écarte les lignes des zones)
        masque = np.zeros_like(g)
        cv2.ellipse(masque, ((ex, ey), (ea * 0.9, eb * 0.9), ell[2]), 255, -1)
        if cv2.mean(bw, mask=masque)[0] < 0.85 * 255:
            continue
        if aire > meilleure_aire:
            meilleur, meilleure_aire = (c, coque, ell), aire

    if meilleur is None:
        return None
    c, coque, ell = meilleur
    ell = _affiner_ellipse(c, ell)
    (ex, ey), (ea, eb), ang = ell
    return ((ex / f, ey / f), (ea / f, eb / f), ang)


def ellipse_depuis_points(points):
    """Ellipse (ou cercle) passant au mieux par des points cliqués sur le bord du visuel."""
    pts = np.array(points, dtype=np.float32)
    if len(pts) >= 5:
        return cv2.fitEllipse(pts)
    if len(pts) < 3:
        raise ValueError("Il faut au moins 3 points sur le bord du visuel.")
    # cercle par moindres carrés : x² + y² + Dx + Ey + F = 0
    A = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    b = -(pts[:, 0] ** 2 + pts[:, 1] ** 2)
    D, E, F = np.linalg.lstsq(A, b, rcond=None)[0]
    cx, cy = -D / 2, -E / 2
    r = math.sqrt(max(cx * cx + cy * cy - F, 1e-6))
    return ((cx, cy), (2 * r, 2 * r), 0.0)


# ---------------------------------------------------------------------------
# Redressement : l'ellipse du visuel devient un cercle de 59,5 mm, centre au milieu
# ---------------------------------------------------------------------------
def matrice_redressement(ellipse):
    """Matrice 3x3 (affine) : photo -> image redressée, à partir de l'ellipse du visuel."""
    (ex, ey), (ea, eb), ang = ellipse
    t = math.radians(ang)
    u = np.array([[math.cos(t)], [math.sin(t)]])
    v = np.array([[-math.sin(t)], [math.cos(t)]])
    r = R_VISUEL * PPM
    A = r * (u @ u.T / (ea / 2) + v @ v.T / (eb / 2))
    t_ = np.array([[CENTRE], [CENTRE]]) - A @ np.array([[ex], [ey]])
    return np.vstack([np.hstack([A, t_]), [0, 0, 1]])


def redresser(img, H):
    """Renvoie (image redressée BGR, masque des pixels valides)."""
    norm = cv2.warpPerspective(img, H, (TAILLE, TAILLE), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    un = np.full(img.shape[:2], 255, np.uint8)
    valide = cv2.warpPerspective(un, H, (TAILLE, TAILLE), flags=cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0
    return norm, valide


# --- Correction de perspective à l'aide des lignes des zones -----------------
# (rayon en mm, type) : 'sombre' = ligne noire sur blanc, 'claire' = ligne blanche
# sur le noir, 'bord' = bord du visuel (noir à l'intérieur, blanc à l'extérieur)
_REPERES = ([(rayon_zone(n), "sombre") for n in range(1, 7)] + [(R_VISUEL, "bord")]
            + [(rayon_zone(n), "claire") for n in range(8, 11)])


def _points_reperes(g, fenetre_mm, n_angles=360):
    """Points des lignes des zones dans l'image redressée : liste (x_mm, y_mm, rayon_attendu)."""
    pas = 0.1
    offs = np.arange(-fenetre_mm, fenetre_mm + pas / 2, pas)
    ang = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
    zone_n = (np.hypot(*np.mgrid[0:TAILLE:8, 0:TAILLE:8] - CENTRE) / PPM < R_VISUEL - 2)
    noir = float(np.median(g[::8, ::8][zone_n]))
    zone_b = np.abs(np.hypot(*np.mgrid[0:TAILLE:8, 0:TAILLE:8] - CENTRE) / PPM - 50) < 10
    blanc = float(np.median(g[::8, ::8][zone_b]))
    C = max(blanc - noir, 40.0)
    sortie = []
    for R, genre in _REPERES:
        r = R + offs[None, :]
        mx = (CENTRE + ca * r * PPM).astype(np.float32)
        my = (CENTRE + sa * r * PPM).astype(np.float32)
        prof = cv2.remap(g, mx, my, cv2.INTER_LINEAR, borderValue=-1).astype(np.float64)
        valide = (prof >= 0).all(axis=1)
        if genre == "bord":
            sig = np.gradient(prof, axis=1)
            seuil = 0.25 * C / (0.6 / pas)
        else:
            sig = (np.median(prof, axis=1, keepdims=True) - prof) if genre == "sombre" \
                else (prof - np.median(prof, axis=1, keepdims=True))
            seuil = 0.25 * C
        i = np.argmax(sig, axis=1)
        ok = valide & (sig[np.arange(n_angles), i] > seuil) & (i > 0) & (i < len(offs) - 1)
        for a in np.nonzero(ok)[0]:
            j = i[a]
            y0, y1, y2 = sig[a, j - 1], sig[a, j], sig[a, j + 1]
            den = y0 - 2 * y1 + y2
            dj = 0.5 * (y0 - y2) / den if abs(den) > 1e-9 else 0.0
            rr = R + offs[j] + max(-0.5, min(0.5, dj)) * pas
            sortie.append((ca[a, 0] * rr, sa[a, 0] * rr, R))
    return np.array(sortie)


def _ajuster_homographie(pts, iterations=25):
    """Homographie G (en mm, centrée) qui ramène les points sur des cercles concentriques."""
    u = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    R = pts[:, 2]

    def residus(p, u, R):
        G = np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1.0]])
        v = u @ G.T
        return np.hypot(v[:, 0] / v[:, 2], v[:, 1] / v[:, 2]) - R

    p = np.zeros(8)
    garde = np.ones(len(u), bool)
    for passe in range(3):
        uu, RR = u[garde], R[garde]
        mu = 1e-3
        for _ in range(iterations):
            r0 = residus(p, uu, RR)
            J = np.empty((len(r0), 8))
            for k in range(8):
                dp = np.zeros(8)
                dp[k] = 1e-7 if k >= 6 else 1e-6
                J[:, k] = (residus(p + dp, uu, RR) - r0) / dp[k]
            A = J.T @ J
            delta = -np.linalg.solve(A + mu * np.diag(np.diag(A)) + 1e-9 * np.eye(8), J.T @ r0)
            r1 = residus(p + delta, uu, RR)
            if (r1 ** 2).sum() < (r0 ** 2).sum():
                p = p + delta
                mu = max(mu / 3, 1e-7)
                if np.abs(delta).max() < 1e-9:
                    break
            else:
                mu *= 5
        r = residus(p, u, R)
        sigma = 1.4826 * np.median(np.abs(r[garde])) + 0.02
        garde = np.abs(r) < 3 * sigma
    G = np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1.0]])
    return G, float(np.sqrt(np.mean(residus(p, u[garde], R[garde]) ** 2))), int(garde.sum())


def corriger_perspective(img, H):
    """Affine H (issue de l'ellipse) -> homographie complète grâce aux lignes des zones.
    Renvoie H inchangée si les lignes ne sont pas assez visibles."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 1.0).astype(np.float32)
    T = np.array([[PPM, 0, CENTRE], [0, PPM, CENTRE], [0, 0, 1.0]])
    Ti = np.linalg.inv(T)
    for fenetre in (3.0, 1.5, 1.0):
        norm = cv2.warpPerspective(g, H, (TAILLE, TAILLE), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=-1)
        pts = _points_reperes(norm, fenetre)
        if len(pts) < 300 or len(np.unique(pts[:, 2])) < 3:
            return H
        G, rms, n = _ajuster_homographie(pts)
        if rms > 0.5 or n < 250:
            return H
        H = T @ G @ Ti @ H
        H = H / H[2, 2]
    return H


# ---------------------------------------------------------------------------
# Détection des plombs dans l'image redressée
# ---------------------------------------------------------------------------
def _niveau_local(g, masque_remplir, valeur, operation, taille_mm=12):
    """Estime le niveau local (papier ou noir) en effaçant les petits défauts."""
    tmp = g.copy()
    tmp[masque_remplir] = valeur
    k = 4
    petit = cv2.resize(tmp, (TAILLE // k, TAILLE // k), interpolation=cv2.INTER_AREA)
    d = int(taille_mm * PPM / k) | 1
    noyau = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))
    petit = cv2.morphologyEx(petit, operation, noyau)
    petit = cv2.GaussianBlur(petit, (0, 0), d / 4)
    return cv2.resize(petit, (TAILLE, TAILLE), interpolation=cv2.INTER_LINEAR)


def carte_contraste(norm, valide):
    """Carte où les trous du carton ressortent (≈ 0 sur le carton intact, ≈ 1 sur un trou)."""
    g = cv2.cvtColor(norm, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lab = cv2.cvtColor(norm, cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)

    yy, xx = np.mgrid[0:TAILLE, 0:TAILLE].astype(np.float32)
    r = np.hypot(xx - CENTRE, yy - CENTRE) / PPM
    Rv = R_VISUEL
    zone_noire = (r < Rv - 1.5) & valide
    zone_papier = (r > Rv + 1.5) & (r < rayon_zone(1) - 1) & valide
    noir = float(np.median(g[zone_noire])) if zone_noire.any() else 30.0
    papier = float(np.median(g[zone_papier])) if zone_papier.any() else 220.0
    C = max(papier - noir, 40.0)

    papier_local = _niveau_local(g, r < Rv + 1.5, papier, cv2.MORPH_CLOSE)
    noir_local = _niveau_local(g, r > Rv - 1.5, noir, cv2.MORPH_OPEN)

    dev_noir = (g - noir_local) / C          # trou = plus clair que le noir
    dev_papier = (papier_local - g) / C      # trou = plus foncé que le papier
    dev = np.where(r < Rv, dev_noir, dev_papier)
    bande = np.abs(r - Rv) < 0.6
    dev[bande] = np.minimum(dev_noir, dev_papier)[bande]

    # fond coloré derrière le carton : les trous sont colorés
    chroma_papier = float(np.median(chroma[zone_papier])) if zone_papier.any() else 0.0
    dev = np.maximum(dev, (chroma - chroma_papier - 8) / 25)

    dev[~valide] = 0
    dev[r > rayon_zone(1) + R_PLOMB + 1] = 0
    return dev


def _centres_initiaux(pts, k):
    """Première estimation des centres de k plombs qui se chevauchent dans une tache."""
    m = pts.mean(axis=0)
    if k == 1:
        return [tuple(m)]
    if k == 2:
        # deux disques : l'écart entre centres se déduit de l'allongement de la tache
        cov = np.cov((pts - m).T)
        vals, vecs = np.linalg.eigh(cov)
        s = 2 * math.sqrt(max(vals[1] - vals[0], 0.0))
        axe = vecs[:, 1]
        return [tuple(m + axe * s / 2), tuple(m - axe * s / 2)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, _, centres = cv2.kmeans(pts.astype(np.float32), k, None, crit, 5, cv2.KMEANS_PP_CENTERS)
    return [tuple(c) for c in centres]


class _Tache:
    """Une tache (un ou plusieurs trous qui se touchent) expliquée par k disques de plomb."""

    def __init__(self, masque, x0, y0, rayon):
        self.B = masque
        self.x0, self.y0 = x0, y0
        h, w = masque.shape
        self.yy, self.xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.r2 = rayon * rayon
        ys, xs = np.nonzero(masque)
        self.pts = np.c_[xs, ys].astype(np.float64)
        self.aire = len(xs)
        self._cache = {}

    def _score(self, centres):
        U = np.zeros_like(self.B)
        for cx, cy in centres:
            U |= (self.xx - cx) ** 2 + (self.yy - cy) ** 2 <= self.r2
        # pixels de la tache couverts, moins les disques qui débordent de la tache
        return 2 * np.count_nonzero(U & self.B) - np.count_nonzero(U)

    def ajuster(self, k):
        """(score, [centres]) du meilleur placement de k disques (recherche locale)."""
        if k in self._cache:
            return self._cache[k]
        centres = [list(c) for c in _centres_initiaux(self.pts, k)]
        meilleur = self._score(centres)
        for pas in (4.0, 2.0, 1.0, 0.5):
            for _ in range(30):
                ameliore = False
                for c in centres:
                    for dx, dy in ((pas, 0), (-pas, 0), (0, pas), (0, -pas)):
                        c[0] += dx
                        c[1] += dy
                        s = self._score(centres)
                        if s > meilleur:
                            meilleur, ameliore = s, True
                        else:
                            c[0] -= dx
                            c[1] -= dy
                if not ameliore:
                    break
        res = (meilleur, [(c[0] + self.x0, c[1] + self.y0) for c in centres])
        self._cache[k] = res
        return res


def detecter_plombs(norm, valide, n_attendu=None, seuil=0.30):
    """Liste des impacts [(x_mm, y_mm), ...] (repère : centre cible, y vers le bas).
    n_attendu : nombre de plombs tirés sur le carton (aide à séparer les trous groupés)."""
    dev = cv2.GaussianBlur(carte_contraste(norm, valide), (0, 0), 0.4 * PPM)
    bw = (dev > seuil).astype(np.uint8) * 255
    # supprime les lignes des zones et les chiffres (traits fins), garde les trous de 4,5 mm
    d = int(2.6 * PPM) | 1
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d)))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    nb, etiquettes, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    aire_plomb = math.pi * (R_PLOMB * PPM) ** 2
    ids = [i for i in range(1, nb) if stats[i, cv2.CC_STAT_AREA] >= 0.35 * aire_plomb]
    ids.sort(key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)
    if n_attendu and len(ids) > n_attendu:
        ids = ids[:n_attendu]
    if not ids:
        return []

    # rayon apparent d'un trou, mesuré sur les trous isolés
    aires = np.array([stats[i, cv2.CC_STAT_AREA] for i in ids], float)
    seuls = aires[(aires > 0.6 * aire_plomb) & (aires < 1.4 * aire_plomb)]
    rayon = math.sqrt(np.median(seuls) / math.pi) if len(seuls) else R_PLOMB * PPM

    marge = int(rayon) + 4
    taches = []
    for i in ids:
        x, y, w, h = stats[i, :4]
        x0, y0 = max(x - marge, 0), max(y - marge, 0)
        x1, y1 = min(x + w + marge, TAILLE), min(y + h + marge, TAILLE)
        taches.append(_Tache(etiquettes[y0:y1, x0:x1] == i, x0, y0, rayon))

    # répartition des plombs : on ajoute un plomb là où il explique le mieux la forme
    k = [1] * len(taches)
    aire_disque = math.pi * rayon * rayon
    while True:
        if n_attendu and sum(k) >= n_attendu:
            break
        if sum(k) > 60:
            break
        gains = [t.ajuster(ki + 1)[0] - t.ajuster(ki)[0] for t, ki in zip(taches, k)]
        j = int(np.argmax(gains))
        # sans nombre imposé, il faut un vrai morceau de trou inexpliqué ; avec un nombre
        # imposé on accepte moins, mais jamais un plomb « fantôme » sur un trou déjà expliqué
        if gains[j] < (0.1 if n_attendu else 0.4) * aire_disque:
            break
        k[j] += 1

    tirs = []
    for t, ki in zip(taches, k):
        for cx, cy in t.ajuster(ki)[1]:
            tirs.append(((cx - CENTRE) / PPM, (cy - CENTRE) / PPM))
    return tirs


def calibrer(img, ellipse=None, perspective=True):
    """Matrice photo -> image redressée. ellipse=None : repérage automatique du visuel.
    Renvoie None si le visuel n'est pas trouvé."""
    if ellipse is None:
        ellipse = trouver_visuel(img)
        if ellipse is None:
            return None
    H = matrice_redressement(ellipse)
    if perspective:
        H = corriger_perspective(img, H)
    return corriger_rotation(img, H)


def corriger_rotation(img, H):
    """Remet le carton droit grâce aux chiffres des zones, imprimés sur les 4 axes.
    (Rotation résiduelle limitée à ±45° : la photo doit être à peu près à l'endroit.)"""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    norm = cv2.warpPerspective(g, H, (TAILLE, TAILLE), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255).astype(np.float32)
    pas_deg = 0.25
    ang = np.deg2rad(np.arange(0, 360, pas_deg))
    profil = np.zeros(len(ang))
    for n in range(1, 9):
        rm = (rayon_zone(n) + rayon_zone(n + 1)) / 2
        r = rm + np.arange(-2.0, 2.01, 0.25)
        mx = (CENTRE + np.cos(ang)[:, None] * r * PPM).astype(np.float32)
        my = (CENTRE + np.sin(ang)[:, None] * r * PPM).astype(np.float32)
        p = cv2.remap(norm, mx, my, cv2.INTER_LINEAR).astype(np.float64)
        fond = np.median(p)
        encre = (fond - p) if n <= 6 else (p - fond)   # chiffres noirs / chiffres blancs
        profil += np.clip(encre, 0, None).mean(axis=1)
    k = int(round(90 / pas_deg))
    plie = profil.reshape(4, k).sum(axis=0)
    plie = np.convolve(np.r_[plie[-8:], plie, plie[:8]], np.ones(5) / 5, "same")[8:-8]
    if plie.max() < 3 * np.median(plie) + 1e-6:
        return H                                       # pas de chiffres nets : on ne touche à rien
    phi = np.argmax(plie) * pas_deg
    if phi > 45:
        phi -= 90
    t = math.radians(-phi)
    Rt = np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1.0]])
    T = np.array([[1, 0, CENTRE], [0, 1, CENTRE], [0, 0, 1.0]])
    H = T @ Rt @ np.linalg.inv(T) @ H
    return H / H[2, 2]
