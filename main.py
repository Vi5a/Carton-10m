"""Analyse de cartons – Pistolet 10 m : version Android (Kivy).

Les photos sont prises dans la galerie (aucun accès à l'appareil photo).
Sur ordinateur, `python main.py` lance la même interface pour les essais.
"""
import csv
import datetime
import io
import math
import os
import threading
import traceback

from kivy.config import Config
from kivy.utils import platform

if platform != "android":
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "860")
    Config.set("input", "mouse", "mouse,multitouch_on_demand")

import cv2                                               # noqa: E402
import numpy as np                                       # noqa: E402
import kivy                                              # noqa: E402
from kivy.app import App                                 # noqa: E402
from kivy.clock import Clock                             # noqa: E402
from kivy.core.text import Label as CoreLabel           # noqa: E402
from kivy.core.window import Window                      # noqa: E402
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle  # noqa: E402
from kivy.graphics.texture import Texture                # noqa: E402
from kivy.metrics import dp, sp                          # noqa: E402
from kivy.uix.boxlayout import BoxLayout                 # noqa: E402
from kivy.uix.button import Button                       # noqa: E402
from kivy.uix.gridlayout import GridLayout               # noqa: E402
from kivy.uix.label import Label                         # noqa: E402
from kivy.uix.modalview import ModalView                 # noqa: E402
from kivy.uix.popup import Popup                         # noqa: E402
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager  # noqa: E402
from kivy.uix.scrollview import ScrollView               # noqa: E402
from kivy.uix.slider import Slider                       # noqa: E402
from kivy.uix.stencilview import StencilView             # noqa: E402
from kivy.uix.textinput import TextInput                 # noqa: E402
from kivy.uix.togglebutton import ToggleButton           # noqa: E402

import android_io                                        # noqa: E402
import cible                                             # noqa: E402
import detection                                         # noqa: E402
import rendu                                             # noqa: E402
from cible import R_PLOMB, fr, rayon_zone                # noqa: E402

_polices = os.path.join(os.path.dirname(kivy.__file__), "data", "fonts")
rendu.POLICE_NORMALE = os.path.join(_polices, "DejaVuSans.ttf")   # contient « → »
rendu.POLICE_GRAS = os.path.join(_polices, "Roboto-Bold.ttf")

# couleurs (r, g, b, a) 0..1
FOND = (0.11, 0.12, 0.13, 1)
BARRE = (0.16, 0.17, 0.19, 1)
BOUTON = (0.24, 0.26, 0.29, 1)
ACCENT = (0.13, 0.45, 0.85, 1)
ROUGE = (0.86, 0.23, 0.2, 1)
TEXTE = (0.93, 0.93, 0.93, 1)
GRIS = (0.62, 0.64, 0.67, 1)
TAILLE_MAX_TEXTURE = 2048


def seuil_depuis_sensibilite(v):
    return 0.55 - 0.05 * float(v)          # 1 -> 0,50 (strict) … 9 -> 0,10 (sensible)


