from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FILE_SIZE = 5 * 1024 * 1024
MIN_DIMENSION = 64
MAX_DIMENSION = 4096
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 10
ACCEPTED_FORMATS = {"JPEG", "PNG"}


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    image_format: str
    width: int
    height: int


def validate_batch_size(file_count: int) -> None:
    if not MIN_BATCH_SIZE <= file_count <= MAX_BATCH_SIZE:
        raise ImageValidationError(
            f"Batch must contain between {MIN_BATCH_SIZE} and "
            f"{MAX_BATCH_SIZE} files."
        )


def validate_image(uploaded_file: BinaryIO) -> ValidatedImage:
    try:
        uploaded_file.seek(0)
        content = uploaded_file.read(MAX_FILE_SIZE + 1)
        uploaded_file.seek(0)
    except (OSError, ValueError) as error:
        raise ImageValidationError("File content could not be read") from error

    if not content:
        raise ImageValidationError("File is empty")
    if len(content) > MAX_FILE_SIZE:
        raise ImageValidationError("File exceeds 5 MiB; maximum is 5 MiB")
    if not isinstance(content, bytes):
        raise ImageValidationError("File content could not be read")

    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            image.verify()
    except UnidentifiedImageError as error:
        raise ImageValidationError(
            "File is not a valid JPEG or PNG image"
        ) from error
    except (
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        raise ImageValidationError("Image is truncated or corrupt") from error

    if image_format not in ACCEPTED_FORMATS:
        raise ImageValidationError("File is not a valid JPEG or PNG image")

    try:
        with Image.open(BytesIO(content)) as image:
            oriented_image = ImageOps.exif_transpose(image)
            width, height = oriented_image.size
            if not (
                MIN_DIMENSION <= width <= MAX_DIMENSION
                and MIN_DIMENSION <= height <= MAX_DIMENSION
            ):
                raise ImageValidationError(
                    f"Image is {width}x{height}; each dimension must be between "
                    f"{MIN_DIMENSION} and {MAX_DIMENSION} pixels"
                )
            oriented_image.load()
    except ImageValidationError:
        raise
    except (
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        raise ImageValidationError("Image is truncated or corrupt") from error

    return ValidatedImage(image_format, width, height)
