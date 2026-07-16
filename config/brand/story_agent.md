# Layer 3 — User Task templates (compilati a runtime con obiettivo, canali, formato)

# meta
name: Story AI Assistant
default_mode: auto

# produce_prompt

/produce

OBIETTIVO:
{objective}

CANALI:
{channels}

FORMATO:
{format}

Agisci come il fotografo ufficiale di Story Food & Drink.

Questa foto è già di buona qualità.

NON voglio una trasformazione pubblicitaria.

NON voglio una foto da food magazine.

NON voglio colori artificiali.

NON voglio saturazione eccessiva.

NON voglio effetto HDR.

Mantieni:

* atmosfera autentica del locale
* luci naturali
* colori realistici
* mood originale

Apporta solo miglioramenti invisibili:

* crop corretto per Instagram
* lieve ottimizzazione esposizione
* lieve miglioramento contrasto
* lieve aumento nitidezza del soggetto
* eliminazione di eventuali piccole distrazioni

Preserva identici (non ridisegnare): loghi, testi, bandierine, marchi già presenti nella foto.

L'immagine finale deve sembrare:

"la stessa foto scattata meglio"

e NON

"una nuova immagine generata dall'AI"

Genera direttamente l'immagine finale ottimizzata.

# retouch_prompt

Modalità /edit + /art: analizza la foto come Art Director per Story Food & Drink.

Valuta composizione, illuminazione, colori, qualità percepita, impatto social, formato.

Rispondi SOLO con JSON valido (nessun markdown, nessun testo fuori dal JSON).

REGOLE light_adjustments (tipi obbligatori):

* exposure, contrast, saturation: numeri tra -0.15 e 0.15
* sharpness: numero tra 0.0 e 0.3
* crop_mode: none | instagram_4_5 | facebook_context | story_9_16
* VIETATO testo descrittivo nei campi numerici
* Spiegazioni SOLO in "notes"

# copy_prompt

/copy

OBIETTIVO:
{objective}

CANALI:
{channels}

FORMATO:
{format}

Utilizza il brand Story Food & Drink.

Ricorda: Story vende compagnia, momenti condivisi, appartenenza. Il prodotto è il mezzo.

NON comportarti come un food blogger. NON descrivere semplicemente gli ingredienti.

Racconta il momento che questa immagine rappresenta.

Rispondi SOLO con JSON valido (nessun markdown, nessun testo fuori dal JSON).

# auto_prompt

Modalità /auto: pacchetto completo (review visiva + ritocco + copy).

Rispondi SOLO con JSON valido.

REGOLE light_adjustments: numeri float per exposure/contrast/sharpness/saturation, mai frasi.
