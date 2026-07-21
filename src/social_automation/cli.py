"""Entry point CLI. Uso: python -m social_automation"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from social_automation import __version__
from social_automation.app_timezone import now_app
from social_automation.canva.auth import normalize_scopes, run_canva_oauth
from social_automation.canva.client import CanvaClient
from social_automation.canva.templates import resolve_template_id
from social_automation.config_loaders import (
    load_canva_yaml,
    load_categories_yaml,
    load_category_aliases,
    load_schedule_yaml,
    resolve_drive_folder_id,
    resolve_schedule_path,
)
from social_automation.db.store import (
    add_planning_event,
    backfill_image_quality_evaluations,
    has_source_asset_render_for_platform,
    list_due_events,
    record_render_artifacts,
)
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import (
    apply_category_alias,
    infer_category_names,
    normalize_business_category,
    sort_assets_newest_first,
)
from social_automation.meta.client import MetaClient
from social_automation.meta.graph_hints import meta_graph_error_action_hint
from social_automation.meta.graph_httpx import graph_httpx_tls_params
from social_automation.meta.oauth_page_token import open_browser_for_page_token_oauth
from social_automation.meta.token_tools import (
    debug_input_token,
    persist_page_token_from_user_token,
)
from social_automation.models import (
    DriveAsset,
    MediaFormat,
    Platform,
)
from social_automation.pipeline.runner import PipelineContext, PipelineRunner
from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.scheduling.dispatch_runner import run_dispatch_scheduled
from social_automation.scheduling.prepare_week import prepare_week
from social_automation.scheduling.story_rules_dispatch import collect_due_story_rules
from social_automation.settings import (
    default_meta_page_token_file,
    intended_meta_page_token_file_path,
    load_settings,
    resolve_meta_page_token_file_path,
)
from social_automation.workflow.process_photo import process_drive_story_photo, process_local_photo

_DEFAULT_CATEGORIES_YAML = Path("config/categories.yaml")

_DRIVE_FOLDER_HELP = (
    "Specifica --folder-id, imposta GOOGLE_DRIVE_FOLDER_ID nel .env, "
    "oppure drive_root_folder_id in config/categories.yaml"
)


def _require_drive_folder_id(
    *,
    folder_id_arg: str,
    folder_id_env: str,
    categories_yaml: Path | None,
) -> str:
    fid = resolve_drive_folder_id(
        folder_id_arg=folder_id_arg,
        folder_id_env=folder_id_env,
        categories_yaml=categories_yaml,
    )
    if not fid:
        print(_DRIVE_FOLDER_HELP, file=sys.stderr)
        sys.exit(1)
    return fid


def _silence_httpx_token_logs() -> None:
    """Evita che httpx logghi URL con access_token in query (livello INFO)."""
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _configure_logging(*, verbose: bool, info_default: bool) -> None:
    """Attiva logging su stderr per comandi che producono output utile (es. render Canva)."""
    if verbose:
        level = logging.DEBUG
    elif info_default:
        level = logging.INFO
    else:
        return
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


_COMMANDS_WITH_PIPELINE_LOGS = frozenset({"canva-render-test", "publish-test", "meta-page"})


def _raw_categories_set(cat_cfg_path: Path) -> set[str]:
    categories_cfg = load_categories_yaml(cat_cfg_path) if cat_cfg_path.exists() else {}
    raw = {
        str(c).strip().lower()
        for c in categories_cfg.get("raw_categories", [])
        if str(c).strip()
    }
    return raw if raw else {"food", "beer", "peppe", "locale"}


def _pick_newest_asset_for_business_category(
    drive: DriveClient,
    folder_id: str,
    cat_cfg_path: Path,
    business_category: str,
    *,
    db_path: Path,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
) -> DriveAsset:
    raw_categories = _raw_categories_set(cat_cfg_path)
    aliases = load_category_aliases(cat_cfg_path) if cat_cfg_path.exists() else {}
    assets = drive.list_images_recursively(
        folder_id,
        category_names=infer_category_names(raw_categories, aliases),
    )
    ranked = sort_assets_newest_first(assets)
    target = normalize_business_category(business_category, aliases)
    for asset in ranked:
        if apply_category_alias(asset.category, aliases) != target:
            continue
        if has_source_asset_render_for_platform(
            db_path,
            source_asset_id=asset.file_id,
            platform=platform,
            media_format=media_format,
        ):
            continue
        return asset
    print(
        f"Nessun asset trovato per categoria business '{target}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def _caption_from_detail(detail: str | None) -> str:
    raw = (detail or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return str(payload.get("caption", "")).strip()
        except ValueError:
            return ""
    return ""


def _safe_scheduled_for(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Social media automation: Drive → Canva → Meta (IG/FB)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log più dettagliati (DEBUG), inclusi polling delle API Canva",
    )
    parser.add_argument(
        "--show-schedule",
        type=Path,
        metavar="YAML",
        help="Legge e stampa gli slot da un file schedule YAML",
    )

    sub = parser.add_subparsers(dest="command", help="Comandi")

    p_auth = sub.add_parser("drive-auth", help="Primo login Google Drive (salva token.json)")
    p_auth.add_argument(
        "--no-browser",
        action="store_true",
        help="Usa flusso console invece del browser locale",
    )
    p_auth.add_argument(
        "--browser",
        default="",
        metavar="NAME",
        help="Browser per l'URL OAuth (es. safari). Sovrascrive GOOGLE_OAUTH_BROWSER nel .env",
    )

    p_list = sub.add_parser(
        "drive-list-images",
        help="Elenca immagini in una cartella Drive (non ricorsivo)",
    )
    p_list.add_argument(
        "--folder-id",
        help=(
            "ID cartella Drive (se omesso: GOOGLE_DRIVE_FOLDER_ID o "
            "drive_root_folder_id in categories.yaml)"
        ),
    )
    p_list.add_argument(
        "--category",
        default="",
        help="Etichetta opzionale (es. burger) per output",
    )
    p_list_recursive = sub.add_parser(
        "drive-list-images-recursive",
        help="Elenca immagini in modo ricorsivo sotto una cartella root Drive",
    )
    p_list_recursive.add_argument(
        "--folder-id",
        help=(
            "ID root Drive (se omesso: GOOGLE_DRIVE_FOLDER_ID o "
            "drive_root_folder_id in categories.yaml)"
        ),
    )
    p_list_recursive.add_argument(
        "--categories",
        default="",
        help=(
            "Categorie separate da virgola da inferire dal path "
            "(es. food,peppe,beer)"
        ),
    )
    p_list_recent = sub.add_parser(
        "drive-list-recent",
        help="Elenca immagini ricorsive ordinando per anno/mese (più recenti prima)",
    )
    p_list_recent.add_argument(
        "--folder-id",
        help=(
            "ID root Drive (se omesso: GOOGLE_DRIVE_FOLDER_ID o "
            "drive_root_folder_id nel file --categories-config)"
        ),
    )
    p_list_recent.add_argument(
        "--categories",
        default="food,beer,peppe,locale",
        help="Categorie raw separate da virgola (default: food,beer,peppe,locale)",
    )
    p_list_recent.add_argument(
        "--categories-config",
        default="config/categories.yaml",
        help="YAML con category_aliases raw->business (default: config/categories.yaml)",
    )
    p_list_recent.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Numero massimo risultati da stampare (default: 100)",
    )
    p_canva_auth = sub.add_parser(
        "canva-auth",
        help="OAuth Canva Connect e salvataggio token locale",
    )
    p_canva_auth.add_argument(
        "--no-browser",
        action="store_true",
        help="Non apre il browser automaticamente (inserimento manuale code/URL)",
    )
    p_canva_auth.add_argument(
        "--scopes",
        default="",
        help=(
            "Scope Canva separati da spazio o virgola; "
            "se omesso usa CANVA_OAUTH_SCOPES dal .env"
        ),
    )
    sub.add_parser(
        "canva-profile",
        help="Verifica token Canva leggendo il profilo utente (scope profile:read)",
    )
    p_canva_render = sub.add_parser(
        "canva-render-test",
        help="Seleziona asset recente da Drive e produce render test Canva in output/",
    )
    p_canva_render.add_argument(
        "--folder-id",
        help=(
            "ID root Drive (se omesso: GOOGLE_DRIVE_FOLDER_ID o "
            "drive_root_folder_id in --categories-config)"
        ),
    )
    p_canva_render.add_argument(
        "--platform",
        required=True,
        choices=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
        help="Piattaforma target (instagram/facebook)",
    )
    p_canva_render.add_argument(
        "--format",
        default=MediaFormat.POST.value,
        choices=[MediaFormat.POST.value, MediaFormat.STORY.value],
        help=(
            "Formato render: 'post' (cartella per piattaforma) oppure 'story' "
            "(cartella unica 'stories', template condiviso IG/FB, 1080x1920)"
        ),
    )
    p_canva_render.add_argument(
        "--category",
        required=True,
        help="Categoria business target (es. boss, birra, food, locale)",
    )
    p_canva_render.add_argument(
        "--categories-config",
        default="config/categories.yaml",
        help="YAML categorie con alias raw->business",
    )
    p_canva_render.add_argument(
        "--canva-config",
        default="",
        help="YAML template Canva (se omesso usa CANVA_CONFIG_PATH)",
    )
    p_canva_render.add_argument(
        "--placeholder",
        action="store_true",
        help="Salta le API Canva e copia solo il file locale (debug / senza token)",
    )
    p_canva_render.add_argument(
        "--no-cover-crop",
        action="store_true",
        help="Non pre-ritagliare l'immagine in modalità «Riempi» prima dell'upload Canva",
    )

    p_publish = sub.add_parser(
        "publish-test",
        help="Drive → Canva → Meta: pubblica l'asset più recente della categoria",
    )
    p_publish.add_argument(
        "--folder-id",
        help=(
            "ID root Drive (se omesso: GOOGLE_DRIVE_FOLDER_ID o "
            "drive_root_folder_id in --categories-config)"
        ),
    )
    p_publish.add_argument(
        "--platform",
        required=True,
        choices=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
        help="Piattaforma (instagram o facebook)",
    )
    p_publish.add_argument(
        "--format",
        default=MediaFormat.POST.value,
        choices=[MediaFormat.POST.value, MediaFormat.STORY.value],
        help=(
            "Formato render. Per ora le storie vanno usate solo con --dry-run: "
            "la pubblicazione storie su Meta non e' ancora implementata."
        ),
    )
    p_publish.add_argument(
        "--category",
        required=True,
        help="Categoria business (es. food, boss)",
    )
    p_publish.add_argument(
        "--categories-config",
        default="config/categories.yaml",
        help="YAML categorie con alias raw->business",
    )
    p_publish.add_argument(
        "--canva-config",
        default="",
        help="YAML template Canva (se omesso usa CANVA_CONFIG_PATH)",
    )
    p_publish.add_argument(
        "--caption",
        default="",
        help="Didascalia del post (Instagram/Facebook)",
    )
    p_publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo Drive + Canva, non chiamare Meta",
    )
    p_publish.add_argument(
        "--skip-validation",
        action="store_true",
        help="Salta il gate vision (utile finché la validazione non è implementata)",
    )
    p_publish.add_argument(
        "--placeholder",
        action="store_true",
        help="Salta le API Canva (copia file) — solo per prove",
    )
    p_publish.add_argument(
        "--no-cover-crop",
        action="store_true",
        help="Disabilita pre-ritaglio cover prima di Canva",
    )
    p_dispatch = sub.add_parser(
        "dispatch-scheduled",
        help="Pubblica gli eventi pianificati scaduti dal DB verso Meta",
    )
    p_dispatch.add_argument(
        "--platform",
        choices=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
        default="",
        help="Filtra la piattaforma target",
    )
    p_dispatch.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Numero massimo di eventi da elaborare (default: 50)",
    )
    p_dispatch.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra gli eventi scaduti senza pubblicare su Meta",
    )
    p_dispatch.add_argument(
        "--ignore-gates",
        action="store_true",
        help="Disattiva temporaneamente i gate approvazione/qualità/vision sul dispatch",
    )

    p_prepare = sub.add_parser(
        "prepare-week",
        help="Workflow settimanale: render, qualità, vision, approvazione e pianificazione slot",
    )
    p_prepare.add_argument(
        "--schedule",
        default="",
        help="Path schedule YAML (default: SCHEDULE_CONFIG_PATH o config/schedule.yaml)",
    )
    p_prepare.add_argument(
        "--days",
        type=int,
        default=7,
        help="Giorni da coprire a partire da ora (default: 7)",
    )
    p_prepare.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula senza render né scrittura pianificazione",
    )
    p_prepare.add_argument(
        "--no-render",
        action="store_true",
        help="Non tentare processamento Drive→Story AI per slot senza immagini",
    )

    p_story = sub.add_parser(
        "story-process",
        help="Drive → Story AI (ritocco + copy) → export foto per Meta",
    )
    p_story.add_argument(
        "--category",
        required=True,
        help="Categoria business (food, beer, peppe, locale, …)",
    )
    p_story.add_argument(
        "--platform",
        choices=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
        default=Platform.INSTAGRAM.value,
    )
    p_story.add_argument(
        "--format",
        dest="media_format",
        choices=[MediaFormat.POST.value, MediaFormat.STORY.value],
        default=MediaFormat.POST.value,
    )
    p_story.add_argument(
        "--mode",
        choices=["auto", "retouch_copy"],
        default="auto",
        help="auto = ritocco+copy in una chiamata; retouch_copy = due chiamate",
    )
    p_story.add_argument(
        "--source",
        default="",
        help="Path immagine locale (salta download Drive)",
    )

    p_img_quality = sub.add_parser(
        "image-quality-evaluate",
        help=(
            "Aggiorna valutazione qualità ONNX su images: flag validità, classe predetta, confidenza."
        ),
    )
    p_img_quality.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Numero massimo di righe images da elaborare per esecuzione (default: 200)",
    )
    p_img_quality.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset nella lista ordinata per id DESC (default: 0)",
    )
    p_img_quality.add_argument(
        "--all-rows",
        action="store_true",
        help=(
            "Rivaluta anche righe già punteggiate "
            "(default: solo righe senza quality_predicted_class)."
        ),
    )

    sub.add_parser(
        "meta-page",
        help="Verifica META_PAGE_ACCESS_TOKEN e stampa id/nome della Facebook Page",
    )
    p_meta_sched = sub.add_parser(
        "meta-scheduled-posts",
        help="Elenca post programmati sulla Page (GET /{page-id}/scheduled_posts)",
    )
    p_meta_sched.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Numero massimo di elementi (1–100, default 25)",
    )
    p_meta_sched.add_argument(
        "--graph-no-proxy",
        action="store_true",
        help="Ignora HTTP_PROXY/HTTPS_PROXY verso graph.facebook.com.",
    )
    p_meta_ig_test = sub.add_parser(
        "meta-test-ig-media-params",
        help=(
            "Test POST /{ig-user-id}/media con parametri extra (es. publish_time): "
            "solo creazione container, senza media_publish. Richiede image_url HTTPS pubblica."
        ),
    )
    p_meta_ig_test.add_argument(
        "--image-url",
        required=True,
        help="URL HTTPS pubblico dell'immagine (requisito API Instagram).",
    )
    p_meta_ig_test.add_argument(
        "--caption",
        default="Test parametri scheduling (CLI meta-test-ig-media-params).",
        help="Didascalia del media container.",
    )
    p_meta_ig_test.add_argument(
        "--unix-time",
        type=int,
        default=None,
        help=(
            "Se impostato, aggiunge al body il parametro indicato da --extra-param "
            "(Unix secondi, come stringa nel form)."
        ),
    )
    p_meta_ig_test.add_argument(
        "--extra-param",
        choices=("publish_time", "scheduled_publish_time"),
        default="publish_time",
        help="Nome del parametro da testare insieme a --unix-time (default: publish_time).",
    )
    p_meta_ig_test.add_argument(
        "--graph-no-proxy",
        action="store_true",
        help="Ignora HTTP_PROXY/HTTPS_PROXY verso graph.facebook.com.",
    )
    p_meta_debug = sub.add_parser(
        "meta-debug-token",
        help=(
            "GET /debug_token sul Page token (META_APP_ID + META_APP_SECRET): "
            "mostra scope effettivi e validità del token"
        ),
    )
    p_meta_debug.add_argument(
        "--token",
        default="",
        help="Page access token (se omesso: stesso caricamento di meta-page da .env / file)",
    )
    p_meta_debug.add_argument(
        "--graph-no-proxy",
        action="store_true",
        help="Ignora HTTP_PROXY/HTTPS_PROXY verso graph.facebook.com.",
    )
    p_meta_clear = sub.add_parser(
        "meta-clear-page-token",
        help=(
            "Elimina i file locali del Page token (prima di meta-oauth-page-token). "
            "Non revoca il token lato Meta; serve a non riusare un token vecchio da file."
        ),
    )
    p_meta_clear.add_argument(
        "--yes",
        action="store_true",
        help="Conferma: elimina i file token trovati (senza --yes viene solo mostrato cosa verrebbe rimosso)",
    )
    p_meta_refresh = sub.add_parser(
        "meta-refresh-page-token",
        help=(
            "Rinnova Page token: scambia user token in long-lived (META_APP_*), "
            "legge me/accounts e scrive il Page token su file (cron-friendly)"
        ),
    )
    p_meta_refresh.add_argument(
        "--user-token",
        default="",
        help="User access token (se omesso usa META_USER_ACCESS_TOKEN dal .env)",
    )
    p_meta_refresh.add_argument(
        "--page-id",
        default="",
        help="Id numerico della Page (se omesso usa META_PAGE_ID o una sola Page in elenco)",
    )
    p_meta_refresh.add_argument(
        "--skip-exchange",
        action="store_true",
        help="Non chiamare fb_exchange_token (usa direttamente il user token come già long-lived)",
    )
    p_meta_refresh.add_argument(
        "--write-token-file",
        default="output/meta_page_token.txt",
        help="Path file dove salvare solo il Page token (default: output/meta_page_token.txt)",
    )
    p_meta_refresh.add_argument(
        "--print-token",
        action="store_true",
        help="Stampa il Page token in chiaro su stdout (disabilita se redirezioni i log)",
    )
    p_meta_refresh.add_argument(
        "--graph-no-proxy",
        action="store_true",
        help=(
            "Ignora HTTP_PROXY/HTTPS_PROXY per graph.facebook.com "
            "(se compare CERTIFICATE_VERIFY_FAILED verso Meta)."
        ),
    )
    p_meta_oauth = sub.add_parser(
        "meta-oauth-page-token",
        help=(
            "Facebook Login nel browser: callback su META_REDIRECT_URI, poi Page token su file "
            "(richiede Facebook Login + redirect URI registrato nell'app Meta)"
        ),
    )
    p_meta_oauth.add_argument(
        "--page-id",
        default="",
        help="Id numerico della Page (se omesso usa META_PAGE_ID o una sola Page in elenco)",
    )
    p_meta_oauth.add_argument(
        "--write-token-file",
        default="output/meta_page_token.txt",
        help="Path file dove salvare solo il Page token (default: output/meta_page_token.txt)",
    )
    p_meta_oauth.add_argument(
        "--no-browser",
        action="store_true",
        help="Non aprire il browser: stampa solo l'URL da aprire manualmente",
    )
    p_meta_oauth.add_argument(
        "--oauth-timeout",
        type=float,
        default=300.0,
        help="Secondi di attesa per il callback OAuth (default: 300)",
    )
    p_meta_oauth.add_argument(
        "--scopes",
        default="",
        help=(
            "Scope separati da virgola (se omesso: META_OAUTH_SCOPES dal .env, default pages_show_list)"
        ),
    )
    p_meta_oauth.add_argument(
        "--graph-no-proxy",
        action="store_true",
        help=(
            "Ignora HTTP_PROXY/HTTPS_PROXY per le chiamate a graph.facebook.com "
            "(se compare CERTIFICATE_VERIFY_FAILED: proxy MITM o SSL inspection)."
        ),
    )
    p_meta_oauth.add_argument(
        "--oauth-rerequest",
        action="store_true",
        help=(
            "Aggiunge auth_type=rerequest al dialog Facebook: mostra di nuovo la schermata permessi "
            "(dopo aver esteso META_OAUTH_SCOPES; altrimenti Meta può riusare il consenso precedente)."
        ),
    )

    args = parser.parse_args()

    _configure_logging(
        verbose=bool(args.verbose),
        info_default=(args.command in _COMMANDS_WITH_PIPELINE_LOGS),
    )

    if args.show_schedule:
        sched = load_schedule_yaml(args.show_schedule)
        print(f"timezone={sched.timezone}")
        for s in sched.slots:
            plats = ", ".join(p.value for p in s.platforms)
            print(f"  {s.weekday} {s.time_hhmm} → {plats}")
        return

    settings = load_settings()

    if args.command == "drive-auth":
        oauth_browser = (args.browser or settings.google_oauth_browser or "").strip() or None
        DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=not args.no_browser,
            oauth_browser=oauth_browser,
        )
        print(f"Token salvato in {settings.google_token_path.resolve()}")
        return

    if args.command == "drive-list-images":
        folder_id = _require_drive_folder_id(
            folder_id_arg=args.folder_id or "",
            folder_id_env=settings.google_drive_folder_id,
            categories_yaml=_DEFAULT_CATEGORIES_YAML,
        )
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        client = DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )
        cat = args.category.strip() or None
        assets = client.list_images_in_folder(folder_id, category=cat)
        if not assets:
            print("(nessuna immagine in questa cartella)")
            return
        for a in assets:
            suffix = f"  [{a.category}]" if a.category else ""
            print(f"{a.file_id}\t{a.mime_type}\t{a.name}{suffix}")
        return

    if args.command == "drive-list-images-recursive":
        folder_id = _require_drive_folder_id(
            folder_id_arg=args.folder_id or "",
            folder_id_env=settings.google_drive_folder_id,
            categories_yaml=_DEFAULT_CATEGORIES_YAML,
        )
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        client = DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )
        raw_categories = [c.strip() for c in args.categories.split(",") if c.strip()]
        categories = set(raw_categories) if raw_categories else None
        assets = client.list_images_recursively(folder_id, category_names=categories)
        if not assets:
            print("(nessuna immagine trovata sotto la root)")
            return
        for a in assets:
            suffix = f"  [{a.category}]" if a.category else ""
            print(f"{a.file_id}\t{a.mime_type}\t{a.name}{suffix}")
        return

    if args.command == "canva-auth":
        if not settings.canva_client_id.strip() or not settings.canva_client_secret.strip():
            print(
                "Imposta CANVA_CLIENT_ID e CANVA_CLIENT_SECRET nel .env prima di continuare.",
                file=sys.stderr,
            )
            sys.exit(1)
        scopes_raw = (args.scopes or settings.canva_oauth_scopes).strip()
        scopes = normalize_scopes(scopes_raw)
        if not scopes:
            print("Nessuno scope Canva impostato.", file=sys.stderr)
            sys.exit(1)
        token_path = run_canva_oauth(
            client_id=settings.canva_client_id.strip(),
            client_secret=settings.canva_client_secret.strip(),
            redirect_uri=settings.canva_redirect_uri.strip(),
            scopes=scopes,
            token_path=settings.canva_token_path,
            open_browser=not args.no_browser,
        )
        print(f"Token Canva salvato in {token_path.resolve()}")
        return

    if args.command == "canva-profile":
        client = CanvaClient.from_token_file(
            settings.canva_client_id.strip(),
            settings.canva_client_secret.strip(),
            settings.canva_redirect_uri.strip(),
            settings.canva_token_path,
        )
        profile = client.get_profile()
        print(profile)
        return

    if args.command == "drive-list-recent":
        aliases_path = Path(args.categories_config)
        folder_id = _require_drive_folder_id(
            folder_id_arg=args.folder_id or "",
            folder_id_env=settings.google_drive_folder_id,
            categories_yaml=aliases_path,
        )
        categories = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
        aliases: dict[str, str] = {}
        if aliases_path.exists():
            aliases = load_category_aliases(aliases_path)
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        client = DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )
        assets = client.list_images_recursively(folder_id, category_names=categories)
        ranked = sort_assets_newest_first(assets)
        if args.limit > 0:
            ranked = ranked[: args.limit]
        if not ranked:
            print("(nessuna immagine trovata sotto la root)")
            return
        for a in ranked:
            raw_cat = a.category
            biz_cat = apply_category_alias(raw_cat, aliases)
            cat_txt = f"{raw_cat}->{biz_cat}" if raw_cat else "-"
            path_txt = "/".join(a.path_segments) if a.path_segments else "-"
            print(f"{a.file_id}\t{a.mime_type}\t{a.name}\t[{cat_txt}]\t{path_txt}")
        return

    if args.command == "canva-render-test":
        cat_cfg_path = Path(args.categories_config)
        platform = Platform(args.platform)
        media_format = MediaFormat(args.format)
        aliases = load_category_aliases(cat_cfg_path) if cat_cfg_path.exists() else {}
        folder_id = _require_drive_folder_id(
            folder_id_arg=args.folder_id or "",
            folder_id_env=settings.google_drive_folder_id,
            categories_yaml=cat_cfg_path,
        )
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        drive_client = DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )
        target_business_category = normalize_business_category(args.category, aliases)
        selected = _pick_newest_asset_for_business_category(
            drive_client,
            folder_id,
            cat_cfg_path,
            args.category,
            db_path=settings.db_path,
            platform=platform,
            media_format=media_format,
        )
        canva_cfg_path = (
            Path(args.canva_config) if args.canva_config else settings.canva_config_path
        )
        if not canva_cfg_path.exists():
            print(
                f"Config Canva non trovata: {canva_cfg_path}. "
                "Copia config/canva.example.yaml in config/canva.yaml e inserisci template ID.",
                file=sys.stderr,
            )
            sys.exit(1)
        canva_cfg = load_canva_yaml(canva_cfg_path)
        template_id = resolve_template_id(
            canva_cfg,
            platform=platform.value,
            category=target_business_category,
            media_format=media_format,
        )
        if not template_id:
            print(
                f"Nessun template Canva configurato per platform={platform.value} "
                f"category={target_business_category} format={media_format.value}.",
                file=sys.stderr,
            )
            sys.exit(1)
        output_dir = settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
        source_path = output_dir / f"drive_{selected.file_id}{suffix}"
        source_path.write_bytes(drive_client.download_file_bytes(selected.file_id))

        canva_client = CanvaClient.from_token_file(
            settings.canva_client_id.strip(),
            settings.canva_client_secret.strip(),
            settings.canva_redirect_uri.strip(),
            settings.canva_token_path,
        )
        rendered = canva_client.render_for_platform(
            source_path,
            platform,
            template_id=template_id,
            output_dir=output_dir / "canva-rendered",
            output_stem=f"{target_business_category}_{selected.file_id}",
            use_placeholder=bool(args.placeholder),
            precrop_cover=not bool(args.no_cover_crop),
            media_format=media_format,
        )
        render_metadata = canva_client.get_last_render_metadata() or {}
        image_id = record_render_artifacts(
            settings.db_path,
            image_name=selected.name,
            image_path=rendered,
            source_asset_id=selected.file_id,
            source_asset_name=selected.name,
            business_category=target_business_category,
            metadata_payload=render_metadata,
        )
        print(f"selected_asset={selected.file_id}\t{selected.name}")
        print(f"template_id={template_id}")
        print(f"media_format={media_format.value}")
        print(f"rendered_file={rendered}")
        print(f"db_image_id={image_id}")
        return

    if args.command == "meta-page":
        _silence_httpx_token_logs()
        if not settings.meta_page_access_token.strip():
            print(
                "META_PAGE_ACCESS_TOKEN mancante (e nessun META_PAGE_TOKEN_FILE valido).",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_tf = (settings.meta_page_token_file or "").strip()
        if raw_tf:
            resolved = resolve_meta_page_token_file_path(raw_tf)
            if resolved is None:
                print(
                    f"Attenzione: META_PAGE_TOKEN_FILE={raw_tf!r} non trovato "
                    f"(cwd={Path.cwd()}). "
                    "Si sta usando META_PAGE_ACCESS_TOKEN dal .env, che potrebbe essere scaduto.",
                    file=sys.stderr,
                )
            elif args.verbose:
                print(f"meta-page: token da file {resolved}", file=sys.stderr)
        meta = MetaClient(
            settings.meta_page_access_token.strip(),
            settings.meta_ig_user_id.strip(),
            graph_version=(settings.meta_graph_version or "v22.0").strip(),
            settings=settings,
        )
        try:
            print(meta.get_page_profile())
        except RuntimeError as e:
            err = str(e)
            if "190/" in err or "[190/" in err:
                print(
                    "\nSuggerimento: errore 190 spesso indica token scaduto/revocato o ancora un "
                    "**user token** nel .env. Verifica META_PAGE_TOKEN_FILE (path assoluto consigliato), "
                    "lascia vuoto META_PAGE_ACCESS_TOKEN se usi solo il file, e rilancia "
                    "`meta-oauth-page-token` oppure `meta-refresh-page-token` con un user token fresco da Explorer.",
                    file=sys.stderr,
                )
            elif ("[200/" in err) or ("(200/" in err):
                print(meta_graph_error_action_hint(err), file=sys.stderr)
            elif (
                ("100/" in err or "[100/" in err)
                and (settings.meta_page_id or "").strip()
            ):
                pid = (settings.meta_page_id or "").strip()
                print(
                    "meta-page: Graph non restituisce il profilo Page (es. manca "
                    "`pages_read_engagement` o feature in App Review). "
                    "Per pubblicare/pianificare l'app usa META_PAGE_ID dal .env senza questa GET.",
                    file=sys.stderr,
                )
                print({"id": pid, "name": None, "graph_page_profile": "unavailable"})
                return
            raise
        return

    if args.command == "meta-scheduled-posts":
        _silence_httpx_token_logs()
        if not settings.meta_page_access_token.strip():
            print(
                "META_PAGE_ACCESS_TOKEN mancante (e nessun META_PAGE_TOKEN_FILE valido).",
                file=sys.stderr,
            )
            sys.exit(1)
        lim = max(1, min(int(getattr(args, "limit", 25) or 25), 100))
        graph_settings = (
            settings.model_copy(update={"meta_graph_http_trust_env": False})
            if getattr(args, "graph_no_proxy", False)
            else settings
        )
        if getattr(args, "graph_no_proxy", False):
            print(
                "graph-no-proxy: META_GRAPH_HTTP_TRUST_ENV disattivato per questa esecuzione.",
                file=sys.stderr,
            )
        meta = MetaClient(
            settings.meta_page_access_token.strip(),
            settings.meta_ig_user_id.strip(),
            graph_version=(settings.meta_graph_version or "v22.0").strip(),
            settings=graph_settings,
        )
        try:
            data = meta.list_page_scheduled_posts(limit=lim)
        except RuntimeError as e:
            err = str(e)
            if "[283/" in err or "283/" in err or "pages_read_engagement" in err.lower():
                print(
                    "Suggerimento: GET scheduled_posts può richiedere permessi di lettura sulla Page "
                    "(es. pages_read_engagement). Il post programmato può esistere comunque: "
                    "controlla dalla Pagina Facebook classica o in Business Suite con ritardo.",
                    file=sys.stderr,
                )
            raise
        print(json.dumps(data, indent=2, ensure_ascii=False))
        rows = data.get("data") or []
        if isinstance(rows, list) and rows:
            print("\nSintesi (orario di uscita in UTC):", file=sys.stderr)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rid = row.get("id", "")
                ts = row.get("scheduled_publish_time")
                if isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(int(ts), tz=UTC)
                    print(f"  {rid}\n    → {dt.isoformat()} UTC", file=sys.stderr)
                elif ts is not None:
                    print(f"  {rid}\n    → scheduled_publish_time={ts!r}", file=sys.stderr)
                else:
                    print(f"  {rid}", file=sys.stderr)
        print(
            "\nNota: i post creati con il flusso feed + attached_media dovrebbero comparire nel Planner "
            "di Business Suite. Se l'array data è vuoto, verifica permessi di lettura o la Page selezionata.",
            file=sys.stderr,
        )
        return

    if args.command == "meta-test-ig-media-params":
        _silence_httpx_token_logs()
        if not settings.meta_page_access_token.strip():
            print(
                "META_PAGE_ACCESS_TOKEN mancante (e nessun META_PAGE_TOKEN_FILE valido).",
                file=sys.stderr,
            )
            sys.exit(1)
        ig_id = (settings.meta_ig_user_id or "").strip()
        if not ig_id:
            print("META_IG_USER_ID mancante nel .env.", file=sys.stderr)
            sys.exit(1)
        image_url = (getattr(args, "image_url", "") or "").strip()
        caption = (getattr(args, "caption", "") or "").strip()
        if not caption:
            caption = "Test parametri (meta-test-ig-media-params)."
        unix_ts = getattr(args, "unix_time", None)
        extra_name = (getattr(args, "extra_param", "publish_time") or "publish_time").strip()
        graph_settings = (
            settings.model_copy(update={"meta_graph_http_trust_env": False})
            if getattr(args, "graph_no_proxy", False)
            else settings
        )
        if getattr(args, "graph_no_proxy", False):
            print(
                "graph-no-proxy: META_GRAPH_HTTP_TRUST_ENV disattivato per questa esecuzione.",
                file=sys.stderr,
            )
        gv = (settings.meta_graph_version or "v22.0").strip().lstrip("/") or "v22.0"
        url = f"https://graph.facebook.com/{gv}/{ig_id}/media"
        tok = settings.meta_page_access_token.strip()
        data: dict[str, str] = {
            "access_token": tok,
            "image_url": image_url,
            "caption": caption,
        }
        if unix_ts is not None:
            data[extra_name] = str(int(unix_ts))
        print("Richiesta (senza valore del token):", file=sys.stderr)
        print(f"  POST {url}", file=sys.stderr)
        print(
            "  form: "
            + ", ".join(
                f"{k}={v!r}" if k != "access_token" else "access_token=<omesso>"
                for k, v in sorted(data.items())
            ),
            file=sys.stderr,
        )
        tls = graph_httpx_tls_params(graph_settings)
        with httpx.Client(**tls) as client:
            r = client.post(url, data=data, timeout=120.0)
        try:
            body = r.json()
        except Exception:
            body = {"_non_json": (r.text or "")[:4000]}
        out = {"http_status": r.status_code, "body": body}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            em = str((body["error"] or {}).get("message") or body["error"])
            hint = meta_graph_error_action_hint(em)
            if hint:
                print(hint, file=sys.stderr)
        print(
            "\nNota: non è stato chiamato media_publish; il container IG scade in ~24h se inutilizzato.",
            file=sys.stderr,
        )
        if r.status_code >= 400:
            sys.exit(1)
        return

    if args.command == "meta-debug-token":
        _silence_httpx_token_logs()
        app_id = settings.meta_app_id.strip()
        app_secret = settings.meta_app_secret.strip()
        if not app_id or not app_secret:
            print(
                "Servono META_APP_ID e META_APP_SECRET nel .env per debug_token.",
                file=sys.stderr,
            )
            sys.exit(1)
        tok = (getattr(args, "token", "") or "").strip()
        if not tok and not settings.meta_page_access_token.strip():
            print(
                "Nessun Page token: META_PAGE_ACCESS_TOKEN vuoto e nessun META_PAGE_TOKEN_FILE valido.",
                file=sys.stderr,
            )
            sys.exit(1)
        if not tok:
            tok = settings.meta_page_access_token.strip()
        gv = (settings.meta_graph_version or "v22.0").strip()
        graph_settings = (
            settings.model_copy(update={"meta_graph_http_trust_env": False})
            if getattr(args, "graph_no_proxy", False)
            else settings
        )
        if getattr(args, "graph_no_proxy", False):
            print(
                "graph-no-proxy: META_GRAPH_HTTP_TRUST_ENV disattivato per questa esecuzione.",
                file=sys.stderr,
            )
        try:
            out = debug_input_token(
                input_token=tok,
                app_id=app_id,
                app_secret=app_secret,
                graph_version=gv,
                settings=graph_settings,
            )
        except RuntimeError as e:
            err = str(e)
            if ("[200/" in err) or ("(200/" in err):
                print(meta_graph_error_action_hint(err), file=sys.stderr)
            raise
        print(json.dumps(out, indent=2, ensure_ascii=False))
        print(
            "\nCerca in data.scopes (o granular_scopes) voci come pages_manage_posts; "
            "se mancano, il token è stato emesso senza quei permessi: rifai OAuth / Explorer.",
            file=sys.stderr,
        )
        return

    if args.command == "meta-clear-page-token":
        s = settings
        candidates: list[Path] = []
        raw_tf = (s.meta_page_token_file or "").strip()
        if raw_tf:
            ip = intended_meta_page_token_file_path(raw_tf)
            if ip is not None:
                candidates.append(ip)
        candidates.append(default_meta_page_token_file().resolve())
        uniq: list[Path] = []
        seen: set[Path] = set()
        for p in candidates:
            r = p.resolve()
            if r not in seen:
                seen.add(r)
                uniq.append(p)
        existing = [p for p in uniq if p.is_file()]
        if not existing:
            print(
                "meta-clear-page-token: nessun file token trovato sul disco "
                f"(candidati: {', '.join(str(p) for p in uniq)}).",
                file=sys.stderr,
            )
            print(
                "Se il token è solo in META_PAGE_ACCESS_TOKEN nel .env, commenta o svuota quella riga a mano.",
                file=sys.stderr,
            )
            return
        if not args.yes:
            print(
                "meta-clear-page-token: i seguenti file verrebbero eliminati:\n  "
                + "\n  ".join(str(p) for p in existing),
                file=sys.stderr,
            )
            print(
                "Rilancia con --yes per eliminarli. Poi svuota META_PAGE_ACCESS_TOKEN nel .env se presente, "
                "imposta META_OAUTH_SCOPES con pages_manage_posts, e meta-oauth-page-token.",
                file=sys.stderr,
            )
            sys.exit(1)
        for p in existing:
            p.unlink()
            print(f"eliminato: {p}")
        print(
            "\nProssimi passi: nel .env rimuovi o commenta META_PAGE_ACCESS_TOKEN se lo usavi; "
            "verifica META_OAUTH_SCOPES=pages_show_list,pages_manage_posts,pages_read_engagement; "
            "poi PYTHONPATH=src python -m social_automation meta-oauth-page-token",
        )
        return

    if args.command == "meta-refresh-page-token":
        _silence_httpx_token_logs()
        app_id = settings.meta_app_id.strip()
        app_secret = settings.meta_app_secret.strip()
        if not app_id or not app_secret:
            print(
                "Servono META_APP_ID e META_APP_SECRET nel .env per lo scambio token.",
                file=sys.stderr,
            )
            sys.exit(1)
        user_token = (args.user_token or settings.meta_user_access_token or "").strip()
        if not user_token:
            print(
                "Passa --user-token oppure imposta META_USER_ACCESS_TOKEN nel .env "
                "(token utente da Graph API Explorer, con permessi sulle Page).",
                file=sys.stderr,
            )
            sys.exit(1)
        gv = (settings.meta_graph_version or "v22.0").strip()
        page_id_arg = (args.page_id or settings.meta_page_id or "").strip() or None
        out_path = Path(args.write_token_file)
        graph_settings = (
            settings.model_copy(update={"meta_graph_http_trust_env": False})
            if getattr(args, "graph_no_proxy", False)
            else settings
        )
        if getattr(args, "graph_no_proxy", False):
            print(
                "graph-no-proxy: META_GRAPH_HTTP_TRUST_ENV disattivato per questa esecuzione.",
                file=sys.stderr,
            )
        exchange_info, row = persist_page_token_from_user_token(
            user_access_token=user_token,
            app_id=app_id,
            app_secret=app_secret,
            graph_version=gv,
            page_id=page_id_arg,
            skip_exchange=bool(args.skip_exchange),
            output_path=out_path,
            settings=graph_settings,
        )
        if args.skip_exchange:
            print("skip_exchange=true (nessuna chiamata fb_exchange_token)")
        elif exchange_info:
            print(f"user_token_long_lived_ok\texpires_in_seconds={exchange_info.get('expires_in')}")
        print(
            f"page_token_file_written\tpath={out_path.resolve()}\t"
            f"page_id={row.get('id')}\tpage_name={row.get('name')}"
        )
        print(
            "Imposta nel .env: META_PAGE_TOKEN_FILE="
            f"{out_path.resolve()} "
            "(e puoi lasciare vuoto META_PAGE_ACCESS_TOKEN se preferisci solo il file)."
        )
        if args.print_token:
            print(out_path.read_text(encoding="utf-8").strip())
        return

    if args.command == "meta-oauth-page-token":
        _silence_httpx_token_logs()
        app_id = settings.meta_app_id.strip()
        app_secret = settings.meta_app_secret.strip()
        if not app_id or not app_secret:
            print(
                "Servono META_APP_ID e META_APP_SECRET nel .env per OAuth Facebook.",
                file=sys.stderr,
            )
            sys.exit(1)
        redirect = (settings.meta_redirect_uri or "").strip()
        if not redirect:
            print("META_REDIRECT_URI non impostato nel .env.", file=sys.stderr)
            sys.exit(1)
        gv = (settings.meta_graph_version or "v22.0").strip()
        scopes_arg = (args.scopes or settings.meta_oauth_scopes or "").strip()
        effective_scopes = scopes_arg or "pages_show_list"
        oauth_auth = ""
        if getattr(args, "oauth_rerequest", False):
            oauth_auth = "rerequest"
        else:
            oauth_auth = (settings.meta_oauth_auth_type or "").strip()
        graph_settings = (
            settings.model_copy(update={"meta_graph_http_trust_env": False})
            if getattr(args, "graph_no_proxy", False)
            else settings
        )
        if getattr(args, "graph_no_proxy", False):
            print(
                "graph-no-proxy: META_GRAPH_HTTP_TRUST_ENV disattivato per questa esecuzione "
                "(nessun proxy da variabili d'ambiente verso graph.facebook.com).",
                file=sys.stderr,
            )
        print(
            f"OAuth scope nel dialog: {effective_scopes}",
            file=sys.stderr,
        )
        if oauth_auth:
            print(
                f"OAuth auth_type nel dialog: {oauth_auth}",
                file=sys.stderr,
            )
        print(
            f"OAuth: apri il browser e accetta i permessi. "
            f"Callback atteso su: {redirect}\n"
            "(Deve coincidere con un «URI di reindirizzamento OAuth validi» dell'app Meta.)"
        )
        user_short = open_browser_for_page_token_oauth(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect,
            graph_version=gv,
            scopes=scopes_arg or None,
            auth_type=oauth_auth,
            timeout_s=float(args.oauth_timeout),
            open_browser=not bool(args.no_browser),
            listen_port=int(settings.meta_oauth_listen_port),
            ssl_certfile=(settings.meta_oauth_tls_certfile or "").strip(),
            ssl_keyfile=(settings.meta_oauth_tls_keyfile or "").strip(),
            settings=graph_settings,
        )
        page_id_arg = (args.page_id or settings.meta_page_id or "").strip() or None
        out_path = Path(args.write_token_file)
        exchange_info, row = persist_page_token_from_user_token(
            user_access_token=user_short,
            app_id=app_id,
            app_secret=app_secret,
            graph_version=gv,
            page_id=page_id_arg,
            skip_exchange=False,
            output_path=out_path,
            settings=graph_settings,
        )
        print(f"user_token_long_lived_ok\texpires_in_seconds={exchange_info.get('expires_in')}")
        print(
            f"page_token_file_written\tpath={out_path.resolve()}\t"
            f"page_id={row.get('id')}\tpage_name={row.get('name')}"
        )
        print(
            "Imposta nel .env: META_PAGE_TOKEN_FILE="
            f"{out_path.resolve()} "
            "(e META_REDIRECT_URI come sopra per i prossimi login)."
        )
        return

    if args.command == "publish-test":
        cat_cfg_path = Path(args.categories_config)
        folder_id = _require_drive_folder_id(
            folder_id_arg=args.folder_id or "",
            folder_id_env=settings.google_drive_folder_id,
            categories_yaml=cat_cfg_path,
        )
        platform = Platform(args.platform)
        media_format = MediaFormat(args.format)
        if not args.dry_run:
            if not settings.meta_page_access_token.strip():
                print(
                    "META_PAGE_ACCESS_TOKEN mancante nel .env (oppure usa --dry-run).",
                    file=sys.stderr,
                )
                sys.exit(1)
            if platform == Platform.INSTAGRAM and not settings.meta_ig_user_id.strip():
                print(
                    "Per --platform instagram serve META_IG_USER_ID "
                    "(account Instagram collegato alla Facebook Page).",
                    file=sys.stderr,
                )
                sys.exit(1)
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        drive_client = DriveClient.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )
        selected = _pick_newest_asset_for_business_category(
            drive_client,
            folder_id,
            cat_cfg_path,
            args.category,
            db_path=settings.db_path,
            platform=platform,
            media_format=media_format,
        )
        canva_cfg_path = (
            Path(args.canva_config) if args.canva_config else settings.canva_config_path
        )
        if not canva_cfg_path.exists():
            print(
                f"Config Canva non trovata: {canva_cfg_path}. "
                "Copia config/canva.example.yaml in config/canva.yaml.",
                file=sys.stderr,
            )
            sys.exit(1)
        canva_cfg = load_canva_yaml(canva_cfg_path)
        target_business_category = args.category.strip().lower()
        template_id = resolve_template_id(
            canva_cfg,
            platform=platform.value,
            category=target_business_category,
            media_format=media_format,
        )
        if not template_id:
            print(
                f"Nessun template Canva per platform={platform.value} "
                f"category={target_business_category} format={media_format.value}.",
                file=sys.stderr,
            )
            sys.exit(1)
        output_dir = settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        canva_client = CanvaClient.from_token_file(
            settings.canva_client_id.strip(),
            settings.canva_client_secret.strip(),
            settings.canva_redirect_uri.strip(),
            settings.canva_token_path,
        )
        ctx = PipelineContext(
            category=target_business_category,
            platform=platform,
            chosen_asset=selected,
            media_format=media_format,
        )
        if args.dry_run:
            suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
            source_path = output_dir / f"drive_{selected.file_id}{suffix}"
            source_path.write_bytes(drive_client.download_file_bytes(selected.file_id))
            rendered = canva_client.render_for_platform(
                source_path,
                platform,
                template_id=template_id,
                output_dir=output_dir / "canva-rendered",
                output_stem=f"{target_business_category}_{selected.file_id}",
                use_placeholder=bool(args.placeholder),
                precrop_cover=not bool(args.no_cover_crop),
                media_format=media_format,
            )
            render_metadata = canva_client.get_last_render_metadata() or {}
            image_id = record_render_artifacts(
                settings.db_path,
                image_name=selected.name,
                image_path=rendered,
                source_asset_id=selected.file_id,
                source_asset_name=selected.name,
                business_category=target_business_category,
                metadata_payload=render_metadata,
            )
            print(
                f"dry_run=true\tselected={selected.file_id}\t"
                f"format={media_format.value}\trendered={rendered}"
            )
            print(f"db_image_id={image_id}")
            return
        meta = MetaClient(
            settings.meta_page_access_token.strip(),
            settings.meta_ig_user_id.strip(),
            graph_version=(settings.meta_graph_version or "v22.0").strip(),
            settings=settings,
        )
        runner = PipelineRunner(
            drive_client,
            canva_client,
            meta,
            vision_api_key=settings.vision_api_key,
            vision_model=settings.vision_model,
            vision_api_base_url=settings.vision_api_base_url,
            output_dir=output_dir,
        )
        result = runner.run_to_publish(
            ctx,
            template_id=template_id,
            caption=args.caption,
            skip_validation=bool(args.skip_validation),
            precrop_cover=not bool(args.no_cover_crop),
            use_placeholder=bool(args.placeholder),
        )
        if not result.ok:
            print(f"publish_failed\t{result.detail}", file=sys.stderr)
            sys.exit(1)
        if not result.rendered_path:
            print("publish_failed\tNessun file renderizzato disponibile", file=sys.stderr)
            sys.exit(1)
        rendered_path = Path(result.rendered_path)
        image_id = record_render_artifacts(
            settings.db_path,
            image_name=selected.name,
            image_path=rendered_path,
            source_asset_id=selected.file_id,
            source_asset_name=selected.name,
            business_category=target_business_category,
            metadata_payload=(canva_client.get_last_render_metadata() or {}),
        )
        print(f"selected_asset={selected.file_id}\t{selected.name}")
        print(f"rendered_file={rendered_path}")
        print(f"meta_external_id={result.external_id}")
        add_planning_event(
            settings.db_path,
            image_id=image_id,
            platform=platform,
            event_type="published",
            external_id=str(result.external_id or ""),
            detail="publish-test",
        )
        print(f"db_image_id={image_id}")
        return

    if args.command == "image-quality-evaluate":
        try:
            stats = backfill_image_quality_evaluations(
                settings.db_path,
                limit=int(args.limit),
                offset=int(args.offset),
                only_unscored=not bool(args.all_rows),
            )
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(
            f"updated={stats['updated']}\tskipped={stats['skipped']}\terrors={stats['errors']}\t"
            f"db={settings.db_path}"
        )
        return

    if args.command == "story-process":
        platform = Platform(args.platform)
        media_format = MediaFormat(args.media_format)
        mode = str(args.mode)
        try:
            if args.source:
                src = Path(args.source)
                if not src.is_file():
                    print(f"File non trovato: {src}", file=sys.stderr)
                    sys.exit(1)
                out = process_local_photo(
                    src,
                    platform=platform,
                    media_format=media_format,
                    business_category=str(args.category),
                    settings=settings,
                    mode=mode,  # type: ignore[arg-type]
                )
            else:
                out = process_drive_story_photo(
                    category=str(args.category),
                    platform=platform,
                    media_format=media_format,
                    settings=settings,
                    mode=mode,  # type: ignore[arg-type]
                )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        print(f"db_image_id={out['image_id']}")
        print(f"processed_file={out['processed_file']}")
        print(f"copy={json.dumps(out.get('copy') or {}, ensure_ascii=False)}")
        return

    if args.command == "prepare-week":
        sched_path = (
            Path(args.schedule)
            if args.schedule
            else resolve_schedule_path(settings.schedule_config_path)
        )
        if not sched_path.is_file():
            print(f"Schedule non trovato: {sched_path}", file=sys.stderr)
            sys.exit(1)
        try:
            result = prepare_week(
                schedule_path=sched_path,
                settings=settings,
                days=int(args.days),
                dry_run=bool(args.dry_run),
                try_render=not bool(args.no_render),
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        print(
            f"prepare_week\tplanned={result.planned}\tprocessed={result.processed}\t"
            f"rendered={result.rendered}\t"
            f"auto_approved={result.auto_approved}\tvision_evaluated={result.vision_evaluated}\t"
            f"skipped_quality={result.skipped_quality}\tskipped_borderline={result.skipped_borderline}\t"
            f"skipped_no_asset={result.skipped_no_asset}\tdry_run={bool(args.dry_run)}"
        )
        for a in result.assignments:
            print(
                f"assign\timage_id={a['image_id']}\tplatform={a['platform']}\t"
                f"when={a['scheduled_for']}\tcategory={a.get('category') or ''}"
            )
        for err in result.errors:
            print(f"error\t{err}", file=sys.stderr)
        if result.errors and result.planned == 0 and result.rendered == 0:
            sys.exit(1)
        return

    if args.command == "dispatch-scheduled":
        platform_filter = Platform(args.platform) if args.platform else None
        limit_n = max(1, int(args.limit))
        dispatch_settings = settings
        if getattr(args, "ignore_gates", False):
            dispatch_settings = settings.model_copy(
                update={
                    "dispatch_require_approval": False,
                    "dispatch_require_quality_pass": False,
                    "dispatch_require_vision_pass": False,
                }
            )
        due_events = list_due_events(
            dispatch_settings.db_path,
            due_before=now_app(dispatch_settings),
            platform=platform_filter,
            limit=limit_n,
        )
        utc_now = datetime.now(UTC)
        due_story = collect_due_story_rules(
            dispatch_settings.db_path,
            now=utc_now,
            platform=platform_filter,
            limit=limit_n,
        )

        if args.dry_run:
            print(
                f"dry_run=true\tplanning_events_due={len(due_events)}\tstory_rules_due={len(due_story)}"
            )
            for row in due_events:
                ok, reason = check_image_dispatch_gates(row, dispatch_settings)
                gate = "pass" if ok else f"BLOCKED:{reason}"
                print(
                    f"event_id={row['id']}\timage_id={row['image_id']}\t"
                    f"platform={row['platform']}\tscheduled_for={row['scheduled_for']}\tgate={gate}"
                )
            for s in due_story:
                print(
                    f"story_rule_id={s['rule_id']}\timage_id={s['image_id']}\t"
                    f"platform={s['platform'].value}\tmode={s['schedule_mode']}\t"
                    f"occurrence={s['occurrence_key']}\tslot={s['slot_label']}"
                )
            if not due_events and not due_story:
                print("Nessun evento pianificato scaduto né regola story da applicare.")
            return

        if not due_events and not due_story:
            print("Nessun evento pianificato scaduto né regola story da applicare.")
            return
        if not dispatch_settings.meta_page_access_token.strip():
            print(
                "META_PAGE_ACCESS_TOKEN mancante nel .env.",
                file=sys.stderr,
            )
            sys.exit(1)
        meta = MetaClient(
            dispatch_settings.meta_page_access_token.strip(),
            dispatch_settings.meta_ig_user_id.strip(),
            graph_version=(dispatch_settings.meta_graph_version or "v22.0").strip(),
            settings=dispatch_settings,
        )
        run_result = run_dispatch_scheduled(
            dispatch_settings,
            meta,
            platform=platform_filter,
            limit=limit_n,
        )
        for line in run_result.skip_reasons:
            print(f"skipped\t{line}")
        print(
            f"dispatch_completed\tplanning_published={run_result.planning_published}\t"
            f"planning_failed={run_result.planning_failed}\tplanning_skipped={run_result.planning_skipped}\t"
            f"story_published={run_result.story_published}\tstory_failed={run_result.story_failed}\t"
            f"story_skipped_reserve={run_result.story_skipped_reserve}"
        )
        if run_result.planning_failed > 0 or run_result.story_failed > 0:
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
