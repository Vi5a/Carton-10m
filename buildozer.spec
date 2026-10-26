[app]

# Nom affiché sous l'icône
title = Analyse Cartons 10m
package.name = analysecartons
package.domain = fr.tir10m

source.dir = .
source.include_exts = py,png,ttf
source.exclude_dirs = bin,.buildozer,.github,exemples
source.exclude_patterns = README.md

version = 1.1

# OpenCV et numpy sont compilés pour Android par python-for-android
requirements = python3,kivy,numpy,opencv,pillow,pyjnius,android

icon.filename = %(source.dir)s/icone.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #1C1F22

orientation = portrait
fullscreen = 0

# Aucune permission : pas d'appareil photo, pas d'accès général au stockage.
# Les photos sont choisies dans la galerie via le sélecteur du système, et les
# résultats sont enregistrés dans Images / Téléchargements via MediaStore.
android.permissions =

# Cible Android 16 (API 36), comme exigé pour les applis récentes.
# Fonctionne à partir d'Android 7 (API 24).
android.api = 36
android.minapi = 24
android.ndk_api = 24
# NDK r28 : bibliothèques alignées sur 16 Ko (obligatoire sur les téléphones Android 15+ récents)
android.ndk = 28c
android.accept_sdk_license = True
# arm64-v8a couvre tous les téléphones récents ; ajouter armeabi-v7a pour de très
# vieux appareils (la compilation est alors deux fois plus longue).
android.archs = arm64-v8a
android.allow_backup = True

# Dernière version de python-for-android (mai 2026) : Python 3.14, OpenCV 4.12,
# numpy 2.3, Pillow 11.3, Kivy 2.3.1. Version figée pour une compilation reproductible.
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
warn_on_root = 0
