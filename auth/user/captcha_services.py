import uuid
import base64
import os
from django.core.cache import cache
from django.utils.crypto import get_random_string
from django.conf import settings
from captcha.image import ImageCaptcha

def generate_redis_captcha():
    """Generates a CAPTCHA, stores the text in Redis, and returns a base64 image."""
    # Define a standard, universally available Ubuntu font path
    linux_font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    
    # Fallback to default if the file isn't there yet
    fonts = [linux_font_path] if os.path.exists(linux_font_path) else None
    image_generator = ImageCaptcha(width=160, height=60, fonts=fonts)
    captcha_text = get_random_string(length=5, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    hashkey = uuid.uuid4().hex
    
    # Store the solution in Redis (expires automatically, no cleanup job needed)
    cache_timeout = getattr(settings, 'CAPTCHA_TIMEOUT', 300)
    cache.set(f"captcha_{hashkey}", captcha_text, timeout=cache_timeout)
    
    # Generate image bytes and convert to base64 for the frontend
    image_data = image_generator.generate(captcha_text)
    base64_image = base64.b64encode(image_data.getvalue()).decode('utf-8')
    
    return {
        'key': hashkey,
        'image_url': f"data:image/png;base64,{base64_image}"
    }

def verify_redis_captcha(hashkey: str, response: str) -> bool:
    """Verifies the CAPTCHA against Redis and deletes it ONLY on match success."""
    if not hashkey or not response:
        print("DEBUG CAPTCHA: Missing hashkey or response string payload.")
        return False
        
    cache_key = f"captcha_{hashkey}"
    cached_text = cache.get(cache_key)
    
    print(f"DEBUG CAPTCHA: Received Response='{response}' | Found Cached Text='{cached_text}'")
    
    if not cached_text:
        print("DEBUG CAPTCHA: Cache key was empty or has already expired.")
        return False  
        
    is_valid = cached_text.lower() == response.strip().lower()
    print(f"DEBUG CAPTCHA: Final validation evaluation match result = {is_valid}")
    
    # FIX: ONLY delete the key if it matches perfectly to prevent early deletion by middleware
    if is_valid:
        cache.delete(cache_key)
        
    return is_valid