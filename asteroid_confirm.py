"""
SCRIPT : asteroid_confirm.py
AUTEUR : Aster
DESCRIPTION :
    Ce script gère le flux de travail des confirmations d'astéroïdes dans NINA.
    Il permet d'extraire des coordonnées depuis une liste MPC, de calculer une 
    extrapolation de position en temps réel, d'injecter la cible dans NINA via 
    son API, et de gérer l'archivage de la liste de travail.

USAGE :
    python asteroid_confirm.py <conflist_path> <MODE>

ARGUMENTS :
    1. conflist_path (str) : 
        Chemin complet vers le fichier texte contenant la liste des objets à 
        confirmer (ex: "H:\\NightImages\\Confirm\\conflist.txt").
        Ce fichier doit contenir les noms des fichiers MPC (.txt) à traiter.

    2. MODE (str) :
        Définit l'action à exécuter par le script :
        
        - COUNT : 
            Compte le nombre de lignes restant dans la liste. 
            Retourne le nombre via l'Exit Code (utile pour les boucles NINA).
            
        - GETCOORDS : 
            Lit le premier fichier MPC de la liste, calcule la position RA/DEC 
            extrapolée à l'instant T, et l'envoie au conteneur de cible NINA.
            Retourne la RA formatée pour l'Exit Code (RA_heures * 10000).
            
        - FINISH : 
            Une fois l'acquisition terminée, déplace le fichier MPC traité vers 
            le dossier 'ConfirmSave' et supprime la ligne correspondante dans 
            la liste de travail (conflist.txt).

DÉPENDANCES :
    - Librairies Python : sys, os, shutil, requests, datetime.
    - Serveur API de NINA activé (par défaut sur le port 1888).
"""

import sys
import os
import shutil
import math
import logging
import requests
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION NINA ---
NINA_API_URL = "http://localhost:1888/v2/api/sequence/set-target"
NINA_SCALE   = 10000  # Pour l'Exit Code (RA)
NINA_ERROR   = 9999

# Détermination dynamique du dossier du script (H:\NightImages\Scripts\)
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOG_FILE     = os.path.join(SCRIPT_DIR, 'asteroid_confirm.log')

# --- LOGGING ---
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
)

def log(msg, level='info'):
    print(msg)
    if level == 'info': logging.info(msg)
    elif level == 'error': logging.error(msg)
    elif level == 'warning': logging.warning(msg)

# --- COMMUNICATION NINA API ---
def send_to_nina(obj_id, ra_deg, dec_deg):
    """Envoie les données au Target Container (Index 0) de NINA"""
    
    # AJOUT : Conversion Degrés -> Heures pour l'API NINA
    ra_hours = float(ra_deg)# / 15.0. Faux. C'est déjà divisé par 15 par ailleurs.
    
    params = {
        "name": str(obj_id),
        "ra": f"{ra_hours:.6f}",   # <--- ON ENVOIE LES HEURES ICI
        "dec": f"{dec_deg:.6f}",   # Les degrés sont bons pour la Dec
        "rotation": "0",
        "index": "1"               # <--- On passe à 1 pour cibler le 2ème container       
    }
    try:
        r = requests.get(NINA_API_URL, params=params, timeout=5)
        if r.status_code == 200:
            log(f"[API] Succès : Cible mise à jour -> {obj_id}")
            return True
        log(f"[API] Erreur {r.status_code} : {r.text}", 'error')
    except Exception as e:
        log(f"[API] Connexion échouée : {e}", 'error')
    return False

# --- CALCULS MPC ---
def parse_mpc_line(line):
    line = line.ljust(80)
    # Lecture large des colonnes 1 à 12 (index 0 à 12) pour attraper 
    # les numéros définitifs ET les désignations provisoires.
    obj_id = line[0:12].strip() 
    
    date_str = line[15:32].strip()
    ra_str, dec_str = line[32:44].strip(), line[44:56].strip()
    
    dp = date_str.split()
    day_frac = float(dp[2])
    day_int = int(day_frac)
    obs_dt = datetime(int(dp[0]), int(dp[1]), day_int, tzinfo=timezone.utc) + timedelta(seconds=(day_frac-day_int)*86400)
    
    rp = ra_str.split()
    ra_deg = (int(rp[0]) + int(rp[1])/60.0 + float(rp[2])/3600.0) * 15.0
    
    sign = -1 if dec_str.startswith('-') else 1
    dp2 = dec_str.lstrip('+-').split()
    dec_deg = sign * (int(dp2[0]) + int(dp2[1])/60.0 + float(dp2[2])/3600.0)
    
    return obs_dt, ra_deg, dec_deg, obj_id

