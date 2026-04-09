import requests
import sys
import json

def set_nina_target(name, ra_deg, dec_deg):
    url = "http://localhost:1888/v2/api/target/set"
    
    # Construction du dictionnaire de données
    payload = {
        "Name": name,
        "RA": float(ra_deg),
        "Dec": float(dec_deg)
    }
    
    try:
        # Envoi de la requête POST à NINA
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            print(f"SUCCÈS : Cible '{name}' injectée dans NINA.")
        else:
            print(f"ERREUR : NINA a répondu avec le code {response.status_code}")
            
    except Exception as e:
        print(f"ERREUR : Impossible de contacter NINA. Détails : {e}")

if __name__ == "__main__":
    # Vérification des arguments passés par NINA
    if len(sys.argv) < 4:
        print("Usage: python survey_set_target.py <Name> <RA_Deg> <Dec_Deg>")
    else:
        target_name = sys.argv[1]
        ra = sys.argv[2]
        dec = sys.argv[3]
        set_nina_target(target_name, ra, dec)