def texture_depuis(arr, bgr=True):
    """Texture Kivy depuis une image numpy (BGR ou RGB)."""
    rgba = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA if bgr else cv2.COLOR_RGB2RGBA)
    h, w = rgba.shape[:2]
    t = Texture.create(size=(w, h), colorfmt="rgba")
    t.blit_buffer(rgba.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    t.flip_vertical()
    return t


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
class Carton:
    def __init__(self, chemin, nom, n_attendu):
        self.chemin = chemin
        self.nom = nom
        self.n_attendu = n_attendu
        self.bgr = detection.lire_image(chemin)
        self.H = self.norm = self.valide = None
        self.tirs = []
        self.ignores = set()
        self.erreur = ""
        self._tex_norm = None
        self._tex_src = None
        self.f_src = 1.0                    # échelle de la texture source

    def calibrer(self, ellipse=None):
        H = detection.calibrer(self.bgr, ellipse)
        self._tex_norm = None
        if H is None:
            self.H = self.norm = self.valide = None
            self.tirs, self.ignores = [], set()
            self.erreur = "Visuel non trouvé"
            return False
        self.H = H
        self.norm, self.valide = detection.redresser(self.bgr, H)
        self.erreur = ""
        return True

    def detecter(self, seuil):
        self.ignores = set()
        if self.norm is None:
            self.tirs = []
            return
        self.tirs = detection.detecter_plombs(self.norm, self.valide, self.n_attendu or None, seuil)
        self.tirs.sort(key=lambda t: math.hypot(*t))

    def texture_norm(self):
        if self._tex_norm is None and self.norm is not None:
            self._tex_norm = texture_depuis(self.norm)
        return self._tex_norm

    def texture_src(self):
        if self._tex_src is None:
            h, w = self.bgr.shape[:2]
            self.f_src = min(1.0, TAILLE_MAX_TEXTURE / max(h, w))
            img = self.bgr if self.f_src >= 1 else cv2.resize(self.bgr, None, fx=self.f_src, fy=self.f_src,
                                                              interpolation=cv2.INTER_AREA)
            self._tex_src = texture_depuis(img)
        return self._tex_src

    def drapeaux(self):
        return [t in self.ignores for t in self.tirs]

    def bilan(self):
        return cible.bilan(self.tirs, self.drapeaux())


# ---------------------------------------------------------------------------
# Visionneuse tactile : un doigt = toucher / glisser, deux doigts = zoom
# ---------------------------------------------------------------------------
class VueImage(StencilView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.texture = None
        self.taille = (1, 1)
        self.cadre = None
        self.s, self.tx, self.ty = 1.0, 0.0, 0.0
        self.auto = True
        self.message = ""
        self.calque = None
        self.sur_tap = self.sur_prise = self.sur_glisse = self.sur_lache = None
        self._touches = {}
        self._mode = None
        with self.canvas:
            Color(*FOND)
            self._fond = Rectangle()
            Color(1, 1, 1, 1)
            self._rect = Rectangle()
        self.groupe = InstructionGroup()
        self.canvas.add(self.groupe)
        self.bind(pos=self._taille_changee, size=self._taille_changee)

    # -- vue --
    def _taille_changee(self, *_):
        self._fond.pos, self._fond.size = self.pos, self.size
        if self.auto:
            self.ajuster()
        else:
            self.redessiner()

    def definir_image(self, texture, garder_vue=False):
        meme = self.texture is not None and texture is not None and self.taille == tuple(texture.size)
        self.texture = texture
        self._rect.texture = texture
        if texture is not None:
            self.taille = tuple(texture.size)
        if garder_vue and meme and not self.auto:
            self.redessiner()
        else:
            self.ajuster()

    def ajuster(self, *_):
        self.auto = True
        if self.texture is not None and self.width > 2 and self.height > 2:
            x0, y0, x1, y1 = self.cadre or (0, 0, *self.taille)
            self.s = min(self.width / (x1 - x0), self.height / (y1 - y0)) * 0.98
            self.tx = (self.width - (x0 + x1) * self.s) / 2
            self.ty = (self.height - (y0 + y1) * self.s) / 2
        self.redessiner()

    def vers_ecran(self, x, y):
        return self.x + self.tx + x * self.s, self.top - (self.ty + y * self.s)

    def vers_image(self, X, Y):
        return (X - self.x - self.tx) / self.s, (self.top - Y - self.ty) / self.s

    def redessiner(self, *_):
        if self.texture is not None:
            w, h = self.taille
            X0, Y1 = self.vers_ecran(0, 0)
            X1, Y0 = self.vers_ecran(w, h)
            self._rect.pos, self._rect.size = (X0, Y0), (X1 - X0, Y1 - Y0)
        else:
            self._rect.size = (0, 0)
        self.groupe.clear()
        if self.texture is not None and self.calque:
            self.calque(self)
        if self.message:
            self.texte(self.message, self.center_x, self.center_y, TEXTE, taille=sp(15), centre=True)

    def zoom(self, X, Y, f):
        if self.texture is None:
            return
        x, y = self.vers_image(X, Y)
        self.s = min(max(self.s * f, 0.02), 30)
        self.tx = X - self.x - x * self.s
        self.ty = self.top - Y - y * self.s
        self.auto = False
        self.redessiner()

    # -- dessin du calque --
    def cercle(self, X, Y, r, couleur, largeur=1.5, pointilles=False):
        self.groupe.add(Color(*couleur))
        if pointilles:
            self.groupe.add(Line(circle=(X, Y, r), width=1, dash_length=dp(4), dash_offset=dp(3)))
        else:
            self.groupe.add(Line(circle=(X, Y, r), width=largeur))

    def disque(self, X, Y, r, couleur):
        self.groupe.add(Color(*couleur))
        self.groupe.add(Ellipse(pos=(X - r, Y - r), size=(2 * r, 2 * r)))

    def ligne(self, pts, couleur, largeur=1.5):
        self.groupe.add(Color(*couleur))
        self.groupe.add(Line(points=pts, width=largeur))

    _cache_textes = {}

    def texte(self, txt, X, Y, couleur, taille=None, centre=False):
        taille = taille or sp(12)
        cle = (txt, round(taille))
        tex = self._cache_textes.get(cle)
        if tex is None:
            lbl = CoreLabel(text=txt, font_size=taille, bold=True, halign="center")
            lbl.refresh()
            tex = lbl.texture
            if len(self._cache_textes) > 400:
                self._cache_textes.clear()
            self._cache_textes[cle] = tex
        w, h = tex.size
        x, y = (X - w / 2, Y - h / 2) if centre else (X, Y - h / 2)
        self.groupe.add(Color(0, 0, 0, 0.55))
        self.groupe.add(Rectangle(pos=(x - dp(2), y), size=(w + dp(4), h)))
        self.groupe.add(Color(*couleur))
        self.groupe.add(Rectangle(texture=tex, pos=(x, y), size=(w, h)))

    # -- toucher --
    def on_touch_down(self, t):
        if not self.collide_point(*t.pos):
            return False
        if getattr(t, "is_mouse_scrolling", False):
            self.zoom(t.x, t.y, 1.2 if t.button == "scrolldown" else 1 / 1.2)
            return True
        t.grab(self)
        self._touches[t.uid] = t
        t.ud["debut"] = (t.x, t.y)
        if len(self._touches) == 1:
            self._mode = "tap"
            if t.is_double_tap and not (self.sur_prise and self.texture is not None
                                        and self.sur_prise(*self.vers_image(t.x, t.y), essai=True)):
                self._mode = None
                self.ajuster()
                return True
            if self.sur_prise and self.texture is not None and self.sur_prise(*self.vers_image(t.x, t.y)):
                self._mode = "objet"
        else:
            if self._mode == "objet" and self.sur_lache:
                self.sur_lache(None, None)
            self._mode = "pinch"
            self._debut_pinch()
        return True

    def _debut_pinch(self):
        a, b = list(self._touches.values())[:2]
        self._p0 = (math.hypot(a.x - b.x, a.y - b.y) or 1, self.s,
                    self.vers_image((a.x + b.x) / 2, (a.y + b.y) / 2))

    def on_touch_move(self, t):
        if t.grab_current is not self:
            return False
        if self._mode == "pinch" and len(self._touches) >= 2:
            a, b = list(self._touches.values())[:2]
            d0, s0, (ax, ay) = self._p0
            self.s = min(max(s0 * math.hypot(a.x - b.x, a.y - b.y) / d0, 0.02), 30)
            mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
            self.tx = mx - self.x - ax * self.s
            self.ty = self.top - my - ay * self.s
            self.auto = False
            self.redessiner()
        elif self._mode == "objet":
            self.sur_glisse(*self.vers_image(t.x, t.y))
        elif self._mode in ("tap", "pan"):
            x0, y0 = t.ud["debut"]
            if self._mode == "pan" or math.hypot(t.x - x0, t.y - y0) > dp(10):
                self._mode = "pan"
                self.tx += t.dx
                self.ty -= t.dy
                self.auto = False
                self.redessiner()
        return True

    def on_touch_up(self, t):
        if t.grab_current is not self:
            return False
        t.ungrab(self)
        self._touches.pop(t.uid, None)
        if self._mode == "tap" and self.sur_tap and self.texture is not None:
            self.sur_tap(*self.vers_image(t.x, t.y))
        elif self._mode == "objet" and self.sur_lache:
            self.sur_lache(*self.vers_image(t.x, t.y))
        if not self._touches:
            self._mode = None
        elif self._mode == "pinch":
            self._mode = "pan"
        return True


# ---------------------------------------------------------------------------
# Petits widgets
# ---------------------------------------------------------------------------
def bouton(texte, rappel=None, couleur=BOUTON, **kw):
    kw.setdefault("font_size", sp(14))
    b = Button(text=texte, background_normal="", background_down="", background_color=couleur,
               color=TEXTE, halign="center", valign="middle", **kw)
    b.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(6), None)))
    if rappel:
        b.bind(on_release=lambda *_: rappel())
    return b


