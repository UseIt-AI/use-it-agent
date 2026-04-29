import os
import uuid
import base64
from datetime import datetime, timedelta, timezone


def save_base64_image(base64_image, save_image_dir="./cache"):
    # get current time
    utc_plus_8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc_plus_8).strftime("%Y%m%d_%H%M%S")
    
    # save base64 encoded screenshot and get screenshot path
    image_path = os.path.join(save_image_dir, f"image_{current_time}.png")
    with open(image_path, "wb") as f:
        f.write(base64.b64decode(base64_image))
    return image_path