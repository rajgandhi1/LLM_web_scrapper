import json
import requests
from app.streamlit_web_scraper_chat import StreamlitWebScraperChat
from src.scrapers.playwright_scraper import ScraperConfig
from typing import List, Dict, Optional
import csv
from bs4 import BeautifulSoup
import re
from playwright.async_api import async_playwright
import asyncio
from playwright.sync_api import sync_playwright
import random
from PIL import Image
from io import BytesIO

# def query_model(prompt, model_name="llama3.1:8b"):
#     """
#     Query the Ollama server with a prompt and return the response.

#     Args:
#         prompt (str): The prompt to send to the model.
#         model_name (str): The name of the model to use.

#     Returns:
#         str: The model's response.
#     """
#     url = "http://127.0.0.1:11434/api/generate"
#     headers = {"Content-Type": "application/json"}
#     payload = {"prompt": prompt, "model": model_name}

#     try:
#         response = requests.post(url, headers=headers, json=payload, stream=True)
#         response.raise_for_status()

#         # Process streamed JSON objects
#         full_response = ""
#         for line in response.iter_lines():
#             if line:  # Skip empty lines
#                 try:
#                     json_data = json.loads(line)
#                     if "response" in json_data:
#                         full_response += json_data["response"]
#                 except json.JSONDecodeError as e:
#                     print(f"Error decoding JSON line: {e}")

#         return full_response

#     except requests.RequestException as e:
#         return f"Error querying the model: {e}"

def query_model(prompt, model_name="gpt-4o-mini"):
    """
    Query OpenAI's GPT-4 model with a prompt and return the response.
    """
    import openai
    import os

    # Get API key from environment variable
    openai.api_key = os.getenv('OPENAI_API_KEY')

    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts and formats product information. Always respond with valid JSON containing the requested fields."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent output
            max_tokens=1000
        )
        
        if response and response.choices:
            return response.choices[0].message.content.strip()
        else:
            print("No response received from OpenAI")
            return "{}"  # Return empty JSON string instead of None

    except Exception as e:
        print(f"Error querying the model: {e}")
        return "{}"  # Return empty JSON string instead of None


def verify_image_url(url: str) -> bool:
    try:
        response = requests.head(url, timeout=5)
        return (response.status_code == 200 and 
                'image' in response.headers.get('content-type', ''))
    except:
        return False

def is_product_image(url: str, alt_text: Optional[str] = None) -> bool:
    # Check for common logo-related keywords in the URL or alt text
    logo_keywords = ["logo", "brand", "company", "icon", "header", "menu", "home"]
    if any(keyword in (alt_text or "").lower() for keyword in logo_keywords):
        return False  # This is likely a company logo
    if any(keyword in url.lower() for keyword in logo_keywords):
        return False  # This is likely a company logo
    return True  # This is likely a product image

def verify_image_size(url: str) -> bool:
    try:
        # Fetch image headers
        response = requests.get(url, stream=True, timeout=5)
        response.raise_for_status()

        # Open the image and check its dimensions
        img = Image.open(BytesIO(response.content))
        width, height = img.size
        
        # Check if the image dimensions are at least 400x400 pixels
        return width >= 500 and height >= 500
    except Exception as e:
        print(f"Error verifying image size: {e}")
        return False

def extract_images(html_content: str) -> List[str]:
    # Ensure we're working with string content
    if not isinstance(html_content, str):
        return []
        
    # Skip if content doesn't look like HTML
    if not any(tag in html_content.lower() for tag in ['<html', '<body', '<div']):
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')
    image_urls = []

    # Select all img and picture elements
    images = soup.find_all(['img', 'picture'])
    
    for img in images:
        # Extract src or srcset for img tags
        if img.name == 'img':
            url = img.get('src') or img.get('data-src') or img.get('srcset')
            alt_text = img.get('alt', '')
            if url and is_product_image(url, alt_text):
                # Handle relative URLs
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    domain_match = re.search(r'https?://[^/]+', html_content)
                    if domain_match:
                        url = domain_match.group(0) + url
                
                # Check if URL is valid, not already added, and has a valid size
                if verify_image_url(url) and verify_image_size(url) and url not in image_urls:
                    image_urls.append(url)

        # Extract srcset for picture elements (use the highest resolution)
        elif img.name == 'picture':
            sources = img.find_all('source')
            for source in sources:
                srcset = source.get('srcset')
                if srcset:
                    # Get the highest resolution image from the srcset
                    urls = srcset.split(',')
                    highest_res_url = sorted(urls, key=lambda x: int(re.search(r'(\d+)w', x).group(1) if re.search(r'(\d+)w', x) else 0), reverse=True)[0]
                    final_url = highest_res_url.split(' ')[0]  # Get URL only
                    if is_product_image(final_url) and verify_image_size(final_url) and verify_image_url(final_url) and final_url not in image_urls:
                        image_urls.append(final_url)

    # Return the first 3 unique product image URLs
    print(image_urls)
    return image_urls[:3]

def get_page_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Cloudflare often blocks headless browsers
            args=['--disable-features=site-per-process']  # Help bypass security features
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        try:
            # Add random delay to appear more human-like
            page.wait_for_timeout(random.randint(2000, 5000))
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for potential Cloudflare challenge
            page.wait_for_selector('body', timeout=10000)
            
            # Additional wait if Cloudflare challenge appears
            if page.query_selector('iframe[title*="challenge"]'):
                page.wait_for_timeout(10000)
            
            html = page.content()
            return html
            
        except Exception as e:
            print(f"Error accessing {url}: {e}")
            return ""
        finally:
            context.close()
            browser.close()

