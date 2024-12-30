import json
import requests
from app.streamlit_web_scraper_chat import StreamlitWebScraperChat
from src.scrapers.playwright_scraper import ScraperConfig

def query_model(prompt, model_name="llama3.1:8b"):
    """
    Query the Ollama server with a prompt and return the response.

    Args:
        prompt (str): The prompt to send to the model.
        model_name (str): The name of the model to use.

    Returns:
        str: The model's response.
    """
    url = "http://127.0.0.1:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    payload = {"prompt": prompt, "model": model_name}

    try:
        response = requests.post(url, headers=headers, json=payload, stream=True)
        response.raise_for_status()

        # Process streamed JSON objects
        full_response = ""
        for line in response.iter_lines():
            if line:  # Skip empty lines
                try:
                    json_data = json.loads(line)
                    if "response" in json_data:
                        full_response += json_data["response"]
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON line: {e}")

        return full_response

    except requests.RequestException as e:
        return f"Error querying the model: {e}"

def scrape_and_query(url, question):
    """
    Scrape a website and query the extracted data.

    Args:
        url (str): The URL of the website to scrape.
        question (str): The question to ask about the scraped data.

    Returns:
        str: The response to the query.
    """
    # Scraper configuration
    scraper_config = ScraperConfig(
        use_current_browser=False,  # Adjust as needed
        headless=True,
        max_retries=3,
        delay_after_load=5,
        debug=True,
        wait_for='domcontentloaded'
    )

    # Initialize the web scraper
    web_scraper_chat = StreamlitWebScraperChat(model_name="llama3.1:8b", scraper_config=scraper_config)

    # Step 1: Scrape the website
    print(f"Scraping URL: {url}")
    scraped_data = web_scraper_chat.process_message(url)

    if "Error" in scraped_data:
        print(f"Error during scraping: {scraped_data}")
        return scraped_data

    print("Scraping completed.")

    # Step 2: Combine scraped data with the query
    combined_query = f"The following data was extracted from the website:\n\n{scraped_data}\n\n{question}"
    print(f"Querying data: {combined_query}")
    
    query_response = query_model(combined_query)

    if "Error" in query_response:
        print(f"Error during query: {query_response}")
        return query_response

    print("Query completed.")

    return query_response

if __name__ == "__main__":
    # Define the URL and the question
    target_url = "https://byoma.com/product/hydrating-serum/"
    query_question = (
        "Get the product details for the above product in this format:\n"
        "brand_name,product_name,variant_name,ingredients,images,"
        "marketing_claims,has_complete_ingredients and source_url."
    )

    # Execute the scrape and query workflow
    result = scrape_and_query(target_url, query_question)

    # Output the result
    print("\nResult:")
    print(result)

    # Optionally save the result to a file
    with open(r"C:\Users\Deva_pg\Downloads\honestly\crawled_products2.json", "w") as output_file:
        json.dump(result, output_file, indent=4)
    print("Result saved to output.json.")
