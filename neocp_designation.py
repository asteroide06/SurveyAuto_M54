"""
neocp_designation.py
====================
Génération de désignations provisoires NEOCP sur 7 caractères.

Format : [3 car. date][3 car. champ][1 car. objet]

  - Date   : année (base 31, offset 2020) + mois + jour
  - Champ  : numéro cumulatif absolu en base 31 (AAA=1 … ZZ5=29791)
  - Objet  : 1-9 puis A-Z (35 candidats max par champ)

Codage base 31
--------------
  A=1, B=2, …, Z=26, 1=27, 2=28, 3=29, 4=30, 5=31
  (les chiffres 6-9 et 0 ne sont PAS utilisés)

Fichier compteur
----------------
  C:\\NightImages\\Scripts\\fieldcount.json
  {
      "count":        42,
      "encoded":      "AB3",
      "encoding":     "base31: A=1..Z=26, 1=27..5=31, AAA=1, AAB=2, ..., ZZ5=29791",
      "last_updated": "2026-03-17",
      "last_target":  "FCP0B01"
  }
"""

import json
import os
from datetime import date

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

YEAR_OFFSET   = 2020          # A=2021, B=2022, …, F=2026, …, Z=2046
COUNTER_FILE  = r"C:\NightImages\Scripts\fieldcount.json"
ENCODING_NOTE = "base31: A=1..Z=26, 1=27..5=31, AAA=1, AAB=2, ..., ZZ5=29791"

# ---------------------------------------------------------------------------
# Codage / décodage base 31 (caractère unique)
# ---------------------------------------------------------------------------

def encode_char(n: int) -> str:
    """Encode un entier 1..31 en 1 caractère."""
    if 1 <= n <= 26:
        return chr(64 + n)          # A..Z
    if 27 <= n <= 31:
        return str(n - 26)          # 1..5
    raise ValueError(f"Valeur hors plage [1-31] : {n}")


def decode_char(c: str) -> int:
    """Décode un caractère en entier 1..31."""
    c = c.upper()
    if c.isalpha():
        return ord(c) - 64          # A→1 … Z→26
    if c in "12345":
        return int(c) + 26          # 1→27 … 5→31
    raise ValueError(f"Caractère invalide (attendu A-Z ou 1-5) : {c!r}")


# ---------------------------------------------------------------------------
# Codage / décodage de la date (3 caractères)
# ---------------------------------------------------------------------------

def encode_date(year: int, month: int, day: int) -> str:
    """Encode une date en 3 caractères : Année + Mois + Jour."""
    return encode_char(year - YEAR_OFFSET) + encode_char(month) + encode_char(day)


def decode_date(code: str) -> tuple[int, int, int]:
    """Décode un code de 3 caractères en (année, mois, jour)."""
    if len(code) != 3:
        raise ValueError("Le code date doit faire exactement 3 caractères")
    return (
        decode_char(code[0]) + YEAR_OFFSET,
        decode_char(code[1]),
        decode_char(code[2]),
    )


# ---------------------------------------------------------------------------
# Codage / décodage du numéro de champ (3 caractères, base 31)
# ---------------------------------------------------------------------------

def encode_field(n: int) -> str:
    """Encode un entier 1..29791 en 3 caractères base 31."""
    if not (1 <= n <= 31 ** 3):
        raise ValueError(f"Numéro de champ hors plage [1-29791] : {n}")
    n -= 1                          # ramène à 0-based pour la division
    c3 = n % 31 + 1
    n //= 31
    c2 = n % 31 + 1
    c1 = n // 31 + 1
    return encode_char(c1) + encode_char(c2) + encode_char(c3)


def decode_field(code: str) -> int:
    """Décode un code de 3 caractères base 31 en entier 1..29791."""
    if len(code) != 3:
        raise ValueError("Le code champ doit faire exactement 3 caractères")
    c1, c2, c3 = decode_char(code[0]), decode_char(code[1]), decode_char(code[2])
    return (c1 - 1) * 31 ** 2 + (c2 - 1) * 31 + c3


# ---------------------------------------------------------------------------
# Codage de l'objet (1 caractère)
# ---------------------------------------------------------------------------

def encode_object(n: int) -> str:
    """Encode un numéro d'objet 1..35 : 1-9 puis A-Z."""
    if 1 <= n <= 9:
        return str(n)
    if 10 <= n <= 35:
        return chr(55 + n)          # 10→A, 11→B, …, 35→Z
    raise ValueError(f"Numéro d'objet hors plage [1-35] : {n}")


