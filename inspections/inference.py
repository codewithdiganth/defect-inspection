from functools import lru_cache

from .validation import validate_image


@lru_cache(maxsize=1)
def _load_predict():
    from Model.inference import predict

    return predict


def run_inference(image_path):
    with open(image_path, "rb") as image_file:
        validate_image(image_file)
    result = _load_predict()(str(image_path))
    if isinstance(result, dict):
        try:
            predicted_class = result["predicted_class"]
            confidence = result["confidence"]
            defect_probability = result["defect_probability"]
            model_version = result["model_version"]
        except KeyError as error:
            raise ValueError(
                f"Model result is missing required field: {error.args[0]}"
            ) from error
    elif isinstance(result, (tuple, list)) and len(result) == 4:
        predicted_class, confidence, defect_probability, model_version = result
    else:
        raise ValueError("Model returned an unsupported prediction result.")

    if predicted_class not in {"Normal", "Defective"}:
        raise ValueError(f"Model returned unsupported class: {predicted_class!r}")
    try:
        confidence = float(confidence)
        defect_probability = float(defect_probability)
    except (TypeError, ValueError) as error:
        raise ValueError("Model returned invalid confidence values.") from error
    if not 0 <= confidence <= 1 or not 0 <= defect_probability <= 1:
        raise ValueError("Model returned confidence values outside the 0 to 1 range.")
    if not isinstance(model_version, str) or not model_version:
        raise ValueError("Model returned an invalid model version.")
    return predicted_class, confidence, defect_probability, model_version
