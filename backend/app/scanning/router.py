import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.collections.models import Collection, CollectionPiece
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.scanning.ml_client import BrickognizeAdapter
from app.scanning.models import Scan, ScanResult, ScanStatus
from app.scanning.schemas import (
    ScanConfirmRequest,
    ScanCreate,
    ScanCreateResponse,
    ScanResponse,
    ScanResultResponse,
)

router = APIRouter(prefix="/scans", tags=["scans"])

ml_client = BrickognizeAdapter()


def _get_s3_client():
    kwargs = {
        "region_name": settings.aws_region,
    }
    if settings.aws_s3_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_s3_endpoint_url
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
    if settings.aws_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def generate_presigned_url(s3_key: str, expires_in: int = 300) -> str:
    """Generate a presigned S3 PUT URL for the client to upload the image."""
    s3 = _get_s3_client()
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": s3_key, "ContentType": "image/jpeg"},
        ExpiresIn=expires_in,
    )
    return url


def generate_download_url(s3_key: str, expires_in: int = 300) -> str:
    """Generate a presigned S3 GET URL for the ML service to download the image."""
    s3 = _get_s3_client()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )
    return url


def _build_scan_response(
    scan: Scan, results: list[ScanResult], threshold: float
) -> ScanResponse:
    result_responses = [
        ScanResultResponse(
            id=r.id,
            part_num=r.part_num,
            color_id=r.color_id,
            confidence=r.confidence,
            bbox=r.bbox,
            user_verified=r.user_verified,
            needs_review=r.confidence < threshold,
        )
        for r in results
    ]
    return ScanResponse(
        id=scan.id,
        collection_id=scan.collection_id,
        status=scan.status,
        created_at=scan.created_at,
        results=result_responses,
    )


async def _get_user_scan(
    scan_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Scan:
    result = await db.execute(
        select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


@router.post("", response_model=ScanCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    body: ScanCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanCreateResponse:
    # Verify the collection belongs to this user
    result = await db.execute(
        select(Collection).where(
            Collection.id == body.collection_id,
            Collection.user_id == user.id,
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    s3_key = f"scans/{user.id}/{uuid.uuid4()}.jpg"

    scan = Scan(
        id=uuid.uuid4(),
        collection_id=body.collection_id,
        user_id=user.id,
        s3_key=s3_key,
        status=ScanStatus.PENDING,
        photo_consent=body.photo_consent,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    upload_url = generate_presigned_url(s3_key)

    return ScanCreateResponse(
        id=scan.id,
        upload_url=upload_url,
        s3_key=s3_key,
    )


@router.post("/{scan_id}/process", response_model=ScanResponse)
async def process_scan(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    scan = await _get_user_scan(scan_id, user, db)

    if scan.status not in (ScanStatus.PENDING, ScanStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scan is already in status {scan.status}",
        )

    scan.status = ScanStatus.PROCESSING
    await db.commit()

    try:
        image_url = generate_download_url(scan.s3_key)
        predictions = await ml_client.predict(image_url, str(scan.id))

        for pred in predictions:
            scan_result = ScanResult(
                id=uuid.uuid4(),
                scan_id=scan.id,
                part_num=pred.part_num,
                color_id=pred.color_id,
                confidence=pred.confidence,
                bbox=pred.bbox,
                user_verified=False,
            )
            db.add(scan_result)

        scan.status = ScanStatus.COMPLETED
        await db.commit()
        # Reload results (avoid lazy-load in async context)
        results_query = await db.execute(
            select(ScanResult).where(ScanResult.scan_id == scan.id)
        )
        loaded_results = list(results_query.scalars().all())

    except Exception:
        scan.status = ScanStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ML processing failed",
        )

    return _build_scan_response(scan, loaded_results, settings.confidence_threshold)


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    scan = await _get_user_scan(scan_id, user, db)

    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_id == scan.id)
    )
    loaded_results = list(result.scalars().all())

    return _build_scan_response(scan, loaded_results, settings.confidence_threshold)


@router.post("/{scan_id}/confirm", response_model=ScanResponse)
async def confirm_scan(
    scan_id: uuid.UUID,
    body: ScanConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    scan = await _get_user_scan(scan_id, user, db)

    if scan.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scan must be in COMPLETED status to confirm",
        )

    # Load all results for this scan indexed by id
    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_id == scan.id)
    )
    all_results = {r.id: r for r in result.scalars().all()}

    for item in body.items:
        scan_result = all_results.get(item.scan_result_id)
        if scan_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ScanResult {item.scan_result_id} not found",
            )

        # Apply any corrections
        if item.corrected_part_num is not None:
            scan_result.user_correction_part = item.corrected_part_num
        if item.corrected_color_id is not None:
            scan_result.user_correction_color = item.corrected_color_id
        scan_result.user_verified = True

        if not item.accepted:
            continue

        # Determine the actual part/color to add (use corrections if provided)
        effective_part = item.corrected_part_num if item.corrected_part_num is not None else scan_result.part_num
        effective_color = item.corrected_color_id if item.corrected_color_id is not None else scan_result.color_id

        # Upsert into collection_pieces
        cp_result = await db.execute(
            select(CollectionPiece).where(
                CollectionPiece.collection_id == scan.collection_id,
                CollectionPiece.part_num == effective_part,
                CollectionPiece.color_id == effective_color,
            )
        )
        existing_piece = cp_result.scalar_one_or_none()
        if existing_piece is not None:
            existing_piece.quantity += 1
        else:
            new_piece = CollectionPiece(
                id=uuid.uuid4(),
                collection_id=scan.collection_id,
                part_num=effective_part,
                color_id=effective_color,
                quantity=1,
            )
            db.add(new_piece)

    await db.commit()

    # Reload scan results (avoid lazy-load in async context)
    result = await db.execute(
        select(ScanResult).where(ScanResult.scan_id == scan.id)
    )
    loaded_results = list(result.scalars().all())

    return _build_scan_response(scan, loaded_results, settings.confidence_threshold)