def decode_object(c: str) -> int:
    """Décode un caractère d'objet en entier 1..35."""
    if c.isdigit() and c != "0":
        return int(c)
    c = c.upper()
    if c.isalpha():
        return ord(c) - 55          # A→10, …, Z→35
    raise ValueError(f"Caractère objet invalide : {c!r}")


# ---------------------------------------------------------------------------
# Compteur de champs persistant
# ---------------------------------------------------------------------------

def _load_counter() -> dict:
    """Charge le fichier compteur ; retourne un dict vide si inexistant."""
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"count": 0}


def _save_counter(data: dict) -> None:
    """Sauvegarde le fichier compteur (crée le répertoire si besoin)."""
    os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def next_field_code(target_designation: str = "") -> tuple[int, str]:
    """
    Incrémente le compteur et retourne (numéro, code 3 car.).
    Met à jour fieldcount.json avec les métadonnées.
    """
    data = _load_counter()
    new_count = data.get("count", 0) + 1
    code = encode_field(new_count)
    data.update({
        "count":        new_count,
        "encoded":      code,
        "encoding":     ENCODING_NOTE,
        "last_updated": date.today().isoformat(),
        "last_target":  target_designation,
    })
    _save_counter(data)
    return new_count, code


def current_field_count() -> tuple[int, str]:
    """Retourne (numéro actuel, code) sans incrémenter."""
    data = _load_counter()
    n = data.get("count", 0)
    return n, (encode_field(n) if n > 0 else "---")


# ---------------------------------------------------------------------------
# Désignation complète
# ---------------------------------------------------------------------------

def make_designation(year: int, month: int, day: int,
                     object_number: int,
                     target_name: str = "") -> tuple[str, int, str]:
    """
    Génère une désignation NEOCP complète sur 7 caractères.

    Incrémente automatiquement le compteur de champs.

    Retourne (désignation, numéro_champ, code_champ).
    Exemple : ("FCPAAB3", 1054, "AAB")  -- fictif
    """
    date_code = encode_date(year, month, day)
    field_num, field_code = next_field_code()
    obj_code = encode_object(object_number)
    designation = date_code + field_code + obj_code
    # mise à jour du last_target avec la désignation finale
    data = _load_counter()
    data["last_target"] = designation
    _save_counter(data)
    return designation, field_num, field_code


# ---------------------------------------------------------------------------
# Interface ligne de commande (appelée depuis process_field.ps1)
# ---------------------------------------------------------------------------
#
#   python neocp_designation.py --next-field YEAR MONTH DAY
#   → imprime le code 6 caractères sur stdout, ex. "FCPAAB"
#
import sys

def _cli():
    if len(sys.argv) == 5 and sys.argv[1] == "--next-field":
        try:
            y, m, d = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
            date_code = encode_date(y, m, d)
            _, field_code = next_field_code()
            print(date_code + field_code, end="")
        except Exception as e:
            print(f"ERREUR: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _cli()   # si appelé avec --next-field, sort ici

    # Tests (exécutés seulement si pas d'arguments CLI)
    if len(sys.argv) == 1:
        print("=== Codage date ===")
        test_dates = [
            (2026,  1,  1),
            (2026,  3, 17),
            (2026, 12, 31),
            (2027,  6, 20),
            (2046, 12, 31),
        ]
        print(f"{'Date':<12} {'Code':>5}   {'Retour':<12} OK")
        print("-" * 40)
        for y, m, d in test_dates:
            code = encode_date(y, m, d)
            back = decode_date(code)
            ok = "✓" if back == (y, m, d) else "✗"
            print(f"{y}-{m:02d}-{d:02d}   {code:>5}   {back[0]}-{back[1]:02d}-{back[2]:02d}   {ok}")

        print("\n=== Codage champ (base 31) ===")
        test_fields = [1, 2, 31, 32, 961, 962, 29791]
        print(f"{'N':>6}  {'Code':>5}  {'Retour':>6}  OK")
        print("-" * 30)
        for n in test_fields:
            code = encode_field(n)
            back = decode_field(code)
            ok = "✓" if back == n else "✗"
            print(f"{n:>6}  {code:>5}  {back:>6}  {ok}")

        print("\n=== Codage objet ===")
        for n in [1, 9, 10, 35]:
            c = encode_object(n)
            back = decode_object(c)
            ok = "✓" if back == n else "✗"
            print(f"  {n:>2} → {c!r} → {back:>2}  {ok}")
