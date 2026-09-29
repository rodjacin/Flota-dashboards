#!/bin/bash
# =============================================================================
#  Genera los dashboards de flota (SAB y GRA-MAD-NOM-ALC) en la nube.
#  Lo lanza GitHub Actions (.github/workflows/actualizar_flota.yml).
#  Reproduce lo que hacía el Mac: extraer -> combinar -> generar -> publicar.
#
#  Necesita estas variables (secretos de GitHub):
#    GCP_JSON   contenido de gcp_mushdrink.json   (bucket de Glovo)
#    GLOVO_KEY  contenido de private_key.pem       (pestaña En vivo)
# =============================================================================
set -euo pipefail
export TZ=Europe/Madrid
AUTO="$(cd "$(dirname "$0")" && pwd)"      # carpeta automatizacion/ del repo
REPO="$(dirname "$AUTO")"
DL="$HOME/Downloads"                        # los scripts esperan ~/Downloads
mkdir -p "$DL" "$HOME/.gcp" "$HOME/claves-pem"

# 1) credenciales desde los secretos (solo existen durante la ejecución)
if [ -n "${GCP_JSON:-}" ];  then printf '%s' "$GCP_JSON"  > "$HOME/.gcp/gcp_mushdrink.json"; chmod 600 "$HOME/.gcp/gcp_mushdrink.json"; fi
if [ -n "${GLOVO_KEY:-}" ]; then printf '%s\n' "$GLOVO_KEY" | tr -d '\r' > "$HOME/claves-pem/private_key.pem"; chmod 600 "$HOME/claves-pem/private_key.pem"; fi

# 2) scripts, plantillas y ficheros de entrada en ~/Downloads
cp "$AUTO"/*.py "$AUTO"/plantilla_resumen_*.html "$DL"/
cp "$AUTO"/entradas/* "$DL"/ 2>/dev/null || true
# la pestaña Capacidad ordena los horarios por fecha de fichero: se restauran las
# fechas originales; los ficheros subidos después toman la fecha de su commit
python3 - "$AUTO/entradas" "$DL" "$REPO" <<'PY'
import sys, os, json, subprocess
ent, dl, repo = sys.argv[1:4]
orig = {}
p = os.path.join(ent, "_fechas_originales.json")
if os.path.exists(p): orig = json.load(open(p, encoding="utf-8"))
for b in os.listdir(ent):
    if b.startswith("_"): continue
    t = orig.get(b)
    if t is None:
        out = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ct", "--", os.path.join(ent, b)],
                             capture_output=True, text=True).stdout.strip()
        t = float(out) if out else None
    if t: os.utime(os.path.join(dl, b), (t, t))
PY

# ids de ciudad de la pestaña En vivo (si no, se averiguan con la API)
mkdir -p "$DL/dashboards/en_vivo"
[ -f "$AUTO/entradas/_city_ids_en_vivo.json" ] && cp "$AUTO/entradas/_city_ids_en_vivo.json" "$DL/dashboards/en_vivo/city_ids.json"

# 3) extraer -> combinar -> generar
cd "$DL"
echo "==== $(date '+%Y-%m-%d %H:%M:%S') INICIO ===="
[ "${SALTAR_EXTRAER:-0}" = 1 ] && echo "(prueba: sin descarga del bucket)" || python3 extraer_datos_fleet.py
python3 combinar_datos_fleet.py
python3 generar_resumen_flota.py

# 4) copiar al sitio publicado (mismo sello que ponía el Mac)
STAMP=$(date '+%d/%m/%Y %H:%M')
OUT="$DL/dashboards"
publish(){
  mkdir -p "$(dirname "$2")"; cp "$1" "$2"
  perl -pi -e "s|Fleet Partner Report 2\.0</div>|Fleet Partner Report 2.0<br>Actualizado $STAMP</div>|" "$2"
  perl -pi -e 's|<head>|<head>\n<meta name="robots" content="noindex,nofollow">|' "$2"
}
publish "$OUT/resumen_flota_riders_SAB.html"             "$REPO/sab/index.html"
publish "$OUT/resumen_flota_riders_GRA_MAD_NOM_ALC.html" "$REPO/gra-mad-nom-alc/index.html"
cat > "$REPO/index.html" <<HTML
<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consola de Flota</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#F6F7F9;color:#14171F;max-width:560px;margin:60px auto;padding:0 16px}
a{display:block;background:#fff;border:1px solid #E4E7EC;border-left:3px solid #0E5A6B;border-radius:10px;padding:16px;margin:12px 0;color:#0E5A6B;text-decoration:none;font-weight:600}
small{color:#6B7280}</style></head><body>
<h1 style="font-size:20px">Consola de Flota · Resumen por Rider</h1>
<a href="sab/">SAB</a>
<a href="gra-mad-nom-alc/">GRA · MAD · NOM · ALC</a>
<a href="mushdrink/">MushDrink · Panel operativo</a>
<small>Actualizado $STAMP</small>
</body></html>
HTML
touch "$REPO/.nojekyll"
rm -f "$HOME/.gcp/gcp_mushdrink.json" "$HOME/claves-pem/private_key.pem"
echo "==== $(date '+%Y-%m-%d %H:%M:%S') FIN ===="
