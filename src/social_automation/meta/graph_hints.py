"""Suggerimenti azionabili per errori comuni della Meta Graph API (UI, CLI)."""


def meta_graph_error_action_hint(message: str) -> str:
    """
    Testo markdown da appendere a messaggi di errore Meta quando il testo
    dell'eccezione contiene codici/messaggi noti.
    """
    msg = (message or "").strip()
    if not msg:
        return ""
    lower = msg.lower()
    chunks: list[str] = []

    if (
        "[200/" in msg
        or "(200/" in msg
        or (
            "permission" in lower
            and "app review" in lower
            and ("pages_manage_posts" in lower or "pages_read_engagement" in lower)
        )
        or (
            "permissions error" in lower
            and ("#200" in msg or "[200/" in msg or "(200/" in msg)
        )
    ):
        chunks.append(
            "\n\nPermessi app / token (errore Graph 200):\n"
            "- In Meta for Developers (developers.facebook.com/apps) apri la tua app → "
            "Casi d’uso / Autorizzazioni e funzioni e abilita pages_manage_posts "
            "e, se richiesto, pages_read_engagement (Meta può elencarli insieme per alcune chiamate).\n"
            "- In modalità Live spesso servono App Review; in Sviluppo di solito "
            "bastano account con ruolo Amministratore / Sviluppatore / Tester sull’app.\n"
            "- Verifica ruolo sulla Facebook Page (es. Editor o superiore) per creare post.\n"
            "- Da terminale: PYTHONPATH=src python -m social_automation meta-debug-token "
            "— nella risposta JSON, campo data.scopes indica i permessi effettivi del Page token; "
            "se manca pages_manage_posts, rifai OAuth con META_OAUTH_SCOPES aggiornati.\n"
            "- Per rimuovere il token salvato su disco prima di un nuovo login: "
            "meta-clear-page-token --yes (poi svuota META_PAGE_ACCESS_TOKEN nel .env se lo usi).\n"
            "- Allarga META_OAUTH_SCOPES e rigenera il Page token, ad esempio:\n"
            "  META_OAUTH_SCOPES=pages_show_list,pages_manage_posts,pages_read_engagement\n"
            "  (rimuovi dalla lista i permessi che Meta segnala come «Invalid Scopes»), "
            "poi meta-oauth-page-token --oauth-rerequest "
            "(senza, Meta può riusare il vecchio consenso e la stringa del token resta uguale).\n"
            "- In alternativa: Graph API Explorer con gli stessi permessi abilitati → meta-refresh-page-token."
        )

    if "[190/" in msg or "(190/" in msg or "session is invalid" in lower:
        chunks.append(
            "\n\nToken (errore 190 / sessione non valida): token scaduto, revocato o non Page. "
            "Rigenera con meta-oauth-page-token o Explorer + meta-refresh-page-token; "
            "preferisci META_PAGE_TOKEN_FILE con path assoluto."
        )

    if (
        "[3/" in msg
        or "(#3)" in msg
        or "(3/" in msg
        or "whitelist" in lower
        or "must be on whitelist" in lower
    ):
        chunks.append(
            "\n\nInstagram Graph — errore #3 «User must be on whitelist»:\n"
            "- Di solito l’app è in **modalità Sviluppo** e l’account Instagram professionale usato "
            "non è tra i **ruoli / tester** dell’app, oppure la funzione richiesta (es. certi parametri "
            "su ``/media``) non è disponibile senza accesso avanzato / approvazione Meta.\n"
            "- In developers.facebook.com → la tua app → **Casi d’uso** (Instagram) / **Ruoli**: "
            "aggiungi il profilo Instagram come **Instagram Tester** (o collega l’app come da guida "
            "Instagram Graph per il tuo caso d’uso).\n"
            "- Se stai usando ``scheduled_publish_time`` su ``POST …/media``, prova invece "
            "``publish_time`` (nomenclatura diversa da Facebook Page); entrambi non garantiscono "
            "scheduling nativo IG affidabile con ``media_publish`` immediato.\n"
            "- Vedi anche ``docs/instagram_graph_api_scheduler_notes.md`` (pattern consigliato: "
            "container + ``media_publish`` all’orario dal tuo scheduler).\n"
            "- In **Live** con App Review completato le restrizioni «whitelist» tipiche del dev mode "
            "spesso spariscono per i permessi approvati."
        )

    return "".join(chunks)
