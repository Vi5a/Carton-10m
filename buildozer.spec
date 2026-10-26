[app]

# Nom affiché sous l'icône
title = Analyse Cartons 10m
package.name = analysecartons
package.domain = fr.tir10m

source.dir = .
source.include_exts = py,png,ttf
source.exclude_dirs = bin,.buildozer,.github,exemples
source.exclude_patterns = README.md

version = 1.0

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

android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
# arm64-v8a couvre tous les téléphones récents ; ajouter armeabi-v7a pour de très
# vieux appareils (la compilation est alors deux fois plus longue).
android.archs = arm64-v8a
android.allow_backup = True

# Version figée de python-for-android (compilation reproductible)
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
