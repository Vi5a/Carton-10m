"""Échanges de fichiers avec Android : choix des photos dans la galerie, enregistrement
et partage des résultats. Sur ordinateur (pour les essais), des équivalents simples
sont utilisés.

L'application n'utilise jamais l'appareil photo : elle ne demande aucune permission
et passe par le sélecteur de photos du système (galerie).
"""
import os
import re
import time

from kivy.utils import platform

ANDROID = platform == "android"
CODE_DEMANDE = 4711


def _nom_sur(nom):
    return re.sub(r"[^\w.\-]+", "_", nom)[:80] or "photo.jpg"


# ---------------------------------------------------------------------------
# Android
# ---------------------------------------------------------------------------
if ANDROID:
    from android import activity, mActivity            # noqa: E402  (module p4a)
    from jnius import autoclass, cast                  # noqa: E402

    Intent = autoclass("android.content.Intent")
    Build = autoclass("android.os.Build$VERSION")
    MediaStore = autoclass("android.provider.MediaStore")
    ContentValues = autoclass("android.content.ContentValues")
    Bundle = autoclass("android.os.Bundle")

    def _dossier_cache():
        d = os.path.join(mActivity.getCacheDir().getAbsolutePath(), "cartons")
        os.makedirs(d, exist_ok=True)
        return d

    def _nom_affiche(resolver, uri):
        try:
            curseur = resolver.query(uri, None, None, None, None)
            if curseur is None:
                return None
            try:
                if curseur.moveToFirst():
                    i = curseur.getColumnIndex("_display_name")
                    if i >= 0:
                        return curseur.getString(i)
            finally:
                curseur.close()
        except Exception:
            pass
        return None

    def _copier_uri(uri, i):
        """Copie la photo choisie dans le cache de l'appli et renvoie (chemin, nom)."""
        resolver = mActivity.getContentResolver()
        nom = _nom_affiche(resolver, uri) or f"photo_{i + 1}.jpg"
        pfd = resolver.openFileDescriptor(uri, "r")
        fd = pfd.detachFd()
        with os.fdopen(fd, "rb") as f:
            data = f.read()
        chemin = os.path.join(_dossier_cache(), f"{int(time.time() * 1000)}_{i}_{_nom_sur(nom)}")
        with open(chemin, "wb") as f:
            f.write(data)
        return chemin, nom

    def choisir_images(rappel):
        """Ouvre la galerie (choix multiple). rappel([(chemin, nom), ...]) est appelé
        depuis un fil Android : l'appelant doit repasser sur le fil Kivy (Clock)."""

        def resultat(code, code_res, intent):
            if code != CODE_DEMANDE:
                return
            activity.unbind(on_activity_result=resultat)
            fichiers = []
            try:
                if code_res == -1 and intent is not None:       # RESULT_OK
                    uris = []
                    clip = intent.getClipData()
                    if clip is not None:
                        for k in range(clip.getItemCount()):
                            uris.append(clip.getItemAt(k).getUri())
                    elif intent.getData() is not None:
                        uris.append(intent.getData())
                    for k, u in enumerate(uris):
                        try:
                            fichiers.append(_copier_uri(u, k))
                        except Exception as ex:                  # une photo illisible n'arrête pas les autres
                            print("Copie impossible :", ex)
            finally:
                rappel(fichiers)

        activity.bind(on_activity_result=resultat)
        if Build.SDK_INT >= 33:
            # sélecteur de photos du système (Android 13+) = galerie
            intent = Intent("android.provider.action.PICK_IMAGES")
            try:
                maxi = int(MediaStore.getPickImagesMaxLimit())
            except Exception:
                maxi = 50
            extras = Bundle()        # Bundle : évite l'ambiguïté int/long de putExtra
            extras.putInt("android.provider.extra.PICK_IMAGES_MAX", max(2, min(50, maxi)))
            intent.putExtras(extras)
        else:
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("image/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            extras = Bundle()
            extras.putBoolean(Intent.EXTRA_ALLOW_MULTIPLE, True)
            intent.putExtras(extras)
        mActivity.startActivityForResult(intent, CODE_DEMANDE)

    def enregistrer(data, nom, mime):
        """Enregistre des octets dans Images/AnalyseCartons (PNG) ou Téléchargements/AnalyseCartons
        (CSV). Renvoie (uri ou None, texte décrivant l'emplacement)."""
        if Build.SDK_INT >= 29:
            resolver = mActivity.getContentResolver()
            valeurs = ContentValues()
            valeurs.put("_display_name", nom)
            valeurs.put("mime_type", mime)
            if mime.startswith("image/"):
                valeurs.put("relative_path", "Pictures/AnalyseCartons")
                collection = autoclass("android.provider.MediaStore$Images$Media").EXTERNAL_CONTENT_URI
                lieu = "Images › AnalyseCartons"
            else:
                valeurs.put("relative_path", "Download/AnalyseCartons")
                collection = autoclass("android.provider.MediaStore$Downloads").EXTERNAL_CONTENT_URI
                lieu = "Téléchargements › AnalyseCartons"
            uri = resolver.insert(collection, valeurs)
            pfd = resolver.openFileDescriptor(uri, "w")
            with os.fdopen(pfd.detachFd(), "wb") as f:
                f.write(data)
            return uri, f"{lieu} › {nom}"
        # Android 8 et 9 : dossier de l'application (sans permission)
        d = mActivity.getExternalFilesDir(None).getAbsolutePath()
        chemin = os.path.join(d, nom)
        with open(chemin, "wb") as f:
            f.write(data)
        return None, chemin

    def marges_systeme(hauteur_fenetre):
        """(haut, bas, gauche, droite) en pixels des barres système qui recouvrent
        la fenêtre de l'appli. Zéro si l'appli n'est pas affichée sous ces barres."""
        try:
            vue = mActivity.getWindow().getDecorView()
            if Build.SDK_INT >= 30:
                Type = autoclass("android.view.WindowInsets$Type")
                ins = vue.getRootWindowInsets().getInsets(Type.systemBars() | Type.displayCutout())
                h, b, g, d = ins.top, ins.bottom, ins.left, ins.right
            else:
                return 0, 0, 0, 0       # avant Android 11 : jamais d'affichage bord à bord
            # la fenêtre Kivy couvre-t-elle tout l'écran (barres comprises) ?
            if hauteur_fenetre < vue.getHeight() - max(h, b, 1) * 0.5:
                return 0, 0, 0, 0
            return int(h), int(b), int(g), int(d)
        except Exception as ex:
            print("Marges système indisponibles :", ex)
            return 0, 0, 0, 0

    def partager(uri, mime, titre="Partager"):
        if uri is None:
            return False
        intent = Intent(Intent.ACTION_SEND)
        intent.setType(mime)
        intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        texte = cast("java.lang.CharSequence", autoclass("java.lang.String")(titre))
        mActivity.startActivity(Intent.createChooser(intent, texte))
        return True

# ---------------------------------------------------------------------------
# Ordinateur (essais)
# ---------------------------------------------------------------------------
else:
    def choisir_images(rappel):
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.filechooser import FileChooserListView
        from kivy.metrics import dp

        boite = BoxLayout(orientation="vertical", spacing=dp(6))
        fc = FileChooserListView(path=os.getcwd(), multiselect=True,
                                 filters=["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"])
        boite.add_widget(fc)
        ligne = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        pop = Popup(title="Choisir les cartons", content=boite, size_hint=(0.95, 0.9))

        def ok(*_):
            pop.dismiss()
            rappel([(p, os.path.basename(p)) for p in fc.selection])

        ligne.add_widget(Button(text="Annuler", on_release=lambda *_: (pop.dismiss(), rappel([]))))
        ligne.add_widget(Button(text="Ouvrir", on_release=ok))
        boite.add_widget(ligne)
        pop.open()

    def enregistrer(data, nom, mime):
        d = os.path.join(os.path.expanduser("~"), "AnalyseCartons")
        os.makedirs(d, exist_ok=True)
        chemin = os.path.join(d, nom)
        with open(chemin, "wb") as f:
            f.write(data)
        return None, chemin

    def partager(uri, mime, titre="Partager"):
        return False

    def marges_systeme(hauteur_fenetre):
        return 0, 0, 0, 0