def scrape_and_query(url: str, question: str):
    # Get HTML content using Playwright
    html_content = get_page_html(url)
    image_urls = extract_images(html_content)
    
    # Get ingredients using existing scraper
    scraper_config = ScraperConfig(
        use_current_browser=False,
        headless=True,
        max_retries=3,
        delay_after_load=5,
        debug=True,
        wait_for='domcontentloaded'
    )
    web_scraper_chat = StreamlitWebScraperChat(model_name="gpt-4o-mini", scraper_config=scraper_config)
    scraped_data = web_scraper_chat.process_message(url)

    if "Error" in scraped_data:
        return {"Error": scraped_data}, []

    combined_query = f"""
    From this product page content, extract ONLY the ingredients list:
    {scraped_data}
    Return ONLY the comma-separated list of ingredients, with no additional text or formatting.
    """
    ingredients_response = query_model(combined_query)

    return ingredients_response, image_urls

def format_product_data(ingredients: str, image_urls: List[str], product_info: Dict) -> Dict:
    # Clean up ingredients string
    cleaned_ingredients = ingredients.strip()
    
    try:
        if cleaned_ingredients.startswith('```json'):
            cleaned_ingredients = cleaned_ingredients.replace('```json', '').replace('```', '')
            ingredients_json = json.loads(cleaned_ingredients)
            cleaned_ingredients = ingredients_json.get('ingredients', 'N/A')
    except:
        pass
    
    if "ingredients:" in cleaned_ingredients.lower():
        cleaned_ingredients = cleaned_ingredients.split("ingredients:", 1)[1]
    cleaned_ingredients = cleaned_ingredients.strip()

    return {
        "Product_Name": product_info.get('product_name', 'N/A'),
        "Brand_Name": product_info.get('brand_name', 'N/A'),
        "Variant_Name": product_info.get('variant_name', 'N/A'),
        "Ingredients_List": cleaned_ingredients if cleaned_ingredients else 'N/A',
        "Product_Images": image_urls if image_urls else []
    }

def construct_product_url(brand: str, product: str, variant: str = "") -> str:
    # Define URL patterns for specific brands
    brand_url_patterns = {
        "laneige": lambda product, variant: f"https://us.laneige.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://us.laneige.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "paula's choice": lambda product, variant: f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "farmacy": lambda product, variant: f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "byoma": lambda product, variant: f"https://byoma.com/product/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://byoma.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "minimalist": lambda product, variant: f"https://beminimalist.co/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://beminimalist.co/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "i'm from": lambda product, variant: f"https://beautybarn.in/product/{product.lower().replace(' ', '-').replace('%', '')}",
        "haruharu wonder": lambda product, variant: f"https://www.haruharuindia.com/product/{product.lower().replace(' ', '-').replace('%', '')}",
        "numbuzin": lambda product, variant: f"https://numbuzinus.com/collections/all-products/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "skin 1004": lambda product, variant: f"https://skin1004.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "beauty of joseon": lambda product, variant: f"https://beautyofjoseon.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "cosrx": lambda product, variant: f"https://www.cosrx.com/products/{product.lower().replace(' ', '-')}.replace('%', '')",
        "isntree": lambda product, variant: f"https://beautybarn.in/product/isntree-{product.lower().replace(' ', '-').replace('%', '')}",
        "by wishtrend": lambda product, variant: f"https://bywishtrend.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "one thing": lambda product, variant: f"https://limese.com/products/one-thing-{product.lower().replace(' ', '-').replace('%', '')}",
        "innisfree": lambda product, variant: f"https://us.innisfree.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "the face shop": lambda product, variant: f"https://thefaceshop.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "tirtir": lambda product, variant: f"https://tirtir.us/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "simple": lambda product, variant: f"https://www.simpleskincare.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "foxtale": lambda product, variant: f"https://foxtale.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "first aid beauty": lambda product, variant: f"https://www.firstaidbeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "fae beauty": lambda product, variant: f"https://www.faebeauty.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "d'you": lambda product, variant: f"https://www.dyou.co/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "inde wild": lambda product, variant: f"https://www.indewild.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "klairs": lambda product, variant: f"https://www.klairscosmetics.com/product/{product.lower().replace(' ', '-').replace('%', '')}",
    }

    # Default URL format for brands not in the specific mapping
    default_url = lambda product, variant: f"https://{brand.lower().replace(' ', '')}.com/product/{product.lower().replace(' ', '-')}" if not variant else f"https://{brand.lower().replace(' ', '')}.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}/"

    # Use the brand-specific pattern or fallback to the default pattern
    url_generator = brand_url_patterns.get(brand.lower(), default_url)
    return url_generator(product, variant)

def read_product_csv(file_path: str) -> List[Dict]:
    products = []
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                url = construct_product_url(
                    row['brand_name'],
                    row['product_name'],
                    row.get('variant_name', '')
                )
                products.append({**row, 'url': url})
        return products
    except Exception as e:
        raise Exception(f"Error reading CSV: {str(e)}")

if __name__ == "__main__":
    csv_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\Products_List2.csv"
    products = read_product_csv(csv_path)
    output_file_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\crawled_products9.json"
    
    with open(output_file_path, "w") as f:
        json.dump([], f)

    for product in products:
        raw_ingredients, image_urls = scrape_and_query(product['url'], "")
        formatted_data = format_product_data(raw_ingredients, image_urls, product)
        
        with open(output_file_path, "r") as f:
            existing_data = json.load(f)
        
        existing_data.append(formatted_data)
        
        with open(output_file_path, "w") as f:
            json.dump(existing_data, f, indent=4)
            
        print(f"Processed and stored: {product['brand_name']} - {product['product_name']}")