def compute_extrapolated_coords(filepath):
    obs = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip(): obs.append(parse_mpc_line(line))
    if len(obs) < 2: raise ValueError("Besoin de 2 lignes MPC minimum.")
    
    t1, ra1, dec1, _ = obs[0]
    tn, ran, decn, obj_id = obs[-1]
    dt_min = (tn - t1).total_seconds() / 60.0
    dec_mid = math.radians((dec1 + decn) / 2.0)
    
    # Vitesses en arcsec/min
    vra = (ran - ra1) * 3600.0 * math.cos(dec_mid) / dt_min
    vdec = (decn - dec1) * 3600.0 / dt_min
    
    # Temps depuis la dernière obs
    dt_extrap = (datetime.now(timezone.utc) - tn).total_seconds() / 60.0
    new_ra = (ran + vra * dt_extrap / (3600.0 * math.cos(math.radians(decn)))) % 360.0
    new_dec = decn + vdec * dt_extrap / 3600.0
    
    return obj_id, new_ra, new_dec

# --- MAIN ---
def main():
    if len(sys.argv) < 3:
        print("Usage: script.py <conflist_path> <MODE>")
        sys.exit(0)

    # Chemins basés sur l'argument reçu (H:\NightImages\Confirm\conflist.txt)
    conflist_path = os.path.abspath(sys.argv[1])
    nina_mode     = sys.argv[2].upper()
    confirm_dir   = os.path.dirname(conflist_path)

    try:
        # MODE COUNT : Pour la condition de boucle NINA
        if nina_mode == 'COUNT':
            count = 0
            if os.path.exists(conflist_path):
                with open(conflist_path, 'r') as f:
                    count = len([l for l in f if l.strip()])
            log(f"[COUNT] Reste {count} objets à traiter.")
            sys.exit(count)

        # Extraction du premier fichier de la liste
        entry = None
        if os.path.exists(conflist_path):
            with open(conflist_path, 'r') as f:
                for line in f:
                    if line.strip():
                        entry = line.strip()
                        break
        
        if not entry:
            log("[INFO] Liste vide, fin de session.")
            sys.exit(0)

        toconfirm_file = os.path.join(confirm_dir, entry)

        # MODE GETCOORDS : Calcul et injection API
        if nina_mode == 'GETCOORDS':
            try:
                obj_id, ra_deg, dec_deg = compute_extrapolated_coords(toconfirm_file)
                if send_to_nina(obj_id, ra_deg, dec_deg):
                    # Retourne la RA (en heures) * 10000 pour NINA si besoin
                    sys.exit(int(round((ra_deg/15.0) * NINA_SCALE)))
                else:
                    sys.exit(NINA_ERROR)
            except Exception as e:
                log(f"[GETCOORDS] Erreur : {e}", 'error')
                sys.exit(NINA_ERROR)

        # MODE FINISH : Archivage et décrémentation
        elif nina_mode == 'FINISH':
            # 1. Archivage physique
            if os.path.exists(toconfirm_file):
                save_dir = os.path.join(os.path.dirname(confirm_dir), "ConfirmSave")
                os.makedirs(save_dir, exist_ok=True)
                shutil.move(toconfirm_file, os.path.join(save_dir, entry))
                log(f"[FINISH] {entry} déplacé vers ConfirmSave.")
            
            # 2. Nettoyage de la liste (Supprime la ligne 1)
            if os.path.exists(conflist_path):
                with open(conflist_path, 'r') as f:
                    lines = f.readlines()
                with open(conflist_path, 'w') as f:
                    f.writelines(lines[1:])
                log("[FINISH] Liste mise à jour (COUNT-1).")
            
            sys.exit(0)

    except Exception as e:
        log(f"ERREUR GÉNÉRALE : {e}", 'error')
        sys.exit(NINA_ERROR)

if __name__ == "__main__":
    main()