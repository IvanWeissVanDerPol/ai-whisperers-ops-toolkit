#!/usr/bin/env bash
# Generate draft social media posts for Ometz from the latest content JSONs.
# Picks 1 random service + 1 testimonial, drafts a FB post + IG caption + WhatsApp message.
# Useful for human review before posting — never auto-posts.
#
# Usage: social-draft.sh [locale]

set -euo pipefail
LOCALE="${1:-es}"
APP="/root/paragu-ai-platform/apps/dra-gabriela"

# Pick a random service file
SERVICE_FILE=$(ls "$APP/content/$LOCALE/services/"*.json 2>/dev/null | shuf -n 1)
[ -z "$SERVICE_FILE" ] && { echo "❌ No services found"; exit 1; }

SERVICE=$(python3 -c "
import json, sys
d = json.load(open('$SERVICE_FILE'))
print(d.get('title', d.get('name', 'servicio dental')))
")

# Pick testimonial
TESTIMONIAL=$(python3 -c "
import json, os, random
files = [f for f in os.listdir('$APP/content/$LOCALE') if 'testimonial' in f or 'review' in f]
if not files:
    print('Testimonio pendiente — escribinos por WhatsApp y te contamos casos reales.')
else:
    d = json.load(open(os.path.join('$APP/content/$LOCALE', random.choice(files))))
    items = d.get('testimonials', d.get('reviews', []))
    if items:
        t = random.choice(items)
        quote = t.get('quote', t.get('text', ''))
        name = t.get('name', 'Paciente')
        print(f'\"{quote}\" — {name}')
    else:
        print('Testimonio pendiente — escribinos por WhatsApp y te contamos casos reales.')
")

echo "============================================================"
echo "  📱 DRAFT SOCIAL POSTS — Ometz Dental"
echo "  Locale: $LOCALE"
echo "  Service: $SERVICE"
echo "  Testimonial: $TESTIMONIAL"
echo "  Generated: $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"
echo ""
echo "--- FACEBOOK POST (long, story-style) ---"
cat << EOF
¿Tenés miedo de ir al dentista? No estás exagerando. Tu miedo es real.

En Ometz Dental entendemos. Por eso:
• Te escucho antes de tocar
• Te explico todo antes de hacerlo
• Vos controlás el ritmo
• Si necesitás parar, paramos

Hoy hablamos sobre: $SERVICE

📍 Auditores de la Guerra del Chaco 617, Barrio Mburucuyá, Asunción
📲 +595 981 146 759 (WhatsApp)
🌐 ometzdental.com

#OmetzDental #Asunción #SaludBucal #DentistaAsunción
EOF
echo ""
echo "--- INSTAGRAM CAPTION (short, visual) ---"
cat << EOF
$TESTIMONIAL

Cada paciente tiene su historia. En Ometz, la escuchamos primero.

→ Escribinos por WhatsApp: link en bio
→ Conocé $SERVICE: ometzdental.com

#OmetzDental #OdontologíaHumana #Asunción
EOF
echo ""
echo "--- WHATSAPP STATUS (~150 chars) ---"
cat << EOF
🦷 Ometz Dental — Te escucho antes de tocar.
📲 Escribinos si querés saber más sobre $SERVICE.
ometzdental.com · Mburucuyá, Asunción
EOF
echo ""
echo "============================================================"
echo "✓ 3 drafts generated. Review and approve before posting."
echo "  To post: bash /root/.hermes/scripts/fb-post.sh \"<paste FB text>\""
echo "  To post IG: bash /root/.hermes/scripts/ig-post.sh \"<caption>\" <image_url>"
echo "============================================================"