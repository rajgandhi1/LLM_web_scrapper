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
from chardet import detect

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
        # print(f"Error verifying image size: {e}")
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
    #print(image_urls)
    return image_urls[:3]

def get_page_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Cloudflare often blocks headless browsers
            args=['--disable-features=site-per-process', '--no-sandbox', '--disable-setuid-sandbox']  # Help bypass security features
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        try:
            # Add random delay to appear more human-like
            page.wait_for_timeout(random.randint(2000, 5000))
            page.goto(url, wait_until='load', timeout=30000)

            # Wait for body to load and check for potential Cloudflare challenge
            page.wait_for_selector('body', timeout=10000)
            
            if page.query_selector('iframe[title*="challenge"]'):
                page.wait_for_timeout(15000)  # Wait longer for challenge
                page.reload()  # Attempt to reload to pass challenge

            # Interact with possible overlay or modal (if any)
            try:
                page.click('button#accept-cookies')  # Example button
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"No cookie acceptance button: {e}")
            
            html = page.content()
            return html
            
        except Exception as e:
            print(f"Error accessing {url}: {e}")
            return ""
        finally:
            context.close()
            browser.close()

def scrape_and_query(url: str, question: str, brand: str, product: str, variant: str = ""):
    """
    Modified scrape_and_query function that first checks IncideCoder.
    """
    # First try IncideCoder
    incidecoder_url = search_incidecoder(brand, product, variant)
    if incidecoder_url:
        print(f"Found product on IncideCoder: {incidecoder_url}")
        incidecoder_data = extract_incidecoder_details(incidecoder_url)
        
        if incidecoder_data:
            return (
                incidecoder_data["ingredients"],
                incidecoder_data["image_urls"],
                incidecoder_data["description"],
                analyze_product_claims(incidecoder_data["description"])
            )
    
    # If IncideCoder fails, fall back to original workflow
    print("Falling back to original workflow...")
    html_content = get_page_html(url)
    
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
        scraped_data = ""

    ingredients_response_2 = search_and_extract_ingredients(html_content)
    final_ingredients_list = ingredients_response_2

    image_urls = extract_images(html_content)
    description = extract_product_description(html_content)
    claims_analysis = analyze_product_claims(description)

    return final_ingredients_list, image_urls, description, claims_analysis

def format_product_data(ingredients: str, image_urls: List[str], description: str, claims: str, product_info: Dict) -> Dict:
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

    # Clean up description and claims
    cleaned_description = clean_llm_response(description)
    cleaned_claims = clean_llm_response(claims)

    return {
        "Product_Name": product_info.get('product_name', 'N/A'),
        "Brand_Name": product_info.get('brand_name', 'N/A'),
        "Variant_Name": product_info.get('variant_name', 'N/A'),
        "Ingredients_List": cleaned_ingredients if cleaned_ingredients else 'N/A',
        "Product_Images": image_urls if image_urls else [],
        "Product_url": product_info.get('url', 'N/A')
    }
    # return {
    #         "Product_Name": product_info.get('product_name', 'N/A'),
    #         "Brand_Name": product_info.get('brand_name', 'N/A'),
    #         "Variant_Name": product_info.get('variant_name', 'N/A'),
    #         "Description": cleaned_description if cleaned_description else 'N/A',
    #         "Claims": cleaned_claims if cleaned_claims else 'N/A',
    #         "Product_url": product_info.get('url', 'N/A')
    #     }