def etiquette(texte="", **kw):
    kw.setdefault("font_size", sp(14))
    kw.setdefault("color", TEXTE)
    lbl = Label(text=texte, markup=True, halign="left", valign="middle", **kw)
    lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
    return lbl


def ligne(*widgets, hauteur=48, espace=6):
    b = BoxLayout(size_hint_y=None, height=dp(hauteur), spacing=dp(espace))
    for w in widgets:
        b.add_widget(w)
    return b


class Compteur(BoxLayout):
    """[−] valeur [+]"""

    def __init__(self, valeur, mini=0, maxi=60, rappel=None, **kw):
        super().__init__(spacing=dp(2), **kw)
        self.valeur, self.mini, self.maxi, self.rappel = valeur, mini, maxi, rappel
        self.add_widget(bouton("−", lambda: self.changer(-1), size_hint_x=None, width=dp(44), font_size=sp(20)))
        self.lbl = Label(text=str(valeur), font_size=sp(17), bold=True, color=TEXTE, size_hint_x=None, width=dp(36))
        self.add_widget(self.lbl)
        self.add_widget(bouton("+", lambda: self.changer(1), size_hint_x=None, width=dp(44), font_size=sp(20)))
        self.size_hint_x = None
        self.width = dp(130)

    def changer(self, d):
        self.definir(self.valeur + d)
        if self.rappel:
            self.rappel(self.valeur)

    def definir(self, v):
        self.valeur = max(self.mini, min(self.maxi, int(v)))
        self.lbl.text = str(self.valeur)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class AnalyseCartonsApp(App):
    title = "Analyse cartons 10 m"

    def build(self):
        Window.clearcolor = FOND
        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self._clavier)
        self.cartons = []
        self.courant = None
        self.sel_carton = None           # index du plomb sélectionné (écran carton)
        self.mode_ajout = False
        self.mode_calib = False
        self.points_calib = []
        self.sel_seance = None           # (carton, index)
        self.historique = []
        self._occupe = False
        self._seance_a_jour = False

        racine = BoxLayout(orientation="vertical")
        self.ecrans = ScreenManager(transition=NoTransition())
        self.ecrans.add_widget(self._ecran_cartons())
        self.ecrans.add_widget(self._ecran_carton())
        self.ecrans.add_widget(self._ecran_seance())
        racine.add_widget(self.ecrans)

        nav = BoxLayout(size_hint_y=None, height=dp(52))
        self.onglets = {}
        for nom, texte in (("cartons", "Cartons"), ("carton", "Carton"), ("seance", "Séance")):
            tb = ToggleButton(text=texte, group="nav", allow_no_selection=False, font_size=sp(15),
                              background_normal="", background_down="", color=TEXTE,
                              background_color=BARRE)
            tb.bind(on_release=lambda w, n=nom: self.aller(n))
            tb.bind(state=lambda w, st: setattr(w, "background_color", ACCENT if st == "down" else BARRE))
            nav.add_widget(tb)
            self.onglets[nom] = tb
        racine.add_widget(nav)
        self.onglets["cartons"].state = "down"
        Clock.schedule_once(lambda dt: self.rafraichir(), 0)
        return racine

    # ------------------------------------------------------------ écrans
    def _ecran_cartons(self):
        e = Screen(name="cartons")
        b = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        self.champ_titre = TextInput(text=f"Séance du {datetime.date.today():%d/%m/%Y}", multiline=False,
                                     size_hint_y=None, height=dp(44), font_size=sp(16),
                                     background_color=(0.2, 0.21, 0.23, 1), foreground_color=TEXTE,
                                     cursor_color=TEXTE, padding=(dp(8), dp(11)))
        self.champ_titre.bind(text=lambda *_: self._invalider_seance())
        b.add_widget(self.champ_titre)
        self.cpt_defaut = Compteur(5, mini=1)
        b.add_widget(ligne(etiquette("Plombs par carton :"), self.cpt_defaut))
        b.add_widget(ligne(bouton("Ajouter des photos (galerie)", self.ajouter_cartons, ACCENT,
                                  font_size=sp(16), bold=True), hauteur=54))
        sv = ScrollView()
        self.grille = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.grille.bind(minimum_height=self.grille.setter("height"))
        sv.add_widget(self.grille)
        b.add_widget(sv)
        self.lbl_total = etiquette("", size_hint_y=None, height=dp(34), font_size=sp(17))
        b.add_widget(self.lbl_total)
        self.curseur = Slider(min=1, max=9, step=1, value=5)
        self.lbl_sens = etiquette("Sensibilité : 5", size_hint_x=None, width=dp(118))
        self.curseur.bind(value=lambda w, v: setattr(self.lbl_sens, "text", f"Sensibilité : {int(v)}"))
        b.add_widget(ligne(self.lbl_sens, self.curseur))
        b.add_widget(ligne(bouton("Redétecter tout", self.redetecter_tout),
                           bouton("Image séance", self.exporter_image),
                           bouton("CSV", self.exporter_csv, size_hint_x=0.6)))
        e.add_widget(b)
        return e

    def _ecran_carton(self):
        e = Screen(name="carton")
        b = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(5))
        self.lbl_carton = etiquette("", font_size=sp(14))
        b.add_widget(ligne(bouton("<", lambda: self.changer_carton(-1), size_hint_x=None, width=dp(44)),
                           self.lbl_carton,
                           bouton(">", lambda: self.changer_carton(1), size_hint_x=None, width=dp(44)),
                           hauteur=44))
        self.vue_carton = VueImage()
        self.vue_carton.calque = self._calque_carton
        self.vue_carton.sur_tap = self._tap_carton
        self.vue_carton.sur_prise = self._prise_carton
        self.vue_carton.sur_glisse = self._glisse_carton
        self.vue_carton.sur_lache = self._lache_carton
        b.add_widget(self.vue_carton)
        self.lbl_info_carton = etiquette("", font_size=sp(13), size_hint_y=None, height=dp(40), color=GRIS)
        b.add_widget(self.lbl_info_carton)

        self.btn_ajout = ToggleButton(text="+ Ajouter", font_size=sp(14), background_normal="",
                                      background_down="", color=TEXTE, background_color=BOUTON)
        self.btn_ajout.bind(state=self._bascule_ajout)
        self.btn_suppr_carton = bouton("Supprimer", self.supprimer_plomb, ROUGE)
        self.barre_edition = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(102), spacing=dp(6))
        self.barre_edition.add_widget(ligne(self.btn_ajout, self.btn_suppr_carton,
                                            bouton("Annuler", self.annuler)))
        self.cpt_carton = Compteur(5, rappel=self.appliquer_nombre)
        self.barre_edition.add_widget(ligne(self.cpt_carton, bouton("Redétecter", self.redetecter),
                                            bouton("Calibrer", self.debut_calibration),
                                            bouton("Retirer", self.retirer_carton, size_hint_x=0.8)))
        self.barre_calib = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(102), spacing=dp(6))
        self.barre_calib.add_widget(etiquette("[b]Calibration[/b] : touchez 6 à 10 points sur le BORD du "
                                              "visuel noir (3 minimum).", font_size=sp(13),
                                              size_hint_y=None, height=dp(48), color=(1, 0.75, 0.3, 1)))
        self.barre_calib.add_widget(ligne(bouton("Retirer le point", self.retirer_point_calib),
                                          bouton("Abandonner", self.fin_calibration),
                                          bouton("Valider", self.valider_calibration, ACCENT)))
        self.zone_barres = BoxLayout(size_hint_y=None, height=dp(102))
        self.zone_barres.add_widget(self.barre_edition)
        b.add_widget(self.zone_barres)
        e.add_widget(b)
        return e

    def _ecran_seance(self):
        e = Screen(name="seance")
        b = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(5))
        self.vue_seance = VueImage()
        self.vue_seance.calque = self._calque_seance
        self.vue_seance.sur_tap = self._tap_seance
        b.add_widget(self.vue_seance)
        self.lbl_impact = etiquette("", font_size=sp(13), size_hint_y=None, height=dp(44))
        b.add_widget(self.lbl_impact)
        self.btn_ignorer = bouton("Ignorer dans l'analyse", self.basculer_ignore, ACCENT)
        self.btn_voir = bouton("Voir carton", self.voir_impact, size_hint_x=0.7)
        b.add_widget(ligne(self.btn_ignorer, self.btn_voir, bouton("Annuler", self.annuler, size_hint_x=0.7)))
        b.add_widget(ligne(bouton("Exporter l'image", self.exporter_image),
                           bouton("Exporter CSV", self.exporter_csv)))
        e.add_widget(b)
        return e

    # ------------------------------------------------------------ navigation
    def aller(self, nom):
        if self.mode_calib and nom != "carton":
            self.fin_calibration()
        self.ecrans.current = nom
        for n, tb in self.onglets.items():
            tb.state = "down" if n == nom else "normal"
        if nom == "seance" and not self._seance_a_jour:
            self._afficher_seance()
        if nom == "carton":
            self._afficher_carton()
        if nom == "cartons":
            self.rafraichir()

    def _clavier(self, fenetre, touche, *args):
        if touche == 27:                       # bouton « retour » d'Android
            if self.mode_calib:
                self.fin_calibration()
                return True
            if self.ecrans.current != "cartons":
                self.aller("cartons")
                return True
        return False

    def on_pause(self):
        return True                            # indispensable : la galerie met l'appli en pause

    def on_resume(self):
        pass

    # ------------------------------------------------------------ messages / tâches
    def message(self, texte, titre="Analyse cartons", partage=None):
        boite = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        boite.add_widget(etiquette(texte, font_size=sp(15)))
        pop = Popup(title=titre, content=boite, size_hint=(0.9, None), height=dp(280))
        boutons = []
        if partage:
            boutons.append(bouton("Partager", lambda: (pop.dismiss(), partage()), ACCENT))
        boutons.append(bouton("OK", pop.dismiss))
        boite.add_widget(ligne(*boutons))
        pop.open()

    def en_tache(self, travail, fin, texte="Analyse…"):
        """Exécute travail(progres) dans un fil, puis fin(resultat) sur le fil Kivy."""
        if self._occupe:
            return
        self._occupe = True
        attente = ModalView(auto_dismiss=False, size_hint=(0.8, None), height=dp(140),
                            background_color=(0, 0, 0, 0.6))
        lbl = Label(text=texte, font_size=sp(16), color=TEXTE, halign="center")
        attente.add_widget(lbl)
        attente.open()

        def progres(t):
            Clock.schedule_once(lambda dt: setattr(lbl, "text", t))

        def executer():
            try:
                res, err = travail(progres), None
            except Exception as ex:
                traceback.print_exc()
                res, err = None, ex

            def terminer(dt):
                attente.dismiss()
                self._occupe = False
                if err is not None:
                    self.message(f"Erreur : {err}")
                else:
                    fin(res)
            Clock.schedule_once(terminer)

        threading.Thread(target=executer, daemon=True).start()

    # ------------------------------------------------------------ cartons
    def ajouter_cartons(self):
        if self._occupe:
            return
        android_io.choisir_images(lambda fichiers: Clock.schedule_once(lambda dt: self._analyser(fichiers)))

    def _analyser(self, fichiers):
        if not fichiers:
            return
        n = self.cpt_defaut.valeur
        seuil = seuil_depuis_sensibilite(self.curseur.value)

        def travail(progres):
            nouveaux, problemes = [], []
            for k, (chemin, nom) in enumerate(fichiers, 1):
                progres(f"Analyse {k}/{len(fichiers)}\n{nom}")
                try:
                    c = Carton(chemin, nom, n)
                except Exception as ex:
                    problemes.append(f"{nom} : {ex}")
                    continue
                if c.calibrer():
                    c.detecter(seuil)
                else:
                    problemes.append(f"{nom} : visuel non trouvé (utilisez « Calibrer »)")
                nouveaux.append(c)
            return nouveaux, problemes

        def fin(res):
            nouveaux, problemes = res
            self.cartons.extend(nouveaux)
            if nouveaux and self.courant is None:
                self.courant = len(self.cartons) - len(nouveaux)
            self.rafraichir()
            if problemes:
                self.message("\n".join(problemes))

        self.en_tache(travail, fin)

    def carton_courant(self):
        if self.courant is None or not (0 <= self.courant < len(self.cartons)):
            return None
        return self.cartons[self.courant]

    def ouvrir_carton(self, i):
        self.courant = i
        self.sel_carton = None
        self.aller("carton")

    def changer_carton(self, d):
        if not self.cartons:
            return
        if self.mode_calib:
            self.fin_calibration()
        self.courant = ((self.courant or 0) + d) % len(self.cartons)
        self.sel_carton = None
        self._afficher_carton()

    def appliquer_nombre(self, n):
        c = self.carton_courant()
        if c:
            c.n_attendu = n
            self.redetecter()

    def redetecter(self):
        c = self.carton_courant()
        if not c or c.norm is None:
            return
        seuil = seuil_depuis_sensibilite(self.curseur.value)
        self._memoriser(c, "redétection")

        def fin(_):
            self.sel_carton = None
            self.rafraichir()
        self.en_tache(lambda p: c.detecter(seuil), fin, "Détection…")

    def redetecter_tout(self):
        if not self.cartons:
            return
        seuil = seuil_depuis_sensibilite(self.curseur.value)
        for c in self.cartons:
            if c.norm is not None:
                self._memoriser(c, "redétection")

        def travail(progres):
            for k, c in enumerate(self.cartons, 1):
                progres(f"Détection {k}/{len(self.cartons)}")
                if c.norm is not None:
                    c.detecter(seuil)
        self.en_tache(travail, lambda _: self.rafraichir(), "Détection…")

    def retirer_carton(self):
        c = self.carton_courant()
        if not c:
            return
        del self.cartons[self.courant]
        self.courant = min(self.courant, len(self.cartons) - 1) if self.cartons else None
        self.sel_carton = None
        self.rafraichir()
        if not self.cartons:
            self.aller("cartons")

    # ------------------------------------------------------------ édition (écran carton)
    @staticmethod
    def _px_mm(x, y):
        return (x - detection.CENTRE) / detection.PPM, (y - detection.CENTRE) / detection.PPM

    def _plomb_proche(self, xm, ym, rayon):
        c = self.carton_courant()
        meilleur, dmin = None, rayon
        for i, (x, y) in enumerate(c.tirs):
            d = math.hypot(x - xm, y - ym)
            if d <= dmin:
                meilleur, dmin = i, d
        return meilleur

    def _tolerance(self):
        # au moins ~1 cm de doigt à l'écran
        return max(R_PLOMB * 1.3, dp(22) / (self.vue_carton.s * detection.PPM))

    def _bascule_ajout(self, w, etat):
        self.mode_ajout = etat == "down"
        w.background_color = ACCENT if self.mode_ajout else BOUTON
        self._maj_info_carton()

    def _prise_carton(self, x, y, essai=False):
        """Un doigt posé sur le plomb sélectionné permet de le déplacer."""
        c = self.carton_courant()
        if not c or self.mode_calib or c.norm is None or self.sel_carton is None:
            return False
        i = self._plomb_proche(*self._px_mm(x, y), self._tolerance())
        if i != self.sel_carton:
            return False
        if not essai:
            self._memoriser(c, "déplacement")
            self._deplace = False
        return True

    def _glisse_carton(self, x, y):
        c = self.carton_courant()
        i = self.sel_carton
        if c and i is not None and i < len(c.tirs):
            ancien = c.tirs[i]
            c.tirs[i] = self._px_mm(x, y)
            if ancien in c.ignores:
                c.ignores.discard(ancien)
                c.ignores.add(c.tirs[i])
            self._deplace = True
            self.vue_carton.redessiner()

    def _lache_carton(self, x, y):
        if not getattr(self, "_deplace", False) and self.historique:
            self.historique.pop()          # simple toucher : rien n'a bougé
        self.rafraichir(garder_vue=True)

    def _tap_carton(self, x, y):
        c = self.carton_courant()
        if not c:
            return
        if self.mode_calib:
            self.points_calib.append((x, y))
            self._maj_info_carton()
            self.vue_carton.redessiner()
            return
        if c.norm is None:
            return
        xm, ym = self._px_mm(x, y)
        if self.mode_ajout:
            self._memoriser(c, "ajout")
            c.tirs.append((xm, ym))
            self.sel_carton = len(c.tirs) - 1
            self.btn_ajout.state = "normal"
            self.rafraichir(garder_vue=True)
            return
        self.sel_carton = self._plomb_proche(xm, ym, self._tolerance())
        self._maj_info_carton()
        self.vue_carton.redessiner()

    def supprimer_plomb(self):
        c = self.carton_courant()
        i = self.sel_carton
        if not c or i is None or i >= len(c.tirs):
            return
        self._memoriser(c, "suppression")
        c.ignores.discard(c.tirs[i])
        del c.tirs[i]
        self.sel_carton = None
        self.rafraichir(garder_vue=True)

    # -- calibration manuelle --
    def debut_calibration(self):
        c = self.carton_courant()
        if not c:
            return
        self.mode_calib = True
        self.points_calib = []
        self.btn_ajout.state = "normal"
        self.zone_barres.clear_widgets()
        self.zone_barres.add_widget(self.barre_calib)
        self._afficher_carton()

    def fin_calibration(self):
        self.mode_calib = False
        self.points_calib = []
        self.zone_barres.clear_widgets()
        self.zone_barres.add_widget(self.barre_edition)
        self._afficher_carton()

    def retirer_point_calib(self):
        if self.points_calib:
            self.points_calib.pop()
            self._maj_info_carton()
            self.vue_carton.redessiner()

    def valider_calibration(self):
        c = self.carton_courant()
        if not c:
            return
        f = c.f_src
        try:
            ell = detection.ellipse_depuis_points([(x / f, y / f) for x, y in self.points_calib])
        except ValueError as ex:
            self.message(str(ex))
            return
        seuil = seuil_depuis_sensibilite(self.curseur.value)
        self._memoriser(c, "calibration")

        def travail(progres):
            if not c.calibrer(ell):
                raise ValueError("calibration impossible avec ces points")
            c.detecter(seuil)

        def fin(_):
            self.sel_carton = None
            self.fin_calibration()
            self.rafraichir()
        self.en_tache(travail, fin, "Calibration…")

    # ------------------------------------------------------------ affichage carton
    def _calque_carton(self, v):
        c = self.carton_courant()
        if not c:
            return
        if self.mode_calib:
            for x, y in self.points_calib:
                X, Y = v.vers_ecran(x, y)
                v.ligne([X - dp(9), Y, X + dp(9), Y], ROUGE, 1.5)
                v.ligne([X, Y - dp(9), X, Y + dp(9)], ROUGE, 1.5)
            if len(self.points_calib) >= 3:
                try:
                    (ex, ey), (ea, eb), ang = detection.ellipse_depuis_points(self.points_calib)
                    t = math.radians(ang)
                    pts = []
                    for k in range(73):
                        a = 2 * math.pi * k / 72
                        px = ex + ea / 2 * math.cos(a) * math.cos(t) - eb / 2 * math.sin(a) * math.sin(t)
                        py = ey + ea / 2 * math.cos(a) * math.sin(t) + eb / 2 * math.sin(a) * math.cos(t)
                        pts.extend(v.vers_ecran(px, py))
                    v.ligne(pts, (1, 0.8, 0, 1), 1.5)
                except Exception:
                    pass
            return
        if c.norm is None:
            return
        P, C = detection.PPM, detection.CENTRE
        cx, cy = v.vers_ecran(C, C)
        for R in [rayon_zone(n) for n in range(1, 11)] + [cible.R_X]:
            v.cercle(cx, cy, R * P * v.s, (0, 0.78, 1, 0.8), 1)
        rp = R_PLOMB * P * v.s
        for i, (x, y) in enumerate(c.tirs):
            X, Y = v.vers_ecran(C + x * P, C + y * P)
            ignore = (x, y) in c.ignores
            if i == self.sel_carton:
                v.cercle(X, Y, rp + dp(3), (1, 0.84, 0.04, 1), 2.5)
            couleur = (0.7, 0.7, 0.7, 1) if ignore else ROUGE
            v.cercle(X, Y, rp, couleur, 1.6, pointilles=ignore)
            v.disque(X, Y, dp(1.5), couleur)
            texte = f"{i + 1}: {fr(cible.valeur_dixieme(math.hypot(x, y)))}" + (" (ignoré)" if ignore else "")
            v.texte(texte, X + rp + dp(3), Y + rp * 0.7, (1, 0.88, 0.4, 1))

    def _maj_info_carton(self):
        c = self.carton_courant()
        if not c:
            t = "Ajoutez des photos depuis l'écran Cartons."
        elif self.mode_calib:
            t = f"{len(self.points_calib)} point(s) placé(s)."
        elif c.norm is None:
            t = "Visuel non trouvé : touchez « Calibrer »."
        elif self.mode_ajout:
            t = "[color=#ffd60a]Touchez l'emplacement du plomb à ajouter.[/color]"
        elif self.sel_carton is not None and self.sel_carton < len(c.tirs):
            x, y = c.tirs[self.sel_carton]
            d = math.hypot(x, y)
            t = (f"Plomb n° {self.sel_carton + 1} : {cible.valeur_entiere(d)} / "
                 f"{fr(cible.valeur_dixieme(d))}  –  glissez-le pour le déplacer, ou « Supprimer ».")
        else:
            t = "Touchez un plomb pour le sélectionner. Deux doigts : zoom. Double-toucher : vue entière."
        self.lbl_info_carton.text = t
        self.btn_suppr_carton.disabled = self.sel_carton is None

    def _afficher_carton(self, garder_vue=False):
        c = self.carton_courant()
        v = self.vue_carton
        if not c:
            v.message = "Aucun carton"
            v.definir_image(None)
            self.lbl_carton.text = ""
            self._maj_info_carton()
            return
        if self.mode_calib or c.norm is None:
            v.cadre = None
            v.message = ""
            v.definir_image(c.texture_src(), garder_vue=garder_vue and self.mode_calib)
        else:
            v.message = ""
            if not garder_vue:
                P, C = detection.PPM, detection.CENTRE
                m = max([abs(t) for p in c.tirs for t in p] + [0.0]) + R_PLOMB + 6
                m = min(max(m, cible.R_VISUEL + 6), detection.DEMI_COTE_MM) * P
                v.cadre = (C - m, C - m, C + m, C + m)
            v.definir_image(c.texture_norm(), garder_vue=garder_vue)
        b = c.bilan()
        att = f"/{c.n_attendu}" if c.n_attendu else ""
        n = b["n"] if b else 0
        alerte = c.n_attendu and n != c.n_attendu
        coul = "ff6b5e" if alerte else "eeeeee"
        score = f"   [b]{b['entier']} / {fr(b['dixieme'])}[/b]" if b else ""
        self.lbl_carton.text = (f"[b]{self.courant + 1}/{len(self.cartons)}[/b]  {c.nom[:22]}\n"
                                f"[color={coul}]{n}{att} plombs[/color]{score}")
        self.cpt_carton.definir(c.n_attendu)
        self._maj_info_carton()

    # ------------------------------------------------------------ liste + total
    def rafraichir(self, garder_vue=False):
        if self.courant is not None and not (0 <= self.courant < len(self.cartons)):
            self.courant = len(self.cartons) - 1 if self.cartons else None
        self.grille.clear_widgets()
        if not self.cartons:
            self.grille.add_widget(etiquette("[color=#9ea3aa]Aucun carton. Touchez « Ajouter des photos » "
                                             "et choisissez les photos de vos cartons dans la galerie.[/color]",
                                             size_hint_y=None, height=dp(80)))
        for i, c in enumerate(self.cartons):
            b = c.bilan()
            n = len(c.tirs)
            alerte = bool(c.erreur) or (c.n_attendu and n != c.n_attendu)
            coul = "ff6b5e" if alerte else "eeeeee"
            plombs = "visuel ?" if c.erreur else (f"{n}/{c.n_attendu}" if c.n_attendu else str(n))
            score = f"{b['entier']}  /  {fr(b['dixieme'])}" if b else "–"
            btn = bouton(f"[b]{i + 1}.[/b]  {c.nom[:26]}\n[color={coul}]{plombs} plombs[/color]     [b]{score}[/b]",
                         lambda i=i: self.ouvrir_carton(i), size_hint_y=None, height=dp(58),
                         couleur=(0.2, 0.21, 0.23, 1) if i != self.courant else (0.18, 0.3, 0.45, 1))
            btn.markup = True
            btn.halign = "left"
            btn.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(20), None)))
            self.grille.add_widget(btn)
        b = self._bilan_seance()
        self.lbl_total.text = (f"[b]Total : {b['entier']}  /  {fr(b['dixieme'])}[/b]   ({b['n']} plombs)"
                               if b else "")
        if self.ecrans.current == "carton":
            self._afficher_carton(garder_vue=garder_vue)
        self._invalider_seance()

    # ------------------------------------------------------------ séance
    def _groupes(self):
        return [(c.nom, c.tirs, c.drapeaux()) for c in self.cartons if c.tirs]

    def _bilan_seance(self):
        return cible.bilan([t for c in self.cartons for t in c.tirs],
                           [ig for c in self.cartons for ig in c.drapeaux()])

    def _invalider_seance(self):
        self._seance_a_jour = False
        if self.ecrans.current == "seance":
            self._afficher_seance()

    def _afficher_seance(self):
        v = self.vue_seance
        if self.sel_seance and not self._impact_existe(self.sel_seance):
            self.sel_seance = None
        g = self._groupes()
        if not g:
            v.message = "Aucun plomb pour l'instant"
            v.definir_image(None)
            self._cadrage = None
        else:
            v.message = ""
            img = rendu.image_seance(g, self.champ_titre.text, taille=1000)
            ancien = getattr(self, "_cadrage", None)
            self._cadrage = img.cadrage
            v.definir_image(texture_depuis(np.asarray(img), bgr=False), garder_vue=(ancien == img.cadrage))
        self._seance_a_jour = True
        self._maj_barre_seance()

    def _impact_existe(self, sel):
        c, i = sel
        return c in self.cartons and 0 <= i < len(c.tirs)

    def _tap_seance(self, x, y):
        cad = getattr(self, "_cadrage", None)
        sel = None
        if cad and y <= cad[3]:
            cx, cy, s, _ = cad
            xm, ym = (x - cx) / s, (y - cy) / s
            dmin = max(R_PLOMB * 1.3, dp(22) / (self.vue_seance.s * s))
            for c in self.cartons:
                for i, (tx, ty) in enumerate(c.tirs):
                    d = math.hypot(tx - xm, ty - ym)
                    if d <= dmin:
                        sel, dmin = (c, i), d
        self.sel_seance = sel
        self._maj_barre_seance()
        self.vue_seance.redessiner()

    def _calque_seance(self, v):
        sel = self.sel_seance
        cad = getattr(self, "_cadrage", None)
        if not sel or not cad or not self._impact_existe(sel):
            return
        cx, cy, s, _ = cad
        x, y = sel[0].tirs[sel[1]]
        X, Y = v.vers_ecran(cx + x * s, cy + y * s)
        r = R_PLOMB * s * v.s + dp(4)
        v.cercle(X, Y, r + dp(1.5), (0, 0, 0, 1), 3)
        v.cercle(X, Y, r, (1, 0.84, 0.04, 1), 2.2)

    def _maj_barre_seance(self):
        sel = self.sel_seance
        if sel and self._impact_existe(sel):
            c, i = sel
            x, y = c.tirs[i]
            d = math.hypot(x, y)
            ignore = (x, y) in c.ignores
            self.lbl_impact.text = (f"[b]{c.nom[:24]}[/b] – n° {i + 1} – {cible.valeur_entiere(d)} / "
                                    f"{fr(cible.valeur_dixieme(d))} ({fr(d)} mm)"
                                    + ("\n[color=#ffb347]IGNORÉ dans l'analyse[/color]" if ignore else ""))
            self.btn_ignorer.text = "Réintégrer dans l'analyse" if ignore else "Ignorer dans l'analyse"
            self.btn_ignorer.disabled = self.btn_voir.disabled = False
        else:
            self.lbl_impact.text = ("[color=#9ea3aa]Touchez un impact pour le sélectionner. "
                                    "Un impact ignoré reste compté dans le score.[/color]")
            self.btn_ignorer.text = "Ignorer dans l'analyse"
            self.btn_ignorer.disabled = self.btn_voir.disabled = True

    def basculer_ignore(self):
        sel = self.sel_seance
        if not sel or not self._impact_existe(sel):
            return
        c, i = sel
        t = c.tirs[i]
        if t in c.ignores:
            self._memoriser(c, "réintégration")
            c.ignores.discard(t)
        else:
            if self._bilan_seance()["n_analyse"] <= 1:
                self.message("Il faut garder au moins un impact dans l'analyse.")
                return
            self._memoriser(c, "impact ignoré")
            c.ignores.add(t)
        self.rafraichir(garder_vue=True)

    def voir_impact(self):
        sel = self.sel_seance
        if sel and self._impact_existe(sel):
            self.courant = self.cartons.index(sel[0])
            self.sel_carton = sel[1]
            self.rafraichir()
            self.aller("carton")

    # ------------------------------------------------------------ annulation
    def _memoriser(self, c, libelle):
        self.historique.append((c, list(c.tirs), set(c.ignores), libelle))
        del self.historique[:-100]

    def annuler(self):
        while self.historique:
            c, tirs, ignores, _ = self.historique.pop()
            if c in self.cartons:
                c.tirs, c.ignores = tirs, ignores
                self.sel_carton = None
                self.rafraichir(garder_vue=True)
                return

    # ------------------------------------------------------------ exports
    def _nom_fichier(self, ext):
        base = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in self.champ_titre.text).strip()
        horo = datetime.datetime.now().strftime("%H%M%S")
        return f"{(base.replace(' ', '_') or 'seance')}_{horo}.{ext}"

    def exporter_image(self):
        g = self._groupes()
        if not g:
            self.message("Aucun plomb à exporter.")
            return
        tampon = io.BytesIO()
        rendu.image_seance(g, self.champ_titre.text, taille=1400).save(tampon, format="PNG")
        self._enregistrer(tampon.getvalue(), self._nom_fichier("png"), "image/png")

    def exporter_csv(self):
        if not any(c.tirs for c in self.cartons):
            self.message("Aucun plomb à exporter.")
            return
        tampon = io.StringIO()
        w = csv.writer(tampon, delimiter=";")
        w.writerow(["Carton", "N°", "X (mm, + = droite)", "Y (mm, + = haut)", "Distance (mm)",
                    "Points", "Décimal", "Mouche", "Ignoré dans l'analyse"])
        for c in self.cartons:
            for i, (x, y) in enumerate(c.tirs, 1):
                d = math.hypot(x, y)
                w.writerow([c.nom, i, fr(x, 2), fr(-y, 2), fr(d, 2), cible.valeur_entiere(d),
                            fr(cible.valeur_dixieme(d)), "X" if cible.est_mouche(d) else "",
                            "oui" if (x, y) in c.ignores else ""])
        b = self._bilan_seance()
        w.writerow([])
        w.writerow(["Total", b["n"], "", "", "", b["entier"], fr(b["dixieme"]), b["mouches"]])
        w.writerow([f"Centre fictif ({b['n_analyse']} impacts analysés)", "", fr(b["centre_x"], 2),
                    fr(-b["centre_y"], 2), fr(b["centre_d"], 2), cible.valeur_entiere(b["centre_d"]),
                    fr(cible.valeur_dixieme(b["centre_d"]))])
        w.writerow(["Score si recentré", "", "", "", "", b["entier_centre"], fr(b["dixieme_centre"])])
        data = ("﻿" + tampon.getvalue()).encode("utf-8")
        self._enregistrer(data, self._nom_fichier("csv"), "text/csv")

    def _enregistrer(self, data, nom, mime):
        try:
            uri, lieu = android_io.enregistrer(data, nom, mime)
        except Exception as ex:
            traceback.print_exc()
            self.message(f"Enregistrement impossible : {ex}")
            return
        partage = (lambda: android_io.partager(uri, mime)) if uri is not None else None
        self.message(f"Enregistré :\n{lieu}", partage=partage)


if __name__ == "__main__":
    AnalyseCartonsApp().run()
