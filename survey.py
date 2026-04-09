"""
survey.py - Génération de coordonnées pour survey astronomique et injection N.I.N.A.

FONCTIONNEMENT :
1. Lecture de la configuration (Azimut/Déclinaison cibles) dans survey_config.txt.
2. Gestion de la dérive sidérale via l'index :
    - Si index = 0 : Calcule la RA initiale (RA0) en temps réel selon le Temps Sidéral Local (TSL) 
      et l'Azimut de départ. Sauvegarde cette RA0 dans survey_state.txt.
      Utile pour initialiser le survey ou le RECALER après une interruption (ex: Confirmation).
    - Si index > 0 : Calcule la RA en ajoutant un décalage fixe (pas de 90% du champ) à la RA0 
      mémorisée, garantissant la continuité du balayage indépendamment du temps écoulé.
3. Modes d'exécution :
    - GETCOORDS : Calcule les coordonnées, nomme le champ et injecte directement la cible 
      dans N.I.N.A. via son API locale (port 1888).
    - RA / DEC : (Rétro-compatibilité) Retourne la coordonnée sous forme d'Exit Code.

USAGE DEPUIS N.I.N.A. :
    python survey.py GETCOORDS <index> <FieldName>
"""

import sys
import math
import datetime
import os
import requests # <--- Ajout pour l'API

# ─────────────────────────────────────────────
# Lecture du fichier de config
# ─────────────────────────────────────────────

def lire_config(chemin):
    config = {}
    with open(chemin, 'r', encoding='utf-8') as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith('#'):
                continue
            if '=' in ligne:
                cle, valeur = ligne.split('=', 1)
                # Supprimer les commentaires en fin de ligne
                valeur = valeur.split('#')[0].strip()
                config[cle.strip()] = valeur
    return config

# ─────────────────────────────────────────────
# Calcul du Temps Sideral Local (TSL) en degres
# ─────────────────────────────────────────────

def calcul_tsl(longitude_deg):
    """Calcule le TSL en degres pour la date et heure UTC actuelles."""
    now = datetime.datetime.now(datetime.timezone.utc)
    Y = now.year
    M = now.month
    D = now.day
    UT = now.hour + now.minute / 60.0 + now.second / 3600.0

    # Jour Julien
    JD = (367 * Y
          - int(7 * (Y + int((M + 9) / 12)) / 4)
          + int(275 * M / 9)
          + D + 1721013.5
          + UT / 24.0)

    # Jours depuis J2000.0
    d = JD - 2451545.0

    # GMST en degres
    GMST = 280.46061837 + 360.98564736629 * d
    GMST = GMST % 360.0
    if GMST < 0:
        GMST += 360.0

    # TSL
    TSL = (GMST + longitude_deg) % 360.0
    if TSL < 0:
        TSL += 360.0

    return TSL

# ─────────────────────────────────────────────
# Conversion Az + Dec -> RA
# ─────────────────────────────────────────────

def az_dec_to_ra(az_deg, dec_deg, latitude_deg, tsl_deg):
    """
    Convertit Az (Nord=0, croissant vers l'Est) + Dec en RA.
    Retourne RA en degres.
    """
    az  = math.radians(az_deg)
    dec = math.radians(dec_deg)
    lat = math.radians(latitude_deg)

    # Angle horaire H via la formule directe Az -> H
    tan_H = math.sin(az) / (math.cos(az) * math.sin(lat) - math.tan(dec) * math.cos(lat))
    H = math.degrees(math.atan(tan_H))

    # Lever l'ambiguite de quadrant :
    # Az dans [0,180] -> objet a l'Est -> H negatif (avant la culmination)
    # Az dans [180,360] -> objet a l'Ouest -> H positif
    if 0 <= az_deg < 180:
        if H > 0:
            H -= 180.0
    else:
        if H < 0:
            H += 180.0

    # RA = TSL - H
    ra = (tsl_deg - H) % 360.0
    return ra

# ─────────────────────────────────────────────
# Calcul de la RA et Dec du champ demande
# ─────────────────────────────────────────────

def get_ra_dec(config, index, repertoire):
    az_depart  = float(config['Az_depart'])
    dec_depart = float(config['Dec_depart'])
    nb_champs  = int(config['Nb_champs'])
    direction  = config['Direction'].strip().lower()
    longitude  = float(config['Longitude'])
    latitude   = float(config['Latitude'])

    # Pas en RA : champ 52.8' avec recouvrement 10%
    pas_ra_deg = 52.8 * 0.90 / 60.0  # 0.792 degres

    if direction == 'ouest':
        pas_ra_deg = -pas_ra_deg

    # Fichier de sauvegarde de RA0
    chemin_state = os.path.join(repertoire, 'survey_state.txt')

    if index == 0:
        # Calculer RA0 depuis Az/Dec et TSL courant, puis le sauvegarder
        tsl = calcul_tsl(longitude)
        ra0 = az_dec_to_ra(az_depart, dec_depart, latitude, tsl)
        with open(chemin_state, 'w', encoding='utf-8') as f:
            f.write(f"{ra0}\n")
        print(f"[state] RA0 = {ra0:.6f} deg sauvegarde dans survey_state.txt")
    else:
        # Relire RA0 depuis le fichier state
        with open(chemin_state, 'r', encoding='utf-8') as f:
            ra0 = float(f.read().strip())

    # RA du champ demande = RA0 + index * pas
    ra  = (ra0 + index * pas_ra_deg) % 360.0
    dec = dec_depart

    return ra, dec, nb_champs

# ─────────────────────────────────────────────
# NOUVEAU : Injection dans N.I.N.A.
# ─────────────────────────────────────────────
def inject_to_nina(name, ra_hours, dec_deg): # Changé ra_deg en ra_hours pour plus de clarté
    url = "http://localhost:1888/v2/api/sequence/set-target"
    
    params = {
        "name": str(name),
        "ra": f"{ra_hours:.6f}",  # C'est maintenant limpide
        "dec": f"{dec_deg:.6f}",
        "rotation": "0",
        "index": "0" 
    }
    
    try:
        # ON UTILISE GET (important !)
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            print(f"[API] Succès : Cible mise à jour -> {name}")
            return True
        else:
            print(f"[API] Erreur {r.status_code} : {r.text}")
    except Exception as e:
        print(f"[API] Connexion échouée : {e}")
    return False
    
# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage : survey.py GETCOORDS <index> <FieldName>")
        sys.exit(1)

    argument = sys.argv[1].upper()
    index    = int(sys.argv[2])
    
    repertoire = os.path.dirname(os.path.abspath(__file__))
    chemin_config = os.path.join(repertoire, 'survey_config.txt')
    config = lire_config(chemin_config)
    ra_deg, dec_deg, nb_champs = get_ra_dec(config, index, repertoire)

    # Nouveau mode GETCOORDS
    if argument == 'GETCOORDS':
        field_name = sys.argv[3] if len(sys.argv) > 3 else f"Field_{index}"
        inject_to_nina(field_name, ra_deg, dec_deg)
        sys.exit(0)

    # Rétro-compatibilité pour tes anciens appels RA/Dec (au cas où)
    elif argument == 'RA':
        ra_hours = ra_deg / 15.0
        sys.exit(int(round(ra_hours * 10000)))
    elif argument == 'DEC':
        sys.exit(int(round(dec_deg * 10000)))