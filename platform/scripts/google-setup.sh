#!/usr/bin/env bash
# Ege Alfa: Drive gelir senkronu için Google kurulumu (Cloud Shell'de çalıştırın).
#   1) Sheets API'yi açar
#   2) Servis hesabı oluşturur (varsa yeniden kullanır)
#   3) JSON anahtarını ~/egealfa/google-sa.json olarak kaydeder (varsa yeni anahtar üretmez)
#   4) Tabloyu paylaşmanızı bekler, ardından erişimi gerçekten test eder
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
SHEET_ID="${SHEET_ID:-1IAFrxrPgDu9BsSq59LbOtA0fScGO-p5lyTIXcpUwsZs}"
SA_NAME="egealfa-drive-gelir"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
OUT_DIR="$HOME/egealfa"
KEY_FILE="$OUT_DIR/google-sa.json"

[ -n "$PROJECT_ID" ] || { echo "Proje seçili değil: gcloud config set project <PROJE_ID>"; exit 1; }
echo "Proje: $PROJECT_ID"

echo "1/4 Sheets API açılıyor..."
gcloud services enable sheets.googleapis.com --project "$PROJECT_ID"

echo "2/4 Servis hesabı..."
if gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "    zaten var: $SA_EMAIL"
else
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID" \
    --display-name "Ege Alfa Drive gelir senkronu (salt-okunur)"
  sleep 5  # IAM yayılması
fi

echo "3/4 JSON anahtarı..."
mkdir -p "$OUT_DIR" && chmod 700 "$OUT_DIR"
if [ -s "$KEY_FILE" ]; then
  echo "    zaten var: $KEY_FILE (yeni anahtar üretilmedi)"
else
  gcloud iam service-accounts keys create "$KEY_FILE" --iam-account "$SA_EMAIL" --project "$PROJECT_ID"
  chmod 600 "$KEY_FILE"
fi

cat <<EOF

══════════════════════════════════════════════════════════════════════
 ŞİMDİ TABLOYU PAYLAŞIN (tarayıcıda, bir kez):
   https://docs.google.com/spreadsheets/d/$SHEET_ID/edit
   Sağ üstte "Paylaş" → şu e-postayı ekleyin → rol: Görüntüleyen
   → "Kişileri bilgilendir" işaretini kaldırın → Gönder

   $SA_EMAIL
══════════════════════════════════════════════════════════════════════
EOF
read -rp "Paylaştıktan sonra Enter'a basın... " _

echo "4/4 Erişim testi..."
b64() { openssl base64 -e -A | tr '+/' '-_' | tr -d '='; }
PEM="$(mktemp)"; trap 'rm -f "$PEM"' EXIT
python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["private_key"])' "$KEY_FILE" > "$PEM"
NOW=$(date +%s)
HEADER=$(printf '{"alg":"RS256","typ":"JWT"}' | b64)
CLAIM=$(printf '{"iss":"%s","scope":"https://www.googleapis.com/auth/spreadsheets.readonly","aud":"https://oauth2.googleapis.com/token","iat":%d,"exp":%d}' \
  "$SA_EMAIL" "$NOW" "$((NOW + 3600))" | b64)
SIG=$(printf '%s.%s' "$HEADER" "$CLAIM" | openssl dgst -sha256 -sign "$PEM" | b64)
TOKEN=$(curl -s -d "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=$HEADER.$CLAIM.$SIG" \
  https://oauth2.googleapis.com/token | python3 -c 'import json,sys;print(json.load(sys.stdin).get("access_token",""))')
[ -n "$TOKEN" ] || { echo "HATA: servis hesabı token alamadı (anahtar dosyasını kontrol edin)"; exit 1; }

RESP=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID?fields=properties.title,sheets.properties.title")
if echo "$RESP" | grep -q '"error"'; then
  echo "HATA: tabloya erişilemedi. Paylaşımı kontrol edin ($SA_EMAIL → Görüntüleyen)."
  echo "$RESP" | head -c 400; echo
  exit 1
fi
echo "$RESP" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("BAŞARILI ✓ Tablo:", d["properties"]["title"])
for s in d.get("sheets", []): print("   -", s["properties"]["title"])'

cat <<EOF

Kurulum tamam. Sunucuya taşıyacaklarınız:
  1) Anahtar dosyası : $KEY_FILE  →  platform/secrets/google-sa.json
     (Cloud Shell'den indirmek için: cloudshell download $KEY_FILE)
  2) .env satırları  :
       DRIVE_INCOME_SPREADSHEET_ID=$SHEET_ID
       GOOGLE_SERVICE_ACCOUNT_JSON=/run/secrets/google-sa.json

UYARI: Anahtar dosyası paroladır. Sohbete, e-postaya veya GitHub'a koymayın.
EOF
