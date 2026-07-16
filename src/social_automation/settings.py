from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    """Root del repository (cartella che contiene `src/`)."""
    import os

    override = (os.environ.get("SOCIAL_AUTOMATION_ROOT") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        if p.is_dir() and (p / "src" / "social_automation").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    """Root del repository (cartella che contiene ``src/``)."""
    return _repo_root()


def _strip_env_value_quotes(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1].strip()
    return s


def resolve_meta_page_token_file_path(path_raw: str) -> Path | None:
    """
    Risolve ``META_PAGE_TOKEN_FILE``.

    Per path **relativi** prova prima la **root del repo** (stesso pacchetto di questo modulo),
    poi la cwd: così Streamlit non legge per errore un altro ``output/...`` nella cwd.
    """
    raw = _strip_env_value_quotes((path_raw or "").strip())
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve() if p.is_file() else None
    alt = _repo_root() / p
    if alt.is_file():
        return alt.resolve()
    if p.is_file():
        return p.resolve()
    return None


def default_meta_page_token_file() -> Path:
    """Path di default del file Page token nella root repo: ``output/meta_page_token.txt``."""
    return _repo_root() / "output" / "meta_page_token.txt"


def intended_meta_page_token_file_path(path_raw: str) -> Path | None:
    """
    Path assoluto previsto per ``META_PAGE_TOKEN_FILE`` (anche se il file non esiste ancora).

    Per path relativi usa la root del repo (come ``resolve_meta_page_token_file_path``).
    """
    raw = _strip_env_value_quotes((path_raw or "").strip())
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.expanduser().resolve()
    return (_repo_root() / p).resolve()


def _read_meta_page_token_file(fp: Path) -> str:
    """Prima riga non vuota / non commento; gestisce BOM e virgolette."""
    try:
        text = fp.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        t = _strip_env_value_quotes(line.strip())
        if t and not t.startswith("#"):
            return t
    return ""


def resolve_media_file_path(path_raw: str) -> Path | None:
    """
    Risolve un path di immagine salvato nel DB.

    Path relativi: prima root repo, poi cwd (evita file sbagliati se la cwd non è il progetto).
    """
    raw = (path_raw or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve() if p.is_file() else None
    alt = _repo_root() / p
    if alt.is_file():
        return alt.resolve()
    if p.is_file():
        return p.resolve()
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Prima il `.env` nella root del repo (Streamlit spesso ha cwd diversa),
        # poi quello nella cwd così le variabili locali possono sovrascrivere.
        env_file=(str(_repo_root() / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_drive_folder_id: str = Field(
        default="",
        description="Cartella principale Drive (opzionale se usi categories.yaml)",
    )
    google_credentials_path: Path = Field(
        default=Path("credentials.json"),
        description="JSON OAuth client Desktop da Google Cloud Console",
    )
    google_token_path: Path = Field(
        default=Path("token.json"),
        description="Token OAuth salvato dopo il primo login",
    )
    google_oauth_browser: str = Field(
        default="",
        description="Browser per OAuth (es. safari). Vuoto = browser predefinito di sistema",
    )

    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_redirect_uri: str = "http://127.0.0.1:8080/callback"
    canva_oauth_scopes: str = (
        "asset:read asset:write design:meta:read design:content:read "
        "design:content:write profile:read"
    )
    canva_token_path: Path = Field(
        default=Path("canva_token.json"),
        description="Token OAuth Canva salvato localmente",
    )
    canva_config_path: Path = Field(
        default=Path("config/canva.yaml"),
        description="Config YAML template Canva",
    )

    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_page_access_token: str = ""
    meta_user_access_token: str = Field(
        default="",
        description="User token (Explorer/OAuth) usato da meta-refresh-page-token; non loggare.",
    )
    meta_page_id: str = Field(
        default="",
        description="Id numerico Facebook Page (default opzionale per meta-refresh-page-token).",
    )
    meta_ig_user_id: str = ""
    meta_graph_version: str = Field(
        default="v22.0",
        description="Versione Graph API (es. v22.0)",
    )
    meta_page_token_file: str = Field(
        default="",
        description=(
            "Se non vuoto e il file esiste, il Page token viene letto da lì "
            "(override di META_PAGE_ACCESS_TOKEN dal .env; utile per cron). "
            "Path relativo: prima root del repo (pacchetto), poi cwd."
        ),
    )
    meta_redirect_uri: str = Field(
        default="http://127.0.0.1:8765/oauth/facebook/callback",
        description=(
            "Redirect OAuth Facebook Login (deve coincidere con «URI di reindirizzamento OAuth validi» "
            "nel pannello app Meta; usato da meta-oauth-page-token). "
            "Se Meta richiede HTTPS: usa https://… (ngrok) oppure https su localhost + certificati sotto."
        ),
    )
    meta_oauth_listen_port: int = Field(
        default=8765,
        description=(
            "Porta su cui il processo locale ascolta il callback. "
            "Con ngrok deve coincidere con `ngrok http QUESTA_PORTA`."
        ),
    )
    meta_oauth_tls_certfile: str = Field(
        default="",
        description="Path PEM certificato per https://127.0.0.1 (es. da mkcert); opzionale",
    )
    meta_oauth_tls_keyfile: str = Field(
        default="",
        description="Path PEM chiave privata per OAuth HTTPS locale; opzionale",
    )
    meta_oauth_scopes: str = Field(
        default="pages_show_list",
        description=(
            "Permessi OAuth Facebook Login per meta-oauth-page-token, separati da virgola "
            "(senza spazi). Per programmare post sulla Page servono permessi abilitati sull'app "
            "e scope coerenti (tipicamente pages_show_list,pages_manage_posts e se richiesto "
            "pages_read_engagement). Se il dialog OAuth risponde «Invalid Scopes», riduci la lista "
            "o abilita i permessi in developers.facebook.com. Vedi anche docs/meta-setup.md."
        ),
    )
    meta_oauth_auth_type: str = Field(
        default="",
        description=(
            "Opzionale: query auth_type del dialog Facebook Login (es. rerequest) per richiedere "
            "di nuovo i permessi dopo aver esteso META_OAUTH_SCOPES. Equivalente CLI: --oauth-rerequest."
        ),
    )
    meta_graph_http_trust_env: bool = Field(
        default=True,
        description=(
            "Se false, httpx non usa proxy da variabili d'ambiente per Graph API "
            "(evita TLS MITM da HTTPS_PROXY). Vedi META_GRAPH_HTTP_CA_BUNDLE per CA aziendale."
        ),
    )
    meta_graph_http_ca_bundle: str = Field(
        default="",
        description="Path opzionale a file PEM bundle CA per verificare TLS verso graph.facebook.com",
    )

    vision_api_key: str = ""
    vision_model: str = ""
    vision_api_base_url: str = Field(
        default="",
        description="Base URL API vision OpenAI-compatible (default: https://api.openai.com/v1)",
    )
    vision_http_trust_env: bool | None = Field(
        default=None,
        description=(
            "Se impostato, controlla proxy/TLS httpx verso OpenAI/Vision. "
            "Se omesso, usa META_GRAPH_HTTP_TRUST_ENV."
        ),
    )
    vision_http_ca_bundle: str = Field(
        default="",
        description=(
            "Path PEM bundle CA per TLS verso API OpenAI-compatible. "
            "Se vuoto, usa META_GRAPH_HTTP_CA_BUNDLE."
        ),
    )
    vision_brand_config_path: Path = Field(
        default=Path("config/vision_brand.yaml"),
        description="Prompt brand per validazione vision per categoria",
    )
    brand_knowledge_path: Path = Field(
        default=Path("config/brand/story_business_rules.md"),
        description=(
            "Layer 2 Business Rules (deprecato come nome: preferire STORY_BUSINESS_RULES_PATH). "
            "Fallback se story_business_rules.md assente."
        ),
    )
    story_system_path: Path = Field(
        default=Path("config/brand/story_system.md"),
        description="Layer 1 System Prompt: identità Story AI Assistant",
    )
    story_business_rules_path: Path = Field(
        default=Path("config/brand/story_business_rules.md"),
        description="Layer 2 Business Rules (tone, pillar, crop, editing, modalità operative)",
    )
    story_agent_config_path: Path = Field(
        default=Path("config/brand/story_agent.md"),
        description="Layer 3 User Task templates (/produce, /copy, /edit, /auto)",
    )
    visual_producer_prompt_path: Path = Field(
        default=Path("config/brand/image_edit_task_prompt.md"),
        description="Prompt task editing immagine post-selezione (Responses / images/edits)",
    )
    visual_hybrid_prompt_path: Path = Field(
        default=Path("config/brand/image_edit_hybrid_task_prompt.md"),
        description="Prompt AI in pipeline ibrida (solo nitidezza/pulizia; tono via Pillow).",
    )
    visual_image_model: str = Field(
        default="gpt-image-1",
        description="Modello OpenAI Images per editing (es. gpt-image-1, dall-e-2)",
    )
    visual_image_size: str = Field(
        default="",
        description="Dimensione output image edit (opzionale). Preferire vuoto/auto per preservare la foto originale.",
    )
    visual_image_input_fidelity: str = Field(
        default="high",
        description=(
            "input_fidelity per gpt-image-1/1.5 (Responses tool o images_edits). "
            "Preserva loghi/volti. Non usato con gpt-image-2."
        ),
    )
    visual_image_quality: str = Field(
        default="",
        description="Qualità output image edit (gpt-image-1: high | medium | low). Vuoto = default API.",
    )
    visual_image_backend: str = Field(
        default="responses",
        description=(
            "Backend ritocco AI: responses (come ChatGPT, consigliato) | images_edits (legacy diretto)."
        ),
    )
    visual_responses_model: str = Field(
        default="gpt-5.5",
        description="Modello mainline per Responses API + tool image_generation (es. gpt-5.5, gpt-4.1).",
    )
    visual_responses_image_model: str = Field(
        default="gpt-image-1.5",
        description=(
            "Modello immagine nel tool Responses (gpt-image-1.5 consigliato per loghi/testi; "
            "gpt-image-2 rigenera più spesso i dettagli)."
        ),
    )
    visual_produce_mode: str = Field(
        default="generative",
        description=(
            "Modalità /produce: generative (Responses API) | pixel (Vision JSON + Pillow, "
            "zero rigenerazione — loghi intatti al 100%)."
        ),
    )
    visual_review_enabled: bool = Field(
        default=False,
        description=(
            "Se false (default): flusso GPT diretto — foto + prompt editing, senza Visual Review "
            "né routing per score."
        ),
    )
    visual_edit_include_kb: bool = Field(
        default=True,
        description=(
            "Se true, allega KB brand nelle instructions API. Default true = come Custom GPT "
            "(system + business rules)."
        ),
    )
    visual_skip_post_crop: bool = Field(
        default=False,
        description=(
            "Se false (default), normalizza dimensioni con crop Pillow dopo l'API. "
            "Se true, output API usato così com'è."
        ),
    )
    visual_edit_plan_enabled: bool = Field(
        default=True,
        description=(
            "Se true (default), vision pre-edit produce un piano foto-specifico "
            "iniettato nel prompt (parità Custom GPT)."
        ),
    )
    visual_precrop_before_api: bool = Field(
        default=False,
        description=(
            "Pre-crop deterministico al formato social prima dell'edit AI. "
            "Default false = pipeline classica ai_edited (crop nel prompt + post-crop)."
        ),
    )
    visual_jpeg_export_quality: int = Field(
        default=95,
        ge=70,
        le=100,
        description="Qualità JPEG export post-API e file finali.",
    )
    visual_hybrid_tone_pipeline: bool = Field(
        default=False,
        description=(
            "Pipeline ibrida: AI per nitidezza selettiva/pulizia; Pillow applica exposure/contrast "
            "numerici dal piano vision. Default false = pipeline classica ai_edited."
        ),
    )
    visual_edit_prompt_compiler: bool = Field(
        default=False,
        description=(
            "Se true, il modello mainline riscrive il prompt prima della chiamata image tool. "
            "Default false = template diretto (come batch ai_edited)."
        ),
    )
    visual_edit_plan_model: str = Field(
        default="",
        description=(
            "Modello vision per Image Edit Plan. Vuoto = VISION_MODEL. "
            "Consigliato gpt-4o per analisi più precisa."
        ),
    )
    visual_gpt_pure_mode: bool = Field(
        default=False,
        description=(
            "Modalità A/B parità Custom GPT: foto originale, template classico, niente edit plan, "
            "pre-crop, compiler né tono Pillow; output API senza post-crop. Log revised_prompt."
        ),
    )
    visual_edit_debug_log: bool = Field(
        default=False,
        description="Se true, logga metadati payload edit (lunghezze prompt, tool params, hash).",
    )
    visual_review_score_use_original: float = Field(
        default=8.0,
        ge=0.0,
        le=10.0,
        description="Score >= valore → usa foto originale (solo crop formato)",
    )
    visual_review_score_manual: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Score < valore → flag review manuale prioritario",
    )
    visual_use_ai_image_edit: bool = Field(
        default=False,
        description=(
            "Se true, foto con score sotto soglia e needs_editing usano edit AI "
            "(Responses API o Images API). Default false: ritocco Pillow (/edit JSON)."
        ),
    )
    visual_disable_pillow_retouch: bool = Field(
        default=False,
        description=(
            "Con VISUAL_USE_AI_IMAGE_EDIT=true: disabilita fallback Pillow se l'edit AI fallisce. "
            "Non forza l'edit su foto già approvate (score >= soglia)."
        ),
    )

    dispatch_require_approval: bool = Field(
        default=True,
        description="Il dispatch automatico pubblica solo immagini con is_valid_for_publication=1",
    )
    dispatch_require_quality_pass: bool = Field(
        default=False,
        description="Se il gate ONNX è configurato, il dispatch richiede is_valid_by_quality_evaluation=1",
    )
    dispatch_require_vision_pass: bool = Field(
        default=False,
        description=(
            "Se vision è configurata, il dispatch richiede vision_eval_pass=1 "
            "(attualmente disattivato anche in dispatch_gates.py)"
        ),
    )

    schedule_config_path: Path = Field(
        default=Path("config/schedule.yaml"),
        description="Calendario editoriale (slot fissi IG/FB); fallback su schedule.example.yaml",
    )
    image_quality_borderline_margin: float = Field(
        default=0.15,
        ge=0.0,
        le=0.5,
        description="Margine sotto la soglia ONNX per considerare un'immagine «borderline»",
    )

    image_quality_onnx_path: str = Field(
        default="models/image-quality/image_scoring_model.onnx",
        description=(
            "Path modello ONNX qualità (relativo: root repo). "
            "Se il file non esiste, il gate qualità resta disattivato."
        ),
    )
    image_quality_class_names_path: str = Field(
        default="models/image-quality/class_names.json",
        description="Path class_names.json (relativo: root repo).",
    )
    image_quality_confidence_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Soglia sulla probabilità «good» per is_valid_by_quality_evaluation = 1",
    )

    app_timezone: str = Field(
        default="Europe/Rome",
        description="Fuso orario applicativo IANA (UI, pianificazione, dispatch)",
    )

    db_path: Path = Field(
        default=Path("output/social_automation.db"),
        description="SQLite locale per stato immagini/render/pianificazione",
    )
    db_backend: str = Field(
        default="sqlite",
        description="Backend DB: sqlite (dev) | postgres (Vercel/Neon)",
    )
    database_url: str = Field(
        default="",
        description="DATABASE_URL Postgres (Neon). Se vuoto, usa env DATABASE_URL.",
    )

    storage_backend: str = Field(
        default="local",
        description="Storage media: local | vercel_blob",
    )
    blob_read_write_token: str = Field(
        default="",
        description="Token Vercel Blob (BLOB_READ_WRITE_TOKEN)",
    )

    google_credentials_json: str = Field(
        default="",
        description="JSON OAuth client Google (sostituisce credentials.json su Vercel)",
    )
    google_refresh_token: str = Field(
        default="",
        description="Refresh token Google Drive (OAuth web)",
    )
    google_redirect_uri: str = Field(
        default="",
        description="Redirect URI OAuth Google web",
    )

    cron_secret: str = Field(
        default="",
        description="Secret per endpoint cron Vercel (CRON_SECRET)",
    )

    config_dir: Path = Field(default_factory=lambda: Path("config"))
    output_dir: Path = Field(default_factory=lambda: Path("output"))


def load_settings() -> Settings:
    import os

    s = Settings()
    updates: dict = {}
    if not (s.database_url or "").strip():
        env_db = (os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or "").strip()
        if env_db:
            updates["database_url"] = env_db
    if not (s.blob_read_write_token or "").strip():
        env_blob = (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()
        if env_blob:
            updates["blob_read_write_token"] = env_blob
    if not (s.cron_secret or "").strip():
        env_cron = (os.environ.get("CRON_SECRET") or "").strip()
        if env_cron:
            updates["cron_secret"] = env_cron
    if updates:
        s = s.model_copy(update=updates)
    path_raw = _strip_env_value_quotes((s.meta_page_token_file or "").strip())
    tok = ""
    if path_raw:
        fp = resolve_meta_page_token_file_path(path_raw)
        if fp is not None:
            tok = _read_meta_page_token_file(fp)
    if not tok:
        default_tok_path = default_meta_page_token_file()
        if default_tok_path.is_file():
            tok = _read_meta_page_token_file(default_tok_path)
    if tok:
        s = s.model_copy(update={"meta_page_access_token": tok})
    else:
        raw_pat = (s.meta_page_access_token or "").strip()
        if raw_pat:
            cleaned = _strip_env_value_quotes(raw_pat.splitlines()[0].strip())
            s = s.model_copy(update={"meta_page_access_token": cleaned})
    return s
