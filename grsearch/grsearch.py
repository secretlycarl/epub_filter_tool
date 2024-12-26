from concurrent.futures import ThreadPoolExecutor
import os
import re
import urllib.parse
import aiohttp
import asyncio
from bs4 import BeautifulSoup, SoupStrainer
from transformers import AutoModelForCausalLM, AutoProcessor

# Model setup
model_id = "microsoft/Phi-3.5-vision-instruct"
model = AutoModelForCausalLM.from_pretrained(
    model_id, 
    device_map="cuda", 
    trust_remote_code=True, 
    torch_dtype="auto", 
    _attn_implementation='eager'    
)
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

def clean_filename_with_llm(filename):
    """Use LLM to clean up the filename."""
    system_prompt = (
        "This is a filename, please clean it up. Your output should be in the format of [title] [author name]. "
        "You will remove any punctuation and symbols except for periods, replace any double spaces with a single space, "
        "and remove any non-title or author name words. Examples - "
        '"A Christmas Carol (NOVEL, 2012, v. 1  IN GREEK) (Greek Edition) - KONDYLIS, THANOS.epub" becomes '
        '"A Christmas Carol Thanos Kondylis". '
        '"a to Z of Girlfriends, The - Natasha West.epub" becomes "The a to Z of Girlfriends Natasha West".'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Filename: {filename}"}
    ]

    prompt = processor.tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = processor(prompt, return_tensors="pt").to("cuda:0")

    generation_args = {
        "max_new_tokens": 1000,
        "temperature": 0.0,
        "do_sample": False,
    }

    generate_ids = model.generate(**inputs,
                                  eos_token_id=processor.tokenizer.eos_token_id,
                                  **generation_args)

    # Remove input tokens
    generate_ids = generate_ids[:, inputs['input_ids'].shape[1]:]
    response = processor.batch_decode(generate_ids,
                                      skip_special_tokens=True,
                                      clean_up_tokenization_spaces=False)[0]
    return response.strip()

def sanitize_filename(filename):
    """Sanitize filenames for better search terms."""
    sanitized = filename.replace(".epub", "")
    sanitized = re.sub(r"[!\"#$%&'()*+,/:;<=>?@[\\]^_`{|}~]", "", sanitized)
    sanitized = sanitized.replace("'", "")
    sanitized = re.sub(r"[\[\](){}]", "", sanitized)
    sanitized = sanitized.replace(" - ", " ")
    sanitized = sanitized.replace("- ", " ")
    return sanitized

def process_single_file(filename, directory):
    """Process a single file: clean with LLM, sanitize, and search Goodreads."""
    cleaned_filename = clean_filename_with_llm(filename)
    sanitized_filename = sanitize_filename(cleaned_filename)
    return filename, sanitized_filename, directory

def save_genres_to_file(original_filename, genres, directory):
    """Save the genres or status message to a txt file in the same directory as the epub."""
    base_filename = os.path.splitext(original_filename)[0]
    file_path = os.path.join(directory, base_filename + ".txt")
    
    if genres:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(", ".join(genres))
        print(f"Genres saved to: {file_path}")
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unknown")
        print(f"No search results found, saved 'unknown' to: {file_path}")

async def fetch(session, url):
    """Fetch a URL asynchronously."""
    async with session.get(url) as response:
        return await response.text()

async def search_goodreads_and_extract_genres(query_data):
    """Search Goodreads for a book and extract its genres if the book has enough ratings."""
    original_filename, sanitized_filename, directory = query_data
    base_url = "https://www.goodreads.com/search?q="
    encoded_query = urllib.parse.quote_plus(sanitized_filename)
    search_url = base_url + encoded_query

    async with aiohttp.ClientSession() as session:
        search_page = await fetch(session, search_url)
        soup = BeautifulSoup(search_page, "lxml", parse_only=SoupStrainer("tr", {"itemscope": "", "itemtype": "http://schema.org/Book"}))

        first_result = soup.find("tr", {"itemscope": "", "itemtype": "http://schema.org/Book"})

        if not first_result:
            print(f"No search results found for query: {sanitized_filename}")
            save_genres_to_file(original_filename, None, directory)
            return

        ratings_count = extract_ratings_from_search_page(first_result)

        if ratings_count < 500:
            print(f"Skipping '{sanitized_filename}' as it has less than 500 ratings.")
            save_genres_to_file(original_filename, ["unpopular"], directory)
            return

        book_link = first_result.find("a", class_="bookTitle")
        if not book_link or not book_link["href"]:
            print(f"Book link not found in the first result for query: {sanitized_filename}")
            save_genres_to_file(original_filename, None, directory)
            return

        book_url = "https://www.goodreads.com" + book_link["href"]
        print(f"Book URL: {book_url}")

        book_page = await fetch(session, book_url)
        genres = extract_genres_from_goodreads(book_page)

        if genres:
            save_genres_to_file(original_filename, genres, directory)
        else:
            save_genres_to_file(original_filename, None, directory)

def extract_ratings_from_search_page(result):
    """Extract the number of ratings from the search page result."""
    ratings_span = result.find("span", class_="greyText smallText uitext")
    if ratings_span:
        minirating = ratings_span.find("span", class_="minirating")
        if minirating:
            ratings_text = minirating.text.split("—")[-1].strip()
            ratings_count_str = ratings_text.split()[0].replace(",", "")
            try:
                ratings_count = int(ratings_count_str)
                return ratings_count
            except ValueError:
                print("Error parsing ratings count.")
                return 0
    return 0

def extract_genres_from_goodreads(page_content):
    """Extract genres from a Goodreads book page content."""
    soup = BeautifulSoup(page_content, 'lxml', parse_only=SoupStrainer('span', class_='BookPageMetadataSection__genreButton'))

    # Find all genre buttons directly
    genres = [
        label.get_text()
        for button in soup.select('span.BookPageMetadataSection__genreButton')
        if (label := button.select_one('span.Button__labelItem'))
    ]

    return genres

def process_folder(directory):
    """Process a folder, prompting for each new folder."""
    filenames = [f for f in os.listdir(directory) if f.endswith(".epub")]

    for i in range(0, len(filenames), 10):  # Process in batches of 10
        batch = filenames[i:i + 10]
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_single_file, batch, [directory] * len(batch)))
            # Ensure that the results are converted into a list before passing to asyncio.gather
            asyncio.run(gather_tasks(results))

async def gather_tasks(results):
    """Run the search_goodreads_and_extract_genres tasks concurrently."""
    await asyncio.gather(*[search_goodreads_and_extract_genres(result) for result in results])

if __name__ == "__main__":
    while True:
        directory = input("Please enter the folder path to process (or type 'exit' to quit): ").strip()
        if directory.lower() == 'exit':
            break
        if os.path.isdir(directory):
            process_folder(directory)
        else:
            print(f"The folder '{directory}' does not exist. Please try again.")
