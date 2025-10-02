import os
import base64
from typing import Tuple

import numpy as np
import cv2

_paddle_clas_model = None


def _get_paddle_clas(model_name=None):
    """Lazy init and return PaddleClas classifier instance."""
    global _paddle_clas_model
    if _paddle_clas_model is None or model_name is not None:
        try:
            from paddleclas import PaddleClas
        except Exception as e:
            raise RuntimeError(f"Failed to import PaddleClas: {e}")
        # Use provided model_name or environment variable or default
        if model_name is None:
            model_name = os.getenv("PADDLECLAS_MODEL_NAME", "EfficientNetB0")
        _paddle_clas_model = PaddleClas(model_name=model_name, topk=5, use_gpu=False)
    return _paddle_clas_model


def paddle_has_cat_from_bytes(image_bytes: bytes, model_name: str = None) -> Tuple[bool, str]:
    try:
        nparr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, "failed to decode image"

        classifier = _get_paddle_clas(model_name)
        results = classifier.predict(img)
        has_cat = _labels_has_cat(results)
        return has_cat, ""
    except Exception as e:
        return False, str(e)


def paddle_has_cat_from_b64(b64_image: str, model_name: str = None) -> Tuple[bool, str]:
    try:
        image_bytes = base64.b64decode(b64_image)
        return paddle_has_cat_from_bytes(image_bytes, model_name)
    except Exception as e:
        return False, str(e)


def _labels_has_cat(results) -> bool:
    # results is a generator, need to iterate through it
    cat_keywords = [
        "cat", "kitten", "tomcat", "tabby", "tiger cat", "siamese", "persian",
        "egyptian cat", "lynx", "wildcat", "feline", "domestic cat", "house cat",
        "maine coon", "british shorthair", "ragdoll", "munchkin", "scottish fold",
        "bengal cat", "russian blue", "abyssinian", "birman", "oriental shorthair"
    ]
    
    # 添加其他毛茸茸动物关键词，这些也会被识别为猫
    furry_animal_keywords = [
        "dog", "puppy", "puppies", "canine", "hound", "terrier", "retriever",
        "shepherd", "spaniel", "poodle", "bulldog", "beagle", "chihuahua",
        "rabbit", "bunny", "hare", "hamster", "guinea pig", "gerbil",
        "ferret", "weasel", "mink", "otter", "raccoon", "raccoon dog",
        "fox", "red fox", "arctic fox", "wolf", "coyote", "jackal",
        "bear", "panda", "koala", "squirrel", "chipmunk", "marmot",
        "hedgehog", "porcupine", "skunk", "badger", "wolverine",
        "seal", "sea lion", "walrus", "otter", "beaver", "muskrat",
        "chinchilla", "capybara", "lemur", "monkey", "ape", "gorilla",
        "furry", "fluffy", "hairy", "fuzzy", "woolly", "downy"
    ]
    
    # 合并所有关键词
    all_keywords = cat_keywords + furry_animal_keywords
    
    # Convert generator to list to access the first result
    results_list = list(results)
    rt = False
    if len(results_list) > 0 and isinstance(results_list[0], dict):
        labels = results_list[0].get("label_names") or []
        labels_lc = [str(x).lower() for x in labels]
        rt = any(any(k in lbl for k in all_keywords) for lbl in labels_lc)
    else:
        # Fallback: search in string representation
        text = str(results_list).lower()
        rt = any(k in text for k in all_keywords)
    if not rt:
        print(f"No cat or furry animal found in {results_list}")
    return rt