def construct_product_url(brand: str, product: str, variant: str = "") -> str:
    # Define URL patterns for specific brands
    brand_url_patterns = {
        "laneige": lambda product, variant: f"https://us.laneige.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://us.laneige.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "paula's choice": lambda product, variant: f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "farmacy": lambda product, variant: f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "byoma": lambda product, variant: f"https://byoma.com/product/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://byoma.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "minimalist": lambda product, variant: f"https://incidecoder.com/products/be-minimalist-{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://beminimalist.co/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "i'm from": lambda product, variant: f"https://beautybarn.in/product/im-from-{product.lower().replace(' ', '-').replace('%', '')}",
        "haruharu wonder": lambda product, variant: f"https://www.haruharuindia.com/product/{product.lower().replace(' ', '-').replace('%', '')}",
        "numbuzin": lambda product, variant: f"https://numbuzinus.com/collections/all-products/products/numbuzin-{product.lower().replace(' ', '-').replace('%', '')}",
        "skin 1004": lambda product, variant: f"https://skin1004.com/products/skin1004-{product.lower().replace(' ', '-').replace('%', '')}",
        "beauty of joseon": lambda product, variant: f"https://beautyofjoseon.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "cosrx": lambda product, variant: f"https://www.cosrx.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "isntree": lambda product, variant: f"https://beautybarn.in/product/isntree-{product.lower().replace(' ', '-').replace('%', '')}",
        "by wishtrend": lambda product, variant: f"https://bywishtrend.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "one thing": lambda product, variant: f"https://limese.com/products/one-thing-{product.lower().replace(' ', '-').replace('%', '')}",
        "innisfree": lambda product, variant: f"https://us.innisfree.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "the face shop": lambda product, variant: f"https://thefaceshop.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "tirtir": lambda product, variant: f"https://incidecoder.com/products/tirtir-{product.lower().replace(' ', '-').replace('%', '')}",
        "simple": lambda product, variant: f"https://incidecoder.com/products/simple-{product.lower().replace(' ', '-').replace('%', '')}",
        "foxtale": lambda product, variant: f"https://foxtale.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "first aid beauty": lambda product, variant: f"https://www.firstaidbeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "fae beauty": lambda product, variant: f"https://https://incidecoder.com/products/fae-{product.lower().replace(' ', '-').replace('%', '')}",
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
        # Detect file encoding
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            detected_encoding = detect(raw_data)['encoding']
        
        with open(file_path, mode='r', newline='', encoding=detected_encoding) as file:
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

def search_and_extract_ingredients(html_content: str) -> str:
    """
    Extract ingredients list from the provided HTML content.

    Args:
        html_content (str): The HTML content of the product page.

    Returns:
        str: Extracted ingredients list or error message.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Method 1: Look for elements with specific keywords in class names or IDs
        ingredient_keywords = ['ingredient', 'ingredients', 'product_list', 'ingredient_list', 
                             'accordion-panel-ingredients', 'product-ingredients']
        
        # Initialize potential ingredients list
        potential_ingredients = []
        
        # Search in class names and IDs
        for keyword in ingredient_keywords:
            # Search by class
            elements = soup.find_all(class_=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_ingredients.append(element.get_text().strip())
            
            # Search by ID
            elements = soup.find_all(id=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_ingredients.append(element.get_text().strip())

        # Method 2: Look for common container elements that might contain ingredients
        for tag in ['div', 'table', 'ul', 'ol', 'p', 'section']:
            elements = soup.find_all(tag)
            for element in elements:
                text = element.get_text().lower().strip()
                # Check if the element or its parent has ingredients-related text
                if any(keyword in text for keyword in ingredient_keywords):
                    potential_ingredients.append(element.get_text().strip())
                
                # Check for ingredient lists that start with common ingredient patterns
                if re.search(r'^(water|aqua|butylene glycol|glycerin|niacinamide)', text, re.IGNORECASE):
                    potential_ingredients.append(element.get_text().strip())

        # Method 3: Look for structured data in JSON-LD
        json_ld = soup.find_all('script', type='application/ld+json')
        for script in json_ld:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Look for ingredients in various possible JSON structures
                    ingredients = data.get('ingredients') or \
                                data.get('product', {}).get('ingredients') or \
                                data.get('mainEntity', {}).get('ingredients')
                    if ingredients:
                        if isinstance(ingredients, list):
                            potential_ingredients.append(', '.join(ingredients))
                        elif isinstance(ingredients, str):
                            potential_ingredients.append(ingredients)
            except (json.JSONDecodeError, AttributeError):
                continue

        # If we found potential ingredients, verify them with the LLM
        if potential_ingredients:
            prompt = f"""
            Analyze the following text sections and extract ONLY the ingredients list.
            Return the ingredients as a comma-separated list. If multiple ingredient lists are found,
            return the most complete one.

            Text sections:
            {' '.join(potential_ingredients)}

            Format the response as a simple comma-separated list without any additional text or formatting.
            """
            verified_ingredients = query_model(prompt)
            return verified_ingredients

        return "Ingredients not found in the product page."

    except Exception as e:
        print(f"Error in search_and_extract_ingredients: {e}")
        return "Error extracting ingredients."

def clean_llm_response(text: str) -> str:
    """
    Clean up LLM response by removing JSON formatting and unnecessary markers.
    """
    # Remove JSON code block markers
    text = text.replace('```json', '').replace('```', '').strip()
    
    try:
        # Try to parse as JSON if it looks like JSON
        if text.startswith('{') and text.endswith('}'):
            data = json.loads(text)
            # Handle different possible JSON structures
            if isinstance(data, dict):
                if 'Claims' in data:
                    # Properly handle newlines in "Claims" field
                    data['Claims'] = data['Claims'].replace('\\n', '\n').strip()
                if 'Description' in data:
                    # Handle newlines in "Description" field if needed
                    data['Description'] = data['Description'].replace('\\n', '\n').strip()
                # Format and return the JSON as a string for display
                return json.dumps(data, indent=4)
    except json.JSONDecodeError:
        pass
    
    return text

def extract_product_description(html_content: str) -> str:
    """
    Extract product description from the HTML content.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Keywords for description and claims
        desc_keywords = ['description', 'product-description', 'product_desc', 
                         'product-overview', 'product-info', 'product-details']
        claims_keywords = ['claims', 'benefits', 'features', 'proven-claims', 
                           'why-we-love-it', 'why-we-love', 'research-results']

        potential_descriptions = []
        potential_claims = []

        # Extract description
        for keyword in desc_keywords:
            elements = soup.find_all(class_=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_descriptions.append(element.get_text().strip())
            elements = soup.find_all(id=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_descriptions.append(element.get_text().strip())

        # Extract claims, including "Why We Love It" and "Research Results"
        for keyword in claims_keywords:
            elements = soup.find_all(class_=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_descriptions.append(element.get_text().strip())
            elements = soup.find_all(id=lambda x: x and keyword in x.lower() if x else False)
            for element in elements:
                potential_descriptions.append(element.get_text().strip())

        # Look for additional details in structured data (JSON-LD)
        json_ld = soup.find_all('script', type='application/ld+json')
        for script in json_ld:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    description = data.get('description') or \
                                  data.get('product', {}).get('description') or \
                                  data.get('mainEntity', {}).get('description')
                    if description:
                        potential_descriptions.append(description)

                    claims = data.get('claims') or data.get('benefits') or data.get('features')
                    if claims:
                        potential_descriptions.extend(claims if isinstance(claims, list) else [claims])
            except (json.JSONDecodeError, AttributeError):
                continue

        # If we found potential descriptions, verify and clean them with the LLM
        if potential_descriptions:
            prompt = """
            Analyze the following text sections and extract the main product description.
            Do not add any information that is not already present in the text. Remove any marketing fluff, prices, or irrelevant details.
            Return only the core product description as plain text, exactly as it appears in the provided text, without any formatting or additions.

            Text sections:
            {}
            """.format(' '.join(potential_descriptions))
            
            verified_description = query_model(prompt)
            return clean_llm_response(verified_description)

        return "Description not found in the product page."

    except Exception as e:
        print(f"Error in extract_product_description: {e}")
        return "Error extracting description."

def analyze_product_claims(description: str) -> str:
    """
    Analyze product claims using LLM.
    """
    prompt = f"""
    Analyze the following product description and extract all claims made by the product.
    
    Return the analysis as plain text in exactly this format without any JSON or other formatting:
    PROVEN CLAIMS:
    - Claim 1
    - Claim 2
    - Claim 3
    - Claim 4 ...
    
    Here is the product description:
    {description}
    """
    claims_response = query_model(prompt)
    return clean_llm_response(claims_response)

def search_incidecoder(brand: str, product: str, variant: str = "") -> Optional[str]:
    """
    Search IncideCoder for a product and return the first result URL if found.
    """
    search_query = f"{brand} {product} {variant}".strip()
    search_url = f"https://incidecoder.com/search?query={requests.utils.quote(search_query)}"
    
    try:
        with sync_playwright() as p:
            # Launch with more browser-like settings
            browser = p.chromium.launch(
                headless=False,  # Use headed mode to appear more human-like
                args=[
                    '--disable-features=site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                ]
            )
            
            # Set up context with more realistic browser properties
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                java_script_enabled=True,
            )
            
            # Add cookies and headers that a real browser would have
            context.add_cookies([
                {
                    'name': 'accept_cookies',
                    'value': 'true',
                    'domain': 'incidecoder.com',
                    'path': '/'
                }
            ])
            
            page = context.new_page()
            
            # Add random delay before navigation
            page.wait_for_timeout(random.randint(2000, 5000))
            
            # Try multiple times with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Navigate with more realistic settings
                    page.set_extra_http_headers({
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                    })
                    
                    # Navigate and wait for content
                    page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                    
                    # Add random mouse movements and scrolls
                    page.mouse.move(random.randint(100, 700), random.randint(100, 700))
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2);')
                    page.wait_for_timeout(random.randint(1000, 3000))
                    
                    # Wait for search results with retry logic
                    for selector in ['a.klavika.simpletextlistitem', '.product-list-item a', 'a[href*="/products/"]']:
                        try:
                            element = page.wait_for_selector(selector, timeout=10000)
                            if element:
                                href = element.get_attribute('href')
                                if href:
                                    return f"https://incidecoder.com{href}"
                        except:
                            continue
                    
                    # Check if redirected to product page
                    if page.url != search_url and '/products/' in page.url:
                        return page.url
                        
                    break  # If we get here without finding results, stop retrying
                    
                except Exception as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5000  # Increase wait time with each retry
                        page.wait_for_timeout(wait_time)
                        continue
                    raise
            
            return None
            
    except Exception as e:
        print(f"Error searching IncideCoder: {e}")
        return None

def extract_incidecoder_details(url: str) -> Dict:
    """
    Extract product details from an IncideCoder product page.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = context.new_page()
            page.goto(url, wait_until='load', timeout=30000)
            
            # Extract ingredients
            ingredients_element = page.query_selector('#ingredlist-short')
            ingredients = ingredients_element.inner_text() if ingredients_element else ""
            
            # Extract product image
            image_element = page.query_selector('.product-main-image img')
            image_url = image_element.get_attribute('src') if image_element else None
            image_urls = [f"https://incidecoder.com{image_url}"] if image_url else []
            
            # Extract product description
            description_element = page.query_selector('.product-description')
            description = description_element.inner_text() if description_element else ""
            
            return {
                "ingredients": ingredients,
                "image_urls": image_urls,
                "description": description,
                "source": "incidecoder"
            }
            
    except Exception as e:
        print(f"Error extracting from IncideCoder: {e}")
        return None
     
if __name__ == "__main__":
    csv_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\Products_List_1000.csv"
    products = read_product_csv(csv_path)
    output_file_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\crawled_products_ingredients_1000.json"

    with open(output_file_path, "w") as f:
        json.dump([], f)

    for product in products:
        raw_ingredients, image_urls, description, claims = scrape_and_query(
            product['url'], 
            "", 
            product['brand_name'], 
            product['product_name'],
            product.get('variant_name', '')
        )
        formatted_data = format_product_data(
            raw_ingredients, image_urls, description, claims, product
        )

        with open(output_file_path, "r") as f:
            existing_data = json.load(f)

        existing_data.append(formatted_data)

        with open(output_file_path, "w") as f:
            json.dump(existing_data, f, indent=4)

        print(f"Processed and stored: {product['brand_name']} - {product['product_name']}")


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