"""Orchestrazione: Drive → Canva → validazione → Meta."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from social_automation.canva.client import CanvaClient
from social_automation.drive.client import DriveClient
from social_automation.meta.client import MetaClient
from social_automation.models import (
    DriveAsset,
    MediaFormat,
    PipelineStep,
    Platform,
    PublishResult,
    ValidationResult,
)
from social_automation.validation.image_gate import validate_image_for_publish

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    category: str
    platform: Platform
    chosen_asset: DriveAsset | None = None
    rendered_path: Path | None = None
    step: PipelineStep = PipelineStep.SELECT_CATEGORY
    media_format: MediaFormat = MediaFormat.POST


class PipelineRunner:
    """Flusso end-to-end con retry lato client HTTP (Meta, ecc.)."""

    def __init__(
        self,
        drive: DriveClient,
        canva: CanvaClient,
        meta: MetaClient,
        *,
        vision_api_key: str,
        vision_model: str,
        output_dir: Path,
        vision_api_base_url: str = "",
    ) -> None:
        self._drive = drive
        self._canva = canva
        self._meta = meta
        self._vision_api_key = vision_api_key
        self._vision_model = vision_model
        self._vision_api_base_url = vision_api_base_url
        self._output_dir = output_dir

    def run_to_publish(
        self,
        ctx: PipelineContext,
        *,
        template_id: str | None,
        caption: str,
        skip_validation: bool = False,
        precrop_cover: bool = True,
        use_placeholder: bool = False,
    ) -> PublishResult:
        """Scarica asset → render Canva → (validazione) → pubblica su Meta."""
        if ctx.chosen_asset is None:
            return PublishResult(
                ok=False,
                platform=ctx.platform,
                detail="Nessun asset selezionato",
            )
        try:
            logger.info(
                "Pipeline: download Drive file_id=%s → render Canva",
                ctx.chosen_asset.file_id,
            )
            ctx.step = PipelineStep.CANVA_RENDER
            self._output_dir.mkdir(parents=True, exist_ok=True)
            suffix = mimetypes.guess_extension(ctx.chosen_asset.mime_type) or ".jpg"
            local_src = self._output_dir / f"src_{ctx.chosen_asset.file_id}{suffix}"
            local_src.write_bytes(
                self._drive.download_file_bytes(ctx.chosen_asset.file_id)
            )
            ctx.rendered_path = self._canva.render_for_platform(
                local_src,
                ctx.platform,
                template_id=template_id,
                output_dir=self._output_dir / "canva-rendered",
                output_stem=f"{ctx.category}_{ctx.chosen_asset.file_id}",
                precrop_cover=precrop_cover,
                use_placeholder=use_placeholder,
                media_format=ctx.media_format,
            )
            logger.info("Pipeline: render salvato in %s", ctx.rendered_path)
            ctx.step = PipelineStep.VALIDATE_IMAGE
            if skip_validation:
                v = ValidationResult(True, reason="Validazione saltata (skip_validation=True)")
            else:
                v = validate_image_for_publish(
                    ctx.rendered_path,
                    ctx.platform,
                    api_key=self._vision_api_key,
                    model=self._vision_model,
                    api_base_url=self._vision_api_base_url,
                    business_category=ctx.category,
                )
            if not v.success:
                return PublishResult(
                    ok=False,
                    platform=ctx.platform,
                    rendered_path=ctx.rendered_path,
                    validation=v,
                    detail=v.reason,
                )
            logger.info("Pipeline: pubblicazione Meta (%s)", ctx.platform.value)
            ctx.step = PipelineStep.META_PUBLISH
            ext_id = self._meta.publish_image(
                ctx.platform,
                ctx.rendered_path,
                caption,
                media_format=ctx.media_format.value,
            )
            ctx.step = PipelineStep.DONE
            logger.info("Pipeline: completata (external_id=%s)", ext_id)
            return PublishResult(
                ok=True,
                platform=ctx.platform,
                rendered_path=ctx.rendered_path,
                validation=v,
                external_id=ext_id,
                detail="Pubblicazione Meta completata",
            )
        except OSError as e:
            return PublishResult(
                ok=False,
                platform=ctx.platform,
                rendered_path=ctx.rendered_path,
                detail=f"Errore file: {e}",
            )
        except Exception as e:
            return PublishResult(
                ok=False,
                platform=ctx.platform,
                rendered_path=ctx.rendered_path,
                detail=str(e),
            )

    def run_until_valid_or_abort(
        self,
        ctx: PipelineContext,
        *,
        template_id: str | None = None,
        max_attempts: int = 5,
    ) -> ValidationResult:
        """Loop: render → validate; su FAIL torna a richiedere nuovo asset (esterno)."""
        for attempt in range(max_attempts):
            if ctx.chosen_asset is None:
                return ValidationResult(False, reason="Nessun asset selezionato")
            ctx.step = PipelineStep.CANVA_RENDER
            self._output_dir.mkdir(parents=True, exist_ok=True)
            suffix = mimetypes.guess_extension(ctx.chosen_asset.mime_type) or ".jpg"
            local_src = self._output_dir / f"src_{ctx.chosen_asset.file_id}{suffix}"
            local_src.write_bytes(
                self._drive.download_file_bytes(ctx.chosen_asset.file_id)
            )
            ctx.rendered_path = self._canva.render_for_platform(
                local_src,
                ctx.platform,
                template_id=template_id,
                output_dir=self._output_dir / "canva-rendered",
                output_stem=f"{ctx.category}_{ctx.chosen_asset.file_id}",
            )
            ctx.step = PipelineStep.VALIDATE_IMAGE
            result = validate_image_for_publish(
                ctx.rendered_path,
                ctx.platform,
                api_key=self._vision_api_key,
                model=self._vision_model,
                api_base_url=self._vision_api_base_url,
                business_category=ctx.category,
            )
            if result.success:
                ctx.step = PipelineStep.SCHEDULE
                return result
            ctx.step = PipelineStep.SELECT_ASSET
            ctx.chosen_asset = None
            _ = attempt
        return ValidationResult(False, reason="Max tentativi validazione")